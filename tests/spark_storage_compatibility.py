"""Full production Maven set and S3A CSV read against an in-memory S3 fixture.

No .env, real R2, production containers or volumes. Downloads Maven packages.
LAKEHOUSE_STORAGE_TEST_IMAGE selects a freshly built runtime image.
"""
import os
from pathlib import Path
import subprocess
import sys
import uuid


def inside():
    from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
    import threading
    from urllib.parse import unquote,urlsplit,parse_qs
    content=b'id,amount\n1,42\n'
    key='incoming/fixture.csv'
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_HEAD(self):self.reply(True)
        def do_GET(self):self.reply(False)
        def reply(self,head):
            url=urlsplit(self.path);path=unquote(url.path);query=parse_qs(url.query)
            status=200;extra={};ctype='application/xml'
            if path=='/fixture' and not head:
                prefix=query.get('prefix',[''])[0]
                item=(f'<Contents><Key>{key}</Key><LastModified>2026-11-24T00:00:00.000Z</LastModified><ETag>"fixture"</ETag><Size>{len(content)}</Size><StorageClass>STANDARD</StorageClass></Contents>' if key.startswith(prefix) else '')
                body=(f'<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/"><Name>fixture</Name><Prefix>{prefix}</Prefix><KeyCount>{int(bool(item))}</KeyCount><MaxKeys>1000</MaxKeys><IsTruncated>false</IsTruncated>{item}</ListBucketResult>').encode()
            elif path=='/fixture/'+key:
                body=content;ctype='text/csv'
                if not head and self.headers.get('Range'):
                    start,end=self.headers['Range'].split('=')[1].split('-');start=int(start);end=min(int(end) if end else len(content)-1,len(content)-1)
                    body=content[start:end+1];status=206;extra['Content-Range']=f'bytes {start}-{end}/{len(content)}'
            elif head and path=='/fixture':body=b''
            else:status=404;body=b'<Error><Code>NoSuchKey</Code><Message>Missing fixture key</Message></Error>'
            self.send_response(status)
            for name,value in {'Content-Length':str(len(body)),'Content-Type':ctype,'Last-Modified':'Tue, 24 Nov 2026 00:00:00 GMT','ETag':'"fixture"',**extra}.items():self.send_header(name,value)
            self.end_headers()
            if not head:self.wfile.write(body)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    os.environ['S3_ENDPOINT']='http://127.0.0.1:'+str(server.server_port)
    import config
    config.all_catalogs=lambda:[]
    from spark_session import create_spark
    spark=None
    try:
        spark=create_spark()
        rows=spark.read.option('header',True).csv('s3a://fixture/'+key).collect()
        assert len(rows)==1 and rows[0]['amount']=='42',rows
        assert spark.sql('SELECT :amount AS amount',args={'amount':42}).first()[0]==42
        print('PASS production Spark/Delta/UC/Hadoop AWS packages, cold-cache launch, S3A CSV read and named SQL parameter binding',flush=True)
    finally:
        if spark:spark.stop()
        server.shutdown();server.server_close()


def main():
    name='spark-storage-check-'+uuid.uuid4().hex[:10]
    root=Path(__file__).resolve().parents[1]
    image=os.getenv('LAKEHOUSE_STORAGE_TEST_IMAGE','r2-lakehouse-v3-runtime:local')
    try:
        command=['docker','run','--name',name,'--user','root','--memory','3g',
            '-v',str(root)+':/project:ro','-e','PYTHONPATH=/project/runtime']
        for value in ('SPARK_LOCAL_IP=127.0.0.1','DEFAULT_CATALOG=spark_catalog','DEFAULT_SCHEMA=default',
                      'SPARK_DRIVER_MEMORY=768m','SPARK_THREADS=1','SPARK_SHUFFLE_PARTITIONS=2',
                      'WORKSPACE_ROOT=/tmp/workspace','RUNTIME_ROOT=/tmp/runtime','RUNS_ROOT=/tmp/runs',
                      'R2_ACCOUNT_ID=fixture','R2_ACCESS_KEY_ID=fixture','R2_SECRET_ACCESS_KEY=fixture',
                      'AWS_ACCESS_KEY_ID=fixture','AWS_SECRET_ACCESS_KEY=fixture','AWS_REGION=auto','AWS_EC2_METADATA_DISABLED=true'):
            command+=['-e',value]
        subprocess.run(command+[image,'python3','/project/tests/spark_storage_compatibility.py','--inside'],check=True)
    finally:subprocess.run(['docker','rm','-f',name],capture_output=True)


if __name__=='__main__':
    inside() if '--inside' in sys.argv else main()
