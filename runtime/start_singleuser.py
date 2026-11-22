"""Start each Hub user's Git agent before Jupyter inherits its environment."""
import os
from pathlib import Path
import sys

from git_integration import ensure_agent

os.environ['SSH_AUTH_SOCK'] = str(Path.home() / '.ssh/lakehouse-agent.sock')
ensure_agent()
os.execvp('jupyterhub-singleuser', ['jupyterhub-singleuser', *sys.argv[1:]])
