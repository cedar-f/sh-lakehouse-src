"""Validate real Compose interpolation/merges with fixture credentials only.

Run on the host: python tests/r2_env_config.py
No daemon operations, .env, user data, build or live R2 access.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile


def main():
    root=Path(__file__).resolve().parents[1]
    text=(root/'.env.example').read_text(encoding='utf-8')
    replacements={'R2_ACCOUNT_ID':'fixture-account', 'R2_ACCESS_KEY_ID':'fixture-key',
                  'R2_SECRET_ACCESS_KEY':'fixture-secret', 'R2_BUCKET':'fixture-bucket',
                  'JUPYTER_TOKEN':'fixture-jupyter', 'RUNNER_TOKEN':'fixture-runner',
                  'POSTGRES_PASSWORD':'fixture-postgres', 'KESTRA_PASSWORD':'fixture-kestra'}
    lines=[key+'='+replacements[key] if key in replacements else line
           for line in text.splitlines() for key in [line.split('=',1)[0]]]
    # Stale duplicate aliases in env_file must not override the R2 source of truth.
    fixture='\n'.join(lines)+'\nAWS_ACCESS_KEY_ID=stale-key\nAWS_SECRET_ACCESS_KEY=stale-secret\n'
    env=os.environ.copy()
    for line in fixture.splitlines():
        if '=' in line and not line.startswith('#'):env.pop(line.split('=',1)[0],None)
    env.pop('COMPOSE_FILE',None);env.pop('COMPOSE_PROJECT_NAME',None)
    with tempfile.TemporaryDirectory(prefix='lakehouse-r2-env-') as directory:
        target=Path(directory)
        for filename in ('compose.yaml','compose.hub.yaml'):
            (target/filename).write_text((root/filename).read_text(encoding='utf-8'),encoding='utf-8')
        dotenv=target/'.env';dotenv.write_text(fixture,encoding='utf-8')
        command=['docker','compose','--env-file',str(dotenv),'-f',str(target/'compose.yaml')]
        for hub in (False,True):
            extra=['-f',str(target/'compose.hub.yaml')] if hub else []
            result=subprocess.run([*command,*extra,'config','--format','json'],env=env,cwd=target,capture_output=True,text=True,check=True)
            services=json.loads(result.stdout)['services']
            for name in ('notebook','sql','runner','registry','bootstrap','runtime-init'):
                values=services[name]['environment']
                assert values['AWS_ACCESS_KEY_ID']==replacements['R2_ACCESS_KEY_ID'],name
                assert values['AWS_SECRET_ACCESS_KEY']==replacements['R2_SECRET_ACCESS_KEY'],name
            print('PASS Compose R2 -> AWS aliases, stale env_file override, mode='+('Hub' if hub else 'single-user'))
        dotenv.write_text(fixture.replace('R2_ACCESS_KEY_ID=fixture-key','R2_ACCESS_KEY_ID='),encoding='utf-8')
        result=subprocess.run([*command,'config','--quiet'],env=env,cwd=target,capture_output=True,text=True)
        assert result.returncode!=0 and 'Fill R2_ACCESS_KEY_ID' in result.stderr
        print('PASS empty R2 key rejected before runtime startup')


if __name__=='__main__':main()
