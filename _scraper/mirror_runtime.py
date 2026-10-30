"""Run automatic publication from a clean NAS Git worktree, preserving edits.

The operator's working tree is never reset. Only exact generated paths that
still equal the previous committed bytes may be synchronized after a push.
"""
from pathlib import Path
import hashlib,io,json,os,shutil,subprocess,tarfile,datetime
from mirror_schedule import atomic_json

OPERATOR_FILES=['data/catalog/brand-source-policy.json','data/catalog/overrides.json',
    'data/catalog/dedup-rules.json','data/catalog/banners.json','data/catalog/promotions.json']

def git(root,*args,input=None):
    result=subprocess.run(['git',*args],cwd=root,input=input,capture_output=True,check=True)
    return result.stdout

def head(root):return git(root,'rev-parse','HEAD').decode().strip()

def master_for(runtime):
    value=os.environ.get('NADAUN_SHOP_MASTER_ROOT')
    if not value:return None
    master=Path(value).resolve();runtime=Path(runtime).resolve()
    if master==runtime or runtime.parent!=master.parent or runtime.name!=master.name+'-auto':
        raise ValueError('Automatic runtime must be the adjacent approved NAS worktree')
    return master

def ensure(master):
    master=Path(master).resolve();runtime=master.with_name(master.name+'-auto')
    commit=head(master)
    if git(master,'diff','--cached','--name-only').strip():raise RuntimeError('Operator has staged changes; automatic runtime waits')
    if git(master,'diff','--name-only','--',*OPERATOR_FILES).strip():raise RuntimeError('Operator source/price/banner policy is being edited; publication waits')
    if not runtime.exists():
        git(master,'worktree','add','--detach','--no-checkout',str(runtime),commit)
        git(runtime,'sparse-checkout','init','--no-cone')
        patterns='/*\n!/*/\n/_scraper/\n!/_scraper/_archive/\n!/_scraper/_review/\n!/_scraper/.sync-state/\n/assets/shop/\n/data/catalog/\n/data/gift/\n/server/\n/api/\n/.github/workflows/\n'
        git(runtime,'sparse-checkout','set','--no-cone','--stdin',input=patterns.encode())
        git(runtime,'checkout','--detach',commit)
    else:
        if not (runtime/'.git').is_file():raise ValueError('Existing automatic path is not the registered Git worktree')
        expected=git(runtime,'rev-parse','--git-common-dir').decode().strip()
        if Path(runtime/expected).resolve()!=(master/'.git').resolve():raise ValueError('Automatic worktree belongs to another repository')
        if git(runtime,'diff','--name-only').strip() or git(runtime,'diff','--cached','--name-only').strip():
            raise RuntimeError('Automatic runtime contains an unfinished publication; inspect its saved receipt')
        if head(runtime)!=commit:
            # A failed run may leave generated changes. Preserve these before
            # any checkout; operator edits and source checkpoints remain intact.
            if git(runtime,'diff','--name-only').strip():raise RuntimeError('Automatic runtime contains an unfinished publication; inspect its receipt')
            git(runtime,'checkout','--detach',commit)
    (runtime/'_private').mkdir(exist_ok=True)
    (runtime/'_scraper/.sync-state').mkdir(parents=True,exist_ok=True)
    project=master/'.vercel/project.json'
    if project.is_file():
        dest=runtime/'.vercel/project.json';dest.parent.mkdir(exist_ok=True);shutil.copyfile(project,dest)
    return runtime

def blob_baseline(master,commit,names):
    request=''.join(commit+':'+name+'\n' for name in names).encode()
    result=git(master,'cat-file','--batch',input=request);cursor=0;baseline={}
    for name in names:
        end=result.index(b'\n',cursor);header=result[cursor:end].split();cursor=end+1
        if header[-1]==b'missing':baseline[name]=None;continue
        if header[1]!=b'blob':raise ValueError('Generated path is not a blob: '+name)
        length=int(header[2]);baseline[name]=result[cursor:cursor+length];cursor+=length
        if result[cursor:cursor+1]!=b'\n':raise ValueError('Invalid Git blob response')
        cursor+=1
    if cursor!=len(result):raise ValueError('Unexpected Git blob trailing data')
    return baseline

