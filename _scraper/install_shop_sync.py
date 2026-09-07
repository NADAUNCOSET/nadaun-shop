"""Install a daily 08:00 Mac worker using this NAS project as the only source."""
import os
from pathlib import Path
import plistlib
import subprocess
import sys
from sync_shop_sources import ROOT,save_json,stamp
from shop_sync import STATE
LABEL='co.nadaun.shop.catalog-sync'
def install():
    STATE.mkdir(parents=True,exist_ok=True)
    target=Path.home()/'Library/LaunchAgents'/f'{LABEL}.plist'
    target.parent.mkdir(parents=True,exist_ok=True)
    logs=Path.home()/'Library/Logs/NADAUN/shop'
    logs.mkdir(parents=True,exist_ok=True)
    definition={'Label':LABEL,'ProgramArguments':[sys.executable,str(ROOT/'_scraper/shop_sync.py'),'--scheduled'],
      'WorkingDirectory':str(Path.home()),'StartCalendarInterval':{'Hour':8,'Minute':0},
      'RunAtLoad':True,'ProcessType':'Background',
      'StandardOutPath':str(logs/'worker.stdout.log'),'StandardErrorPath':str(logs/'worker.stderr.log'),
      'EnvironmentVariables':{'PATH':os.environ.get('PATH','/usr/bin:/bin'),'PYTHONUNBUFFERED':'1'}}
    if target.exists():subprocess.run(['launchctl','bootout',f'gui/{os.getuid()}',str(target)],capture_output=True)
    with target.open('wb') as f:plistlib.dump(definition,f)
    subprocess.run(['launchctl','bootstrap',f'gui/{os.getuid()}',str(target)],check=True)
    result=subprocess.run(['launchctl','print',f'gui/{os.getuid()}/{LABEL}'],capture_output=True,text=True,check=True)
    if str(ROOT/'_scraper/shop_sync.py') not in result.stdout:raise RuntimeError('LaunchAgent did not load the NAS worker')
    save_json(STATE/'schedule.json',{'label':LABEL,'schedule':'매일 08:00 Asia/Seoul','installed_at':stamp(),'host':os.uname().nodename,'source':'_scraper/shop_sync.py','logs':str(logs),'requires':'Mac on, NAS mounted, network available'})
    print('Verified schedule: '+LABEL+' · daily 08:00 · NAS source '+str(ROOT))
if __name__=='__main__':install()
