"""Recreate PAM accounts after a container replacement; hashes stay in hub_state."""
import json,os,subprocess
from pathlib import Path
directory=Path('/srv/jupyterhub/users'); directory.mkdir(parents=True,exist_ok=True)
for entry in directory.glob('*.json'):
    user=json.loads(entry.read_text())
    check=subprocess.run(['id',user['name']],stdout=subprocess.DEVNULL)
    if check.returncode: subprocess.run(['useradd','-m','-u',str(user['uid']),'-g','1000','-s','/bin/bash',user['name']],check=True)
    subprocess.run(['chpasswd','-e'],input=user['name']+':'+user['hash']+'\n',text=True,check=True)
os.execvp('jupyterhub',['jupyterhub','-f','/opt/lakehouse/hub_config.py'])
