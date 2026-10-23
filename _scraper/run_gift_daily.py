"""NAS daily gift feed worker, using existing Git/Vercel operator credentials.

One supported bulk GET per day. No product-page crawler, alternate domain,
cookie export, access-block reset, or payment mutation is implemented here.
"""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
from urllib.request import Request, urlopen
import zipfile

from gift_daily_sync import SOURCE, apply_feed, apply_availability, refresh_metadata, write_catalog, timestamp

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / '_private/gift/daily-sync'
KST = timezone(timedelta(hours=9))
PUBLIC = ['data/gift/catalog.json', 'data/gift/manifest.json', 'data/gift/sync-status.json',
          'gift-sitemap.xml', 'gift-sitemap-1.xml', 'gift-sitemap-2.xml']


def public_paths(root):
    return sorted(set(PUBLIC) | {p.name for p in Path(root).glob('gift-sitemap-*.xml')})


def now(): return datetime.now(KST).isoformat()


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix+'.pending')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n'); tmp.chmod(0o600)
    tmp.replace(path)
    if json.loads(path.read_text()) != data: raise RuntimeError('Saved state readback mismatch')


def command(*args, cwd=ROOT, env=None, input=None):
    p = subprocess.run(args, cwd=cwd, env=env, input=input, text=True, capture_output=True, timeout=240)
    if p.returncode:
        raise RuntimeError('Command failed: '+args[0]+' '+args[1]+'; operator review required')
    return p.stdout.strip()


def git(*args, **kwargs): return command('git', *args, **kwargs)


@contextmanager
def lock():
    path = ROOT/'_scraper/.sync-state/run.lock'
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, 'w') as f: json.dump({'host': socket.gethostname(), 'pid': os.getpid(), 'started_at': now(), 'source': 'gift-daily'}, f)
    try: yield
    finally: path.unlink()


def check_access():
    path = STATE/'source-access.json'
    if not path.exists(): return False, 'source_access_not_verified'
    access = json.loads(path.read_text())
    if access.get('state') != 'ready' or access.get('supported_feed_url') != SOURCE or not access.get('verified_at'):
        return False, access.get('reason', 'source_access_not_verified')
    return True, None


def reconcile_availability(catalog):
    """Consume a provider/export adapter's hash-bound source evidence, if any."""
    receipt = STATE/'availability/current.json'
    if not receipt.exists(): return catalog, []
    record = json.loads(receipt.read_text())
    evidence = record['evidence']
    original = (receipt.parent/record['source_file']).resolve()
    if not original.is_relative_to(receipt.parent.resolve()):
        raise RuntimeError('Availability source file must remain in its NAS evidence folder')
    if hashlib.sha256(original.read_bytes()).hexdigest() != evidence['source_sha256']:
        raise RuntimeError('Availability original checksum mismatch')
    latest = catalog.get('meta', {}).get('mirror', {}).get('last_availability_check_at')
    if latest and timestamp(evidence['observed_at']) <= timestamp(latest):
        return catalog, []
    return apply_availability(catalog, evidence)


def synchronize_head(publication):
    base, commit = publication['base'], publication['commit']
    if git('rev-parse', 'HEAD') == commit:
        return
    with lock():
        if git('rev-parse', 'HEAD') != base or git('diff', '--cached', '--name-only'):
            raise RuntimeError('Local publication recovery requires operator review')
        for name, after in publication['hashes'].items():
            current = hashlib.sha256((ROOT/name).read_bytes()).hexdigest() if (ROOT/name).exists() else None
            if current not in (after, publication['before_hashes'].get(name)):
                raise RuntimeError('Working gift file changed during publication recovery')
        if git('ls-remote', 'origin', 'refs/heads/main').split()[0] != commit:
            raise RuntimeError('Remote advanced during publication recovery')
        for name in publication['hashes']:
            shutil.copy2(Path(publication['run'])/'candidate'/name, ROOT/name)
        git('read-tree', commit); git('update-ref', 'HEAD', commit, base)


def download():
    # The explicit access latch is checked again immediately before networking.
    ready, reason = check_access()
    if not ready: raise RuntimeError('Source access unresolved: '+str(reason))
    with urlopen(Request(SOURCE, headers={'User-Agent': 'NADAUN-OfficialFeed/1.0'}), timeout=45) as response:
        if response.geturl() != SOURCE or response.status != 200:
            raise RuntimeError('Unexpected official feed response or redirect')
        raw = response.read(30_000_001)
        if len(raw) > 30_000_000: raise RuntimeError('Official feed exceeds reviewed size')
        length = response.headers.get('Content-Length')
        if not length or int(length) != len(raw): raise RuntimeError('Incomplete official feed transfer')
        modified = parsedate_to_datetime(response.headers['Last-Modified']).astimezone(timezone.utc)
        age = datetime.now(timezone.utc)-modified
        if age < -timedelta(minutes=5) or age > timedelta(hours=36):
            raise RuntimeError('Source feed is stale or future dated')
        return raw, modified.isoformat()


