import os
c=get_config()
c.JupyterHub.bind_url='http://0.0.0.0:8888'
c.JupyterHub.db_url='sqlite:////srv/jupyterhub/hub.sqlite'
c.JupyterHub.cookie_secret_file='/srv/jupyterhub/cookie_secret'
c.ConfigurableHTTPProxy.pid_file='/srv/jupyterhub/jupyterhub-proxy.pid'
c.JupyterHub.authenticator_class='jupyterhub.auth.PAMAuthenticator'
c.Authenticator.allow_all=True
c.Authenticator.admin_users={os.getenv('HUB_ADMIN','admin')}
c.Spawner.default_url='/lab'
c.Spawner.cmd=['python3','/opt/lakehouse/start_singleuser.py']
c.Spawner.notebook_dir='/workspace'
c.Spawner.environment={k:v for k,v in os.environ.items() if k.startswith(('R2_','SPARK_','PYSPARK_')) or k in ('PYTHONPATH','UC_URL','SQL_HOST','RUNNER_URL','RUNNER_TOKEN','KESTRA_URL','KESTRA_USER','KESTRA_PASSWORD','S3_ENDPOINT','DEFAULT_CATALOG','DEFAULT_SCHEMA','TZ','RUNS_ROOT','RUNTIME_ROOT','LAKEHOUSE_SERVICE')}
# PAM users must be explicitly created by the server administrator using scripts/hub-user.sh.
