import os,sys,urllib.request
kind=sys.argv[1]
if kind=='sql':
    from pyhive import hive
    c=hive.Connection(host='127.0.0.1',port=10000,auth='NOSASL',database='default').cursor()
    c.execute('SELECT 1'); assert c.fetchone()[0]==1
else:
    port,path=(8888,'/api/status') if kind=='notebook' else (8765,'/health')
    req=urllib.request.Request(f'http://127.0.0.1:{port}{path}',headers={'Authorization':'token '+os.getenv('JUPYTER_TOKEN','')})
    urllib.request.urlopen(req,timeout=3).read()
