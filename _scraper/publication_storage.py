"""Promote verified candidates under the shared publisher lock; stage exact bytes."""
import json
import os
import socket
import subprocess


def validate_updates(updates):
    sources = {'plthink': 'plthink', 'avx-approved': 'avx', 'dji-official': 'dji-official'}
    for name, snapshot in updates.items():
        if name not in sources or snapshot.get('source') != sources[name]:
            raise ValueError('Unsupported source promotion')
        count = snapshot.get('product_count')
        if (snapshot.get('complete') is not True or not isinstance(count, int) or
                isinstance(count, bool) or count < 1 or
                not isinstance(snapshot.get('products'), dict) or
                count != len(snapshot['products'])):
            raise ValueError('A complete verified source candidate is required')


def promote_updates(updates, root, out, state, managed, save_json):
    validate_updates(updates)
    lock = state / 'run.lock'
    if not lock.is_file():
        raise RuntimeError('Source promotion requires the shared publication lock')
    owner = json.loads(lock.read_text())
    if owner.get('pid') != os.getpid() or owner.get('host') != socket.gethostname():
        raise RuntimeError('Source promotion requires ownership of the publication lock')
    if subprocess.check_output(['git', 'diff', '--cached', '--name-only'], cwd=root).strip():
        raise RuntimeError('Staged operator changes prevent source promotion')
    raw = subprocess.check_output(['git', 'status', '--porcelain=v1', '-z',
                                   '--untracked-files=all'], cwd=root)
    changed = {row[3:].decode() for row in raw.split(b'\0') if row}
    if changed & set(managed):
        raise RuntimeError('Existing generated edits require review before source promotion')
    for name, snapshot in updates.items():
        save_json(out / (name + '.json'), snapshot)


def stage_generated(owned, command):
    # SMB metadata can leave same-size text rewrites out of a normal git add.
    # Reapply the clean filter and compare the index to the actual file bytes.
    command('git', 'add', '--', *owned)
    command('git', 'add', '--renormalize', '--', *owned)
    entries = command('git', 'ls-files', '-s', '-z', '--', *owned)
    indexed = {row.split('\t', 1)[1]: row.split('\t', 1)[0].split()[1]
               for row in entries.split('\0') if row}
    digests = command('git', 'hash-object', '--', *owned).splitlines()
    if len(digests) != len(owned) or any(indexed.get(name) != digest
                                       for name, digest in zip(owned, digests)):
        raise RuntimeError('Staged catalogue bytes differ from the generated files')