def api(route, run, body=None):
    args = ['vercel', 'api', route, '--raw']
    if body is not None:
        p = run/'deployment-request.json'; save(p, body)
        args += ['-X', 'POST', '--input', str(p)]
    return json.loads(command(*args))


def deploy_and_verify(commit, hashes, run):
    project = json.loads((ROOT/'.vercel/project.json').read_text())
    receipt_path = run/'deployment-created.json'
    if receipt_path.exists():
        uid = json.loads(receipt_path.read_text())['id']
    else:
        project_info = api('/v9/projects/'+project['projectId']+'?teamId='+project['orgId'], run)
        repo_id = project_info.get('link', {}).get('repoId')
        if not repo_id: raise RuntimeError('Vercel GitHub project linkage missing')
        created = api('/v13/deployments?teamId='+project['orgId'], run, {
            'name': project_info['name'], 'project': project['projectId'], 'target': 'production',
            'gitSource': {'type': 'github', 'repoId': str(repo_id), 'ref': 'main', 'sha': commit}})
        uid = created['id']; save(receipt_path, {'id': uid, 'commit': commit})
    for _ in range(80):
        d = api('/v13/deployments/'+uid+'?teamId='+project['orgId'], run)
        if d['readyState'] in ('ERROR', 'CANCELED'):
            save(run/'deployment-error.json', {k: d.get(k) for k in ('id','readyState','errorCode','errorMessage')})
            raise RuntimeError('Deployment did not complete')
        if d['readyState'] == 'READY': break
        time.sleep(10)
    else: raise RuntimeError('Deployment still pending; resume verification next run')
    if d.get('gitSource', {}).get('sha') != commit or not d.get('aliasAssigned'):
        raise RuntimeError('Deployment identity or alias mismatch')
    if not {'shop.nadaun.co', 'order.nadaun.co'} <= set(d.get('alias', [])):
        raise RuntimeError('Production aliases not assigned')
    for name, expected in hashes.items():
        if not name.startswith(('data/gift/', 'gift-sitemap')): continue
        with urlopen('https://shop.nadaun.co/'+name+'?gift_release='+commit, timeout=45) as response:
            if hashlib.sha256(response.read()).hexdigest() != expected:
                raise RuntimeError('Live gift file mismatch: '+name)
    save(run/'live-verification.json', {'checked_at': now(), 'commit': commit,
                                      'deployment': uid, 'verified_files': len(hashes)})


def publish(run, catalog, receipt):
    # Hold the existing shared catalog lock, but preserve unrelated dirty work.
    with lock():
        if git('diff', '--cached', '--name-only'): raise RuntimeError('Existing staged changes need review')
        base = git('rev-parse', 'HEAD')
        if git('ls-remote', 'origin', 'refs/heads/main').split()[0] != base:
            raise RuntimeError('Remote advanced; no automatic rebase of operator work')
        if git('diff', '--name-only', '--', *public_paths(ROOT)): raise RuntimeError('Existing gift publication edits need review')
        before = {n: hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in public_paths(ROOT) if (ROOT/n).exists()}
        with zipfile.ZipFile(run/'before-change.zip', 'w', compression=zipfile.ZIP_DEFLATED) as backup:
            for n in before: backup.write(ROOT/n, n)
        with zipfile.ZipFile(run/'before-change.zip') as backup:
            if backup.testzip() is not None: raise RuntimeError('Backup verification failed')
            for n,h in before.items():
                if hashlib.sha256(backup.read(n)).hexdigest() != h: raise RuntimeError('Backup checksum mismatch')
        stage = run/'candidate'; stage.mkdir()
        archive = subprocess.Popen(['git', 'archive', base], cwd=ROOT, stdout=subprocess.PIPE)
        unpack = subprocess.run(['tar', '-x', '-C', str(stage)], stdin=archive.stdout, capture_output=True)
        archive.stdout.close()
        if archive.wait() or unpack.returncode: raise RuntimeError('Candidate extraction failed')
        write_catalog(stage, catalog)
        names = public_paths(stage)
        node = shutil.which('node')
        if not node: raise RuntimeError('Node runtime missing')
        p = subprocess.run([node, '--test', '_scraper/tests/gift-search.test.cjs',
                            '_scraper/tests/gift-orders.test.cjs', '_scraper/tests/gift-integration.test.cjs'],
                           cwd=stage, capture_output=True, text=True)
        (run/'tests.log').write_text(p.stdout+'\n'+p.stderr)
        if p.returncode: raise RuntimeError('Gift candidate tests failed')
        command(node, 'server/catalog-release-check.cjs', cwd=stage)
        env = {**os.environ, 'GIT_INDEX_FILE': str(run/'candidate.index')}
        git('read-tree', base, env=env)
        hashes = {}
        for n in names:
            hashes[n] = hashlib.sha256((stage/n).read_bytes()).hexdigest()
            blob = git('hash-object', '-w', str(stage/n))
            git('update-index', '--add', '--cacheinfo', '100644,'+blob+','+n, env=env)
        tree = git('write-tree', env=env)
        if git('rev-parse', 'HEAD') != base or any(hashlib.sha256((ROOT/n).read_bytes()).hexdigest() != h for n,h in before.items()):
            raise RuntimeError('Operator work changed while preparing candidate')
        commit = git('commit-tree', tree, '-p', base, input='chore(gift): daily verified source feed refresh\n')
        publication = {'base': base, 'commit': commit, 'tree': tree, 'hashes': hashes,
                       'before_hashes': before, 'run': str(run), 'receipt': receipt}
        save(run/'publication.json', publication)
        git('push', 'origin', commit+':refs/heads/main')
        save(STATE/'pending-publication.json', publication)
        for n in names: shutil.copy2(stage/n, ROOT/n)
        git('read-tree', commit); git('update-ref', 'HEAD', commit, base)
    deploy_and_verify(commit, hashes, run)
    finish(publication)


