"""Install Mac schedules for the two newly approved, fully scoped suppliers."""
from pathlib import Path
import os,plistlib,shutil,subprocess,sys
from sync_shop_sources import ROOT,save_json,stamp
from reviewed_source_worker import SOURCES

def install():
    awake=shutil.which('caffeinate')
    if not awake:raise RuntimeError('This schedule requires macOS caffeinate')
    agents=Path.home()/'Library/LaunchAgents';logs=Path.home()/'Library/Logs/NADAUN/shop'
    agents.mkdir(parents=True,exist_ok=True);logs.mkdir(parents=True,exist_ok=True)
    for source in SOURCES:
        label='co.nadaun.shop.reviewed-'+source+'-sync';domain='gui/'+str(os.getuid())
        existing=subprocess.run(['launchctl','print',domain+'/'+label],capture_output=True,text=True)
        if existing.returncode==0:raise RuntimeError('Existing supplier schedule must be inspected before replacement: '+label)
        definition={'Label':label,'ProgramArguments':[awake,'-i',sys.executable,str(ROOT/'_scraper/reviewed_source_worker.py'),source],
            'WorkingDirectory':str(Path.home()),'RunAtLoad':False,'StartInterval':600,'ProcessType':'Standard',
            'StandardOutPath':str(logs/(source+'.stdout.log')),'StandardErrorPath':str(logs/(source+'.stderr.log')),
            'EnvironmentVariables':{'PATH':os.environ.get('PATH','/usr/bin:/bin'),'PYTHONUNBUFFERED':'1'}}
        target=agents/(label+'.plist')
        if target.exists():raise RuntimeError('Unloaded existing supplier schedule requires inspection: '+str(target))
        with target.open('wb') as handle:plistlib.dump(definition,handle)
        if plistlib.loads(target.read_bytes())!=definition:raise RuntimeError('Supplier schedule readback differs')
        subprocess.run(['launchctl','bootstrap',domain,str(target)],check=True)
        loaded=subprocess.check_output(['launchctl','print',domain+'/'+label],text=True)
        if str(ROOT/'_scraper/reviewed_source_worker.py') not in loaded:raise RuntimeError('Schedule did not load the NAS entrypoint')
        save_json(ROOT/'_scraper/.sync-state'/(source+'-schedule.json'),{
            'installed_at':stamp(),'label':label,'entrypoint':str(ROOT/'_scraper/reviewed_source_worker.py'),
            'refresh_interval_seconds':43200,'resume_interval_seconds':600,
            'requirements':'Mac awake, NAS mounted, network available',
            'initial_state':'Await initial live receipt; registration alone is not verified source refresh or publication'})
        print('Supplier schedule registered:',label,flush=True)

if __name__=='__main__':install()
