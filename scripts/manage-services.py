#!/usr/bin/env python3
"""Prepare/install supervised local worker and a daily verified backup; preserves existing app services."""
import argparse
import os
from pathlib import Path
import plistlib
import subprocess
import shutil

ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['prepare','install','status'])
    p.add_argument('--dispatch',action='store_true',help='Enable real outbound sends. Default processes automations without delivering messages.')
    args=p.parse_args()
    domain='gui/'+str(os.getuid())
    if args.action=='status':
        subprocess.run(['launchctl','list'],check=True)
        return
    generated=ROOT/'.review'/'services';generated.mkdir(parents=True,exist_ok=True)
    logs=ROOT/'.local-services';logs.mkdir(exist_ok=True)
    # Reuse the backend's environment and runtime paths without copying its secrets into output.
    backend=Path.home()/'Library'/'LaunchAgents'/'com.antarescrm.backend.plist'
    existing=plistlib.loads(backend.read_bytes()) if backend.exists() else {}
    environment={**existing.get('EnvironmentVariables',{}),'APP_ENV':'production'}
    # LaunchAgents do not inherit the interactive shell's PostgreSQL path.
    binary_dirs = []
    for executable in ('pg_dump', 'pg_restore'):
        resolved = shutil.which(executable)
        if not resolved:
            raise SystemExit('Instale o PostgreSQL antes de preparar os serviços de backup.')
        binary_dirs.append(str(Path(resolved).parent))
    environment['PATH'] = os.pathsep.join(dict.fromkeys(binary_dirs + environment.get('PATH', os.defpath).split(os.pathsep)))
    definitions={
      'worker':{'ProgramArguments':[str(ROOT/'backend/.venv/bin/python'),'-m','flask','--app','run','run-worker','--dispatch' if args.dispatch else '--no-dispatch'], 'KeepAlive':True,'RunAtLoad':True,'ThrottleInterval':10},
      'backup':{'ProgramArguments':[str(ROOT/'backend/.venv/bin/python'),str(ROOT/'scripts/backup.py'),'--verify'],'StartCalendarInterval':{'Hour':3,'Minute':0}},
    }
    for name,extra in definitions.items():
        label='com.antarescrm.'+name
        definition={'Label':label,'WorkingDirectory':str(ROOT/'backend'),'EnvironmentVariables':environment,
            'StandardOutPath':str(logs/(name+'.log')),'StandardErrorPath':str(logs/(name+'.error.log')),**extra}
        filename=label+'.plist';source=generated/filename
        source.write_bytes(plistlib.dumps(definition));source.chmod(0o600)
        if args.action=='install':
            target=Path.home()/'Library'/'LaunchAgents'/filename
            target.parent.mkdir(parents=True,exist_ok=True)
            if target.exists(): subprocess.run(['launchctl','bootout',domain,str(target)],check=False,capture_output=True)
            target.write_bytes(source.read_bytes());target.chmod(0o600)
            subprocess.run(['launchctl','bootstrap',domain,str(target)],check=True)
            print('Serviço instalado:',label)
        else: print('Preparado:',source)


if __name__=='__main__':main()