def finish(publication):
    save(STATE/'last-success.json', {'checked_at': now(), 'date_kst': datetime.now(KST).date().isoformat(),
                                   'commit': publication['commit'], 'run': publication['run']})
    save(STATE/'status.json', {'state': 'live_verified', 'checked_at': now(), 'commit': publication['commit'],
                              'full_source_complete': False, 'feed_scope': 'naver_channel_subset'})
    pending = STATE/'pending-publication.json'
    if pending.exists(): pending.unlink()


def main():
    STATE.mkdir(parents=True, exist_ok=True)
    pending = STATE/'pending-publication.json'
    if pending.exists():
        p = json.loads(pending.read_text()); synchronize_head(p)
        deploy_and_verify(p['commit'], p['hashes'], Path(p['run'])); finish(p)
        return
    previous = STATE/'status.json'
    if previous.exists() and json.loads(previous.read_text()).get('state') == 'requires_review':
        print('Gift daily sync paused for failure review; requests=0'); return
    if (ROOT/'_scraper/.sync-state/run.lock').exists():
        print('Another catalog worker is active; requests=0'); return
    ready, reason = check_access()
    if not ready:
        save(STATE/'status.json', {'state': 'waiting_source_access', 'checked_at': now(),
                                  'reason': reason, 'requests': 0, 'full_source_complete': False})
        print('Gift daily sync waiting for verified source access; requests=0'); return
    last = STATE/'last-success.json'
    if last.exists() and json.loads(last.read_text())['date_kst'] == datetime.now(KST).date().isoformat():
        print('Gift daily source check already completed today'); return
    run = STATE/'runs'/datetime.now(KST).strftime('%Y%m%d-%H%M%S'); run.mkdir(parents=True)
    raw, modified = download(); observed = now()
    with gzip.open(run/'official-feed.txt.gz', 'wb') as f: f.write(raw)
    with gzip.open(run/'official-feed.txt.gz', 'rb') as f:
        if f.read() != raw: raise RuntimeError('Source backup mismatch')
    catalog = json.loads((ROOT/'data/gift/catalog.json').read_text())
    updated, receipt = apply_feed(catalog, raw, observed_at=observed, modified_at=modified)
    updated, availability_changes = reconcile_availability(updated)
    receipt['availability_changed_ids'] = availability_changes
    updated['meta']['automatic_source_refresh'] = True
    updated['meta']['mirror']['daily_refresh_state'] = 'enabled'
    refresh_metadata(updated); save(run/'source-receipt.json', receipt)
    publish(run, updated, receipt)


if __name__ == '__main__':
    STATE.mkdir(parents=True, exist_ok=True)
    worker_lock = STATE/'worker.lock'
    try: worker_fd = os.open(worker_lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError: raise SystemExit(0)
    with os.fdopen(worker_fd, 'w') as f: json.dump({'pid': os.getpid(), 'host': socket.gethostname(), 'started_at': now()}, f)
    try: main()
    except FileExistsError:
        save(STATE/'status.json', {'state': 'waiting_existing_catalog_worker', 'checked_at': now(), 'requests_retry': False})
        raise SystemExit(0)
    except Exception as e:
        save(STATE/'status.json', {'state': 'requires_review', 'checked_at': now(), 'error': str(e), 'automatic_retry': False})
        print(type(e).__name__+': '+str(e), file=sys.stderr)
        raise SystemExit(1)
    finally:
        worker_lock.unlink()
