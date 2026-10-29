"""Keep live catalogue SQLite on each PC and verified snapshots on NAS."""
from datetime import datetime, timezone
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import tempfile
import unicodedata


def runtime_root():
    if os.name=='nt':return Path(os.environ['LOCALAPPDATA'])/'NADAUN/shop/catalog'
    return Path.home()/'Library/Application Support/NADAUN/shop/catalog'


def runtime_path(work,source,base=None):
    work=Path(work)
    # Different NAS projects can use the same generation basename. Include the
    # full work identity so a previous job's SQLite can never leak into a new one.
    identity=unicodedata.normalize('NFC',str(work.resolve()))
    suffix=hashlib.sha256(identity.encode()).hexdigest()[:12]
    return (Path(base) if base is not None else runtime_root())/source/(work.name+'-'+suffix)/'checkpoint.sqlite3'


def restore(work,source,base=None):
    work=Path(work);target=runtime_path(work,source,base)
    target.parent.mkdir(parents=True,exist_ok=True)
    snapshot=work/'checkpoint.sqlite3';location=work/'checkpoint-location.json'
    metadata=json.loads(location.read_text()) if location.exists() else {}
    expected=metadata.get('snapshot_sha256');marker=target.parent/'last-snapshot.sha256'
    previous=marker.read_text().strip() if marker.exists() else None
    if snapshot.exists() and (not target.exists() or expected and previous!=expected):
        digest=hashlib.sha256(snapshot.read_bytes()).hexdigest()
        if expected and digest!=expected:raise ValueError('NAS checkpoint snapshot digest differs')
        temp=target.with_suffix('.restore.tmp');shutil.copyfile(snapshot,temp)
        with closing(sqlite3.connect(temp)) as check:
            if check.execute('PRAGMA quick_check').fetchone()!=('ok',):raise ValueError('NAS checkpoint snapshot is corrupt')
        if target.exists():
            backup=target.parent/('before-restore-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f')+'.sqlite3')
            shutil.copyfile(target,backup)
        os.replace(temp,target);marker.write_text(digest+'\n')
    return target


def snapshot(connection,work,database,source):
    """SQLite backup and integrity check run locally; NAS receives a closed file."""
    work=Path(work);database=Path(database)
    with tempfile.TemporaryDirectory(prefix='snapshot-',dir=database.parent) as temporary:
        local=Path(temporary)/'checkpoint.sqlite3'
        with closing(sqlite3.connect(local)) as destination:
            connection.backup(destination)
            if destination.execute('PRAGMA quick_check').fetchone()!=('ok',):raise ValueError('Runtime checkpoint backup is corrupt')
        digest=hashlib.sha256(local.read_bytes()).hexdigest()
        pending=work/('checkpoint.snapshot-'+str(os.getpid())+'.tmp')
        shutil.copyfile(local,pending)
        if hashlib.sha256(pending.read_bytes()).hexdigest()!=digest:raise ValueError('NAS checkpoint copy differs')
        os.replace(pending,work/'checkpoint.sqlite3')
    metadata={'source':source,'computer':socket.gethostname(),'runtime_database':str(database),'nas_work_directory':str(work.resolve()),
        'snapshot_sha256':digest,'snapshot_integrity':'ok','snapshot_at':datetime.now(timezone.utc).isoformat(),
        'nas_database_role':'verified closed recovery snapshot; live SQLite runs on this PC'}
    pending=work/('checkpoint-location-'+str(os.getpid())+'.tmp')
    pending.write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n');os.replace(pending,work/'checkpoint-location.json')
    (database.parent/'last-snapshot.sha256').write_text(digest+'\n')
    return metadata
