from datetime import datetime, timezone
from botocore.exceptions import ClientError
import pytest

from file_metadata import list_files, object_detail


class Storage:
    def __init__(self):self.calls=[];self.missing=False;self.denied=False
    def list_objects_v2(self,**args):
        self.calls.append(args)
        return {'Contents':[{'Key':'incoming/a.csv','Size':25,'LastModified':datetime(2026,11,24,tzinfo=timezone.utc),'ETag':'"opaque-2"'}],
                'CommonPrefixes':[{'Prefix':'incoming/nested/'}],'NextContinuationToken':'next'}
    def head_object(self,**args):
        self.calls.append(args)
        if self.missing or self.denied:
            raise ClientError({'Error':{'Code':'403' if self.denied else '404'}},'HeadObject')
        return {'ContentLength':25,'LastModified':datetime(2026,11,24,tzinfo=timezone.utc),'ETag':'"opaque-2"','ContentType':'text/csv','Metadata':{'source':'upload'}}


def test_listing_keeps_pagination_without_head_per_file():
    client=Storage();value=list_files(client,'fixture','incoming/','cursor')
    assert len(client.calls)==1 and client.calls[0]['ContinuationToken']=='cursor'
    assert value['next_page_token']=='next' and value['folders']==['incoming/nested/']
    file=value['files'][0]
    assert file['updated_at']=='2026-11-24T00:00:00+00:00'
    assert file['created_at'] is None and file['object_id']=='fixture/incoming/a.csv'
    assert file['spark_path']=='s3a://fixture/incoming/a.csv' and file['etag']=='opaque-2'


def test_detail_distinguishes_virtual_prefix_from_marker_and_file():
    client=Storage();file=object_detail(client,'fixture','incoming/a.csv','file')
    assert not file['virtual'] and file['content_type']=='text/csv'
    assert file['created_at'] is None and file['metadata']=={'source':'upload'}
    client.missing=True
    assert object_detail(client,'fixture','incoming/virtual/','folder')['virtual']
    with pytest.raises(ClientError):object_detail(client,'fixture','incoming/missing.csv','file')
    client.denied=True
    with pytest.raises(ClientError):object_detail(client,'fixture','incoming/private/','folder')


@pytest.mark.parametrize('key',['../secret','/absolute','incoming/../key','incoming\\key','bad\x00key'])
def test_metadata_rejects_invalid_keys(key):
    with pytest.raises(ValueError):object_detail(Storage(),'fixture',key,'file')
