"""Install persistent per-source workers; all code and records stay on NAS."""
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
from sync_shop_sources import ROOT, save_json, stamp
from shop_sync import STATE


def install():
    logs=Path.home()/'Library/Logs/NADAUN/shop'
    agents=Path.home()/'Library/LaunchAgents'
    logs.mkdir(parents=True,exist_ok=True);agents.mkdir(parents=True,exist_ok=True)
    for source in ('gift','plthink'):
        if source == 'gift':
            from sync_gift_inventory import ensure_source_access, GiftSourceSuspended
            try: ensure_source_access()
            except GiftSourceSuspended:
                print('Gift worker remains suspended; provider review required', flush=True)
                continue
        label='co.nadaun.shop.'+source+'-sync'
        target=agents/(label+'.plist')
        awake=shutil.which('caffeinate')
        if not awake:raise RuntimeError('macOS caffeinate is required for the overnight worker')
        definition={'Label':label,'ProgramArguments':[awake,'-i',sys.executable,str(ROOT/'_scraper/partner_worker.py'),source],
            'WorkingDirectory':str(Path.home()),'RunAtLoad':True,'StartInterval':600,'ProcessType':'Standard',
            'StandardOutPath':str(logs/(source+'.stdout.log')),'StandardErrorPath':str(logs/(source+'.stderr.log')),
            'EnvironmentVariables':{'PATH':os.environ.get('PATH','/usr/bin:/bin'),'PYTHONUNBUFFERED':'1'}}
        # Do not stop an active installed worker to update its definition.
        active=subprocess.run(['launchctl','print',f'gui/{os.getuid()}/{label}'],capture_output=True,text=True)
        if active.returncode==0:raise RuntimeError('Partner worker already installed; inspect its state before replacing: '+label)
        with target.open('wb') as handle:plistlib.dump(definition,handle)
        subprocess.run(['launchctl','bootstrap',f'gui/{os.getuid()}',str(target)],check=True)
        loaded=subprocess.check_output(['launchctl','print',f'gui/{os.getuid()}/{label}'],text=True)
        if str(ROOT/'_scraper/partner_worker.py') not in loaded:raise RuntimeError('Worker did not load the NAS entrypoint')
        save_json(STATE/(source+'-schedule.json'),{'label':label,'installed_at':stamp(),'interval_seconds':600,
            'source':'_scraper/partner_worker.py','arguments':[source],'requires':'Mac awake, NAS mounted, network available',
            'scope':'initial inventory resume' if source=='gift' else 'full snapshot every 12 hours; validated publish after completion'})
        print('Verified worker:',label,flush=True)


if __name__=='__main__':install()