def prepare_publication(runtime,managed):
    runtime=Path(runtime).resolve();master=master_for(runtime)
    if master is None:return None
    base=head(runtime)
    if head(master)!=base:raise RuntimeError('Operator HEAD changed; automatic candidate must be rebased')
    if git(master,'diff','--cached','--name-only').strip():raise RuntimeError('Operator index changed; automatic publication waits')
    if git(master,'diff','--name-only','--',*OPERATOR_FILES).strip():raise RuntimeError('Operator source policy changed; automatic publication waits')
    names=git(runtime,'diff','--name-only','-z').decode().split('\0')
    tracked=set(git(runtime,'ls-files','-z').decode().split('\0'))
    allowed=set(managed);names=sorted((set(names)&allowed)|(allowed-tracked))
    if any('\n' in n or not (runtime/n).is_file() or Path(n).is_absolute() or '..' in Path(n).parts for n in names):raise ValueError('Invalid generated file path')
    baseline=blob_baseline(master,base,names)
    for name,data in baseline.items():
        target=master/name
        if data is None:
            if target.exists():raise RuntimeError('Untracked operator collision: '+name)
        elif not target.is_file() or target.read_bytes()!=data:raise RuntimeError('Operator generated file was edited: '+name)
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    folder=master/'_private/catalog/automatic-publications'/stamp;folder.mkdir(parents=True)
    archive=folder/'before.tar.gz'
    hashes={}
    with tarfile.open(archive,'w:gz',compresslevel=1) as tar:
        for name,data in baseline.items():
            if data is None:hashes[name]=None;continue
            hashes[name]=hashlib.sha256(data).hexdigest();info=tarfile.TarInfo(name);info.size=len(data);tar.addfile(info,io.BytesIO(data))
    with tarfile.open(archive) as tar:
        for name,digest in hashes.items():
            if digest is not None and hashlib.sha256(tar.extractfile(name).read()).hexdigest()!=digest:raise ValueError('Automatic backup verification failed')
    receipt={'base':base,'master':str(master),'runtime':str(runtime),'files':names,'before_sha256':hashes,
        'after_sha256':{n:hashlib.sha256((runtime/n).read_bytes()).hexdigest() for n in names},
        'backup_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'backup_verified':True,'folder':str(folder),'state':'prepared'}
    atomic_json(folder/'publication.json',receipt)
    return receipt

def synchronize_master(runtime,receipt,commit):
    if receipt is None:return
    runtime=Path(runtime).resolve();master=Path(receipt['master']);base=receipt['base'];folder=Path(receipt['folder'])
    if head(runtime)!=commit or head(master)!=base:raise RuntimeError('Publication HEAD changed before operator synchronization')
    if git(master,'diff','--cached','--name-only').strip():raise RuntimeError('Operator index changed before synchronization')
    for name,before in receipt['before_sha256'].items():
        target=master/name
        if before is None:
            if target.exists():raise RuntimeError('Operator created the pending generated path: '+name)
        elif hashlib.sha256(target.read_bytes()).hexdigest()!=before:raise RuntimeError('Operator edited the pending generated path: '+name)
        if hashlib.sha256((runtime/name).read_bytes()).hexdigest()!=receipt['after_sha256'][name]:raise RuntimeError('Automatic generated content changed after staging')
    for name,digest in receipt['after_sha256'].items():
        target=master/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(runtime/name,target)
        if hashlib.sha256(target.read_bytes()).hexdigest()!=digest:raise ValueError('Master generated readback differs: '+name)
    if git(master,'diff','--cached','--name-only').strip():raise RuntimeError('Operator staged changes during synchronization; inspect saved receipt')
    git(master,'read-tree',commit);git(master,'update-ref','HEAD',commit,base)
    receipt.update(state='pushed_master_synchronized',commit=commit)
    atomic_json(folder/'publication.json',receipt)

def synchronize_review_audits(runtime):
    runtime=Path(runtime).resolve();master=master_for(runtime)
    if master is None:return
    catalog=json.loads((runtime/'data/catalog/catalog.json').read_text());revision=catalog['meta']['revision']
    names=['brand-source-register.json','brand-source-register.md','brand-source-review.md','source-matches.json',
           'category-dedup-review.json','camera-compatibility-review.json','retail-content-review.json']
    for name in names:
        source=runtime/'_private/catalog'/name
        if not source.is_file():raise ValueError('Missing automatic review audit: '+name)
        target=master/'_private/catalog'/name;target.parent.mkdir(parents=True,exist_ok=True)
        backup=master/'_private/catalog/automatic-review-backups'/revision/name
        if target.is_file() and not backup.exists():backup.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(target,backup)
        shutil.copyfile(source,target)
        if hashlib.sha256(source.read_bytes()).digest()!=hashlib.sha256(target.read_bytes()).digest():raise ValueError('Review audit copy failed')
    return master

def detail_fallback(root):
    master=master_for(root)
    return master/'data/catalog/source-details' if master else None
