"""Keep Jupyter recovery files out of dbt's resource discovery."""
CHECKPOINT_PATTERN = '**/.ipynb_checkpoints/**'


def prepare_dbt_project(directory):
    ignore = directory / '.dbtignore'
    existing = ignore.read_text(encoding='utf-8-sig') if ignore.exists() else ''
    if CHECKPOINT_PATTERN in {line.strip() for line in existing.splitlines()}:
        return
    prefix = '\n' if existing and not existing.endswith('\n') else ''
    with ignore.open('a', encoding='utf-8') as stream:
        stream.write(prefix + '# Jupyter checkpoints are recovery files, not dbt resources.\n' + CHECKPOINT_PATTERN + '\n')
