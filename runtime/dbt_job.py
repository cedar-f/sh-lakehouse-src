"""Run project-mode dbt with a scoped Thrift schema and pre-SQL validation."""
import json
from pathlib import Path
import sys

from dbt_project import validate_manifest


def run_job(spec):
    from dbt.cli.main import dbtRunner
    from pyhive import hive

    # dbt-spark 1.11 omits database= when opening PyHive connections, which
    # otherwise issues USE default. Scope the correction to this child process.
    connect = hive.connect
    def project_connect(*args, **kwargs):
        kwargs.setdefault('database', spec['destination']['session_schema'])
        return connect(*args, **kwargs)
    hive.connect = project_connect
    common = ['--log-format', 'json', '--no-use-colors', '--profiles-dir', spec['run_dir'],
              '--project-dir', spec['project_dir']]
    if spec.get('parameters'):
        common += ['--vars', json.dumps(spec['parameters'])]
    command = spec['command']
    try:
        if command not in ('deps', 'debug'):
            parsed = dbtRunner().invoke(['parse', *common])
            if not parsed.success:
                if parsed.exception:
                    print(str(parsed.exception), flush=True)
                return 2
            manifest = json.loads((Path(spec['run_dir']) / 'target/manifest.json').read_text())
            validate_manifest(manifest, spec['destination'])
        args = [command, *(['generate'] if command == 'docs' else []), *common]
        if spec.get('select') and command in ('build', 'run', 'test', 'snapshot'):
            args += ['--select', spec['select']]
        result = dbtRunner().invoke(args)
        if result.exception:
            print(str(result.exception), flush=True)
        return 0 if result.success else 1
    finally:
        hive.connect = connect


if __name__ == '__main__':
    try:
        sys.exit(run_job(json.loads(Path(sys.argv[1]).read_text())))
    except Exception as error:
        print('Project configuration error: ' + str(error), flush=True)
        sys.exit(2)
