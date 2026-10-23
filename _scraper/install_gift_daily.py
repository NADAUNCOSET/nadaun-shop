"""Install the owner-requested daily Mac/NAS gift worker without UI focus."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT/'_private/gift/daily-sync'
LABEL = 'co.nadaun.shop.gift-daily-sync'


def main():
    if sys.platform != 'darwin': raise SystemExit('This scheduler installer is for the current Mac only')
    STATE.mkdir(parents=True, exist_ok=True); (STATE/'tmp').mkdir(exist_ok=True)
    # launchd initializes cwd/stdio before the user process opens the SMB share.
    # Bootstrap in the user's directory, then keep the real cwd and all logs on NAS.
    bootstrap = (
        'import os,runpy,sys;from pathlib import Path;'
        'root=Path('+repr(str(ROOT))+');'
        'state=root/"_private/gift/daily-sync";state.mkdir(parents=True,exist_ok=True);'
        'os.chdir(root);'
        'out=open(state/"worker.stdout.log","a",buffering=1);'
        'err=open(state/"worker.stderr.log","a",buffering=1);'
        'os.dup2(out.fileno(),1);os.dup2(err.fileno(),2);'
        'sys.path.insert(0,str(root/"_scraper"));'
        'runpy.run_module("run_gift_daily",run_name="__main__")'
    )
    config = {
        'Label': LABEL,
        'ProgramArguments': [sys.executable, '-c', bootstrap],
        'WorkingDirectory': str(Path.home()),
        'StartCalendarInterval': {'Hour': 7, 'Minute': 10},
        'StartInterval': 900, 'RunAtLoad': True,
        'ProcessType': 'Standard', 'LowPriorityIO': True, 'Nice': 10,
        'EnvironmentVariables': {'PATH': '/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin',
                                 'PYTHONUNBUFFERED': '1', 'TMPDIR': str(STATE/'tmp')},
    }
    source = STATE/(LABEL+'.plist'); source.write_bytes(plistlib.dumps(config))
    destination = Path.home()/'Library/LaunchAgents'/source.name
    destination.parent.mkdir(exist_ok=True)
    if destination.exists():
        previous = plistlib.loads(destination.read_bytes())
        if previous.get('Label') != LABEL or not any(str(ROOT) in value for value in previous.get('ProgramArguments', [])):
            raise SystemExit('Existing worker belongs to a different project')
        old_sha = hashlib.sha256(destination.read_bytes()).hexdigest()
        backup = STATE/('previous-'+old_sha[:16]+'.plist')
        if not backup.exists(): shutil.copy2(destination, backup)
        subprocess.run(['launchctl', 'bootout', 'gui/'+str(os.getuid())+'/'+LABEL], capture_output=True)
    shutil.copy2(source, destination)
    if hashlib.sha256(source.read_bytes()).digest() != hashlib.sha256(destination.read_bytes()).digest():
        raise SystemExit('Installed schedule does not match NAS source')
    subprocess.run(['launchctl', 'bootstrap', 'gui/'+str(os.getuid()), str(destination)], check=True, capture_output=True)
    result = subprocess.run(['launchctl', 'print', 'gui/'+str(os.getuid())+'/'+LABEL], check=True, capture_output=True, text=True)
    (STATE/'launchctl-readback.txt').write_text(result.stdout)
    receipt = {'installed_at': datetime.datetime.now().astimezone().isoformat(), 'label': LABEL,
               'host': os.uname().nodename, 'program': config['ProgramArguments'],
               'daily_target_local_time': '07:10', 'catchup_check_seconds': 900,
               'source_access_guard': str(STATE/'source-access.json'),
               'worker_cwd': str(ROOT), 'logs': str(STATE),
               'requires_mac_awake_and_nas_mounted': True, 'cloud_schedule': False,
               'launchctl_registered': True, 'source_collection_success': False}
    (STATE/'installation.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(receipt, ensure_ascii=False))


if __name__ == '__main__': main()
