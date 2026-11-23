"""Project-owned dbt destinations and Jupyter recovery-file exclusion."""
from pathlib import Path
import re

import yaml

from config import identifier

CHECKPOINT_PATTERN = '**/.ipynb_checkpoints/**'
SCHEMA_MACRO = '''{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if var('lakehouse_catalog', none) is none -%}
        {%- if custom_schema_name is none -%}
            {{ target.schema }}
        {%- else -%}
            {{ target.schema }}_{{ custom_schema_name | trim }}
        {%- endif -%}
    {%- elif custom_schema_name is none -%}
        {%- if node.resource_type in ['model', 'seed', 'snapshot'] -%}
            {{ exceptions.raise_compiler_error('Declare +schema for ' ~ node.name ~ ' in dbt_project.yml') }}
        {%- else -%}
            {{ target.schema }}
        {%- endif -%}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
'''


def project_destination(directory, payload, defaults):
    path = Path(directory) / 'dbt_project.yml'
    if not path.is_file():
        raise ValueError(f'dbt_project.yml not found in {directory}; enter its containing directory relative to the workspace')
    project = yaml.safe_load(path.read_text(encoding='utf-8-sig'))
    if not isinstance(project, dict):
        raise ValueError('dbt_project.yml must be a YAML object')
    variables = project.get('vars') or {}
    if not isinstance(variables, dict):
        raise ValueError('dbt_project.yml vars must be an object')
    if 'lakehouse_catalog' not in variables:
        return {'mode': 'legacy', 'catalog': identifier(payload.get('catalog') or defaults['default_catalog']),
                'session_schema': identifier(payload.get('schema') or defaults['default_schema'])}
    catalog = identifier(variables['lakehouse_catalog'])
    project_name = identifier(project.get('name'))
    if project.get('profile') != 'lakehouse':
        raise ValueError('Project catalog mode requires profile: lakehouse')
    if payload.get('schema') or payload.get('catalog') not in (None, '', catalog):
        raise ValueError('Catalog/schema are owned by dbt_project.yml. Clear legacy Target schema/catalog overrides in the task or dbt panel.')
    parameters = payload.get('parameters') or {}
    if not isinstance(parameters, dict):
        raise ValueError('dbt parameters must be a JSON object')
    if 'lakehouse_catalog' in parameters:
        raise ValueError('Set lakehouse_catalog in dbt_project.yml, not execution dbt vars')
    schemas = set()
    def collect(config):
        if not isinstance(config, dict):
            return
        if '+database' in config or '+catalog' in config:
            raise ValueError('dbt-spark supports one catalog per project; use vars.lakehouse_catalog, not +database/+catalog')
        if '+schema' in config:
            schemas.add(identifier(config['+schema']))
        for key, value in config.items():
            if not str(key).startswith('+'):
                collect(value)
    for resource in ('models', 'seeds', 'snapshots'):
        collect(project.get(resource, {}))
    if not schemas:
        raise ValueError('Declare at least one literal +schema under models/seeds/snapshots in dbt_project.yml')
    return {'mode': 'project', 'catalog': catalog, 'project_name': project_name,
            'session_schema': sorted(schemas)[0], 'schemas': sorted(schemas)}


def ensure_schema_macro(directory):
    """Supply exact names once, preserving every existing user macro."""
    directory = Path(directory)
    project = yaml.safe_load((directory / 'dbt_project.yml').read_text(encoding='utf-8-sig'))
    paths = project.get('macro-paths', ['macros'])
    if not isinstance(paths, list) or not paths or not all(isinstance(p, str) for p in paths):
        raise ValueError('macro-paths must be a nonempty list of workspace-relative directories')
    roots = []
    for relative in paths:
        root = (directory / relative).resolve()
        if Path(relative).is_absolute() or not root.is_relative_to(directory.resolve()):
            raise ValueError('macro-paths must stay inside the dbt project')
        roots.append(root)
        for path in root.rglob('*.sql'):
            if '.ipynb_checkpoints' in path.parts:
                continue
            if re.search(r'{%-?\s*macro\s+generate_schema_name\s*\(', path.read_text(encoding='utf-8-sig')):
                return
    roots[0].mkdir(parents=True, exist_ok=True)
    path = roots[0] / 'lakehouse_schema.sql'
    if path.exists() or path.is_symlink():
        raise ValueError('lakehouse_schema.sql already exists without generate_schema_name; choose another filename for that existing file')
    with path.open('x', encoding='utf-8') as stream:
        stream.write(SCHEMA_MACRO)


def validate_manifest(manifest, destination):
    """Reject fallback names and cross-catalog config before executing SQL."""
    for node in manifest.get('nodes', {}).values():
        if node.get('resource_type') not in ('model', 'seed', 'snapshot'):
            continue
        config = node.get('config', {})
        declared = config.get('schema')
        try:
            identifier(declared)
        except ValueError as error:
            raise ValueError(f"Declare +schema for {node.get('name')} in dbt_project.yml") from error
        if node.get('schema') != declared:
            raise ValueError(f"Schema macro must return the declared schema exactly for {node.get('name')}: expected {declared}, got {node.get('schema')}")
        if node.get('database') or config.get('database'):
            raise ValueError('Per-model database/catalog is unsupported by dbt-spark; use vars.lakehouse_catalog')
    for source in manifest.get('sources', {}).values():
        if source.get('database'):
            raise ValueError('Sources must use schemas in the project catalog; source.database is unsupported by dbt-spark')
        identifier(source.get('schema'))


def prepare_dbt_project(directory):
    ignore = directory / '.dbtignore'
    existing = ignore.read_text(encoding='utf-8-sig') if ignore.exists() else ''
    if CHECKPOINT_PATTERN in {line.strip() for line in existing.splitlines()}:
        return
    prefix = '\n' if existing and not existing.endswith('\n') else ''
    with ignore.open('a', encoding='utf-8') as stream:
        stream.write(prefix + '# Jupyter checkpoints are recovery files, not dbt resources.\n' + CHECKPOINT_PATTERN + '\n')
