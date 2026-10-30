"""Install the Mac supplier queue without changing Windows rental automation."""
from pathlib import Path
import argparse,datetime,hashlib,json,os,plistlib,subprocess,sys
from mirror_schedule import ROOT,policy,atomic_json
from mirror_runtime import ensure,head

LABEL='co.nadaun.shop.mirror-cycle'

def install(enable=False):
    if sys.platform!='darwin':raise RuntimeError('This installer is the macOS launchd entry only')
    settings=policy(ROOT);domain='gui/'+str(os.getuid());target=domain+'/'+LABEL
    path=Path.home()/'Library/LaunchAgents'/(LABEL+'.plist');folder=ROOT/'_private/catalog/auto-mirror';folder.mkdir(parents=True,exist_ok=True)
    if path.exists() or subprocess.run(['launchctl','print',target],capture_output=True).returncode==0:
        raise RuntimeError('Existing mirror queue must be inspected before replacement')
    runtime=ensure(ROOT)
    # Home is only launchd's stable startup cwd. Work, logs and results stay on
    # NAS; an absent NAS exits instead of creating a local replacement folder.
    entry=("import os,runpy,sys;from pathlib import Path;root=Path("+repr(str(ROOT))+");"
        "sys.exit(75) if not (root/'_scraper/mirror_cycle.py').is_file() else None;"
        "os.chdir(root);state=root/'_private/catalog/auto-mirror';state.mkdir(parents=True,exist_ok=True);"
        "out=open(state/'worker.stdout.log','a',buffering=1);err=open(state/'worker.stderr.log','a',buffering=1);"
        "os.dup2(out.fileno(),1);os.dup2(err.fileno(),2);sys.path.insert(0,str(root/'_scraper'));"
        "runpy.run_module('mirror_cycle',run_name='__main__')")
    definition={'Label':LABEL,'ProgramArguments':['/usr/bin/caffeinate','-i',sys.executable,'-c',entry],
        'WorkingDirectory':str(Path.home()),'RunAtLoad':True,'StartInterval':settings['poll_interval_seconds'],
        'ProcessType':'Background','EnvironmentVariables':{'PATH':os.environ.get('PATH','/usr/bin:/bin'),'PYTHONUNBUFFERED':'1'}}
    atomic_json(folder/'control.json',{'enabled':bool(enable),'owner_confirmed_at':settings['confirmed_at'],
        'cadence_seconds':settings['refresh_interval_seconds'],'windows_rental_jobs_changed':False})
    path.parent.mkdir(exist_ok=True)
    data=plistlib.dumps(definition,fmt=plistlib.FMT_XML);path.write_bytes(data)
    backup=folder/'installed-launchagent.plist';backup.write_bytes(data)
    if plistlib.loads(path.read_bytes())!=definition or backup.read_bytes()!=data:raise ValueError('Mac schedule readback differs')
    subprocess.run(['launchctl','enable',target],check=True)
    subprocess.run(['launchctl','bootstrap',domain,str(path)],check=True)
    loaded=subprocess.check_output(['launchctl','print',target],text=True)
    if 'mirror_cycle' not in loaded:raise RuntimeError('Installed service does not reference the NAS queue')
    receipt={'installed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'label':LABEL,'loaded':True,
        'host':__import__('socket').gethostname(),'refresh_interval_seconds':settings['refresh_interval_seconds'],
        'poll_interval_seconds':settings['poll_interval_seconds'],'definition_sha256':hashlib.sha256(data).hexdigest(),
        'entrypoint':str(ROOT/'_scraper/mirror_cycle.py'),'clean_runtime':str(runtime),'code_commit':head(ROOT),'enabled':bool(enable),
        'requires':'Mac awake; NAS connected; source access and verification gates satisfied','windows_rental_automation_changed':False,
        'registration_is_not_source_refresh_success':True}
    atomic_json(folder/'installation.json',receipt);(folder/'launchctl-installed.txt').write_text(loaded)
    print(json.dumps(receipt,ensure_ascii=False),flush=True);return receipt

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--enable',action='store_true');args=parser.parse_args();install(args.enable)
