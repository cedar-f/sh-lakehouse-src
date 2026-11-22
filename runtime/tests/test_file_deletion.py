import pytest

from file_deletion import delete_batch


class Store:
    def __init__(self, keys=(), uploads=(), failures=()):
        self.objects = set(keys)
        self.uploads = uploads
        self.failures = set(failures)
        self.requests = []
        self.batches = []

    def get_paginator(self, name):
        assert name == 'list_multipart_uploads'
        return self

    def paginate(self, **args):
        self.requests.append(args)
        matches = [{'Key': key} for key in self.uploads if key.startswith(args['Prefix'])]
        yield {'Uploads': []}
        yield {'Uploads': matches}

    def list_objects_v2(self, **args):
        assert 'ContinuationToken' not in args and 'Delimiter' not in args
        self.requests.append(args)
        return {'Contents': [{'Key': key} for key in sorted(self.objects)
                             if key.startswith(args['Prefix'])][:args['MaxKeys']]}

    def delete_objects(self, **args):
        assert args['Delete']['Quiet'] is False
        keys = [item['Key'] for item in args['Delete']['Objects']]
        self.batches.append(keys)
        deleted = [key for key in keys if key not in self.failures]
        self.objects.difference_update(deleted)
        return {'Deleted': [{'Key': key} for key in deleted],
                'Errors': [{'Key': key, 'Code': 'AccessDenied', 'Message': 'Object is locked'}
                           for key in keys if key in self.failures]}


def request(key, kind='file'):
    return {'key': key, 'kind': kind, 'confirmation': key}


@pytest.mark.parametrize('key,kind', [('', 'folder'), ('incoming/', 'folder'),
    ('warehouse/table/data.parquet', 'file'), ('platform-backups/v3/', 'folder'),
    ('/incoming/a', 'file'), ('incoming/../warehouse/x', 'file'),
    ('incoming/./x', 'file'), ('incoming//x', 'file'), ('incoming/a\\b', 'file'),
    ('incoming/a\x00b', 'file'), ('incoming/folder', 'folder'),
    ('incoming/folder/', 'file'), ('incoming/' + 'é' * 600, 'file')])
def test_invalid_and_protected_paths_never_touch_storage(key, kind):
    client = Store()
    with pytest.raises(ValueError):
        delete_batch(client, 'bucket', request(key, kind))
    assert not client.requests and not client.batches


def test_exact_confirmation_is_required():
    client = Store()
    with pytest.raises(ValueError, match='Confirm'):
        delete_batch(client, 'bucket', {'key': 'incoming/file.csv', 'kind': 'file'})
    assert not client.requests


def test_file_delete_is_exact_and_handles_unicode():
    key = 'incoming/dữ liệu & +%.csv'
    client = Store([key, key + '.bak', 'warehouse/protected'])
    result = delete_batch(client, 'bucket', request(key))
    assert result == {'deleted': 1, 'has_more': False, 'errors': []}
    assert client.objects == {key + '.bak', 'warehouse/protected'}


def test_recursive_deletion_is_bounded_and_preserves_sibling_prefixes():
    target = 'incoming/data/'
    client = Store([target] + [target + 'nested/' + str(i) for i in range(2004)]
                   + ['incoming/database/keep.csv', 'incoming/data', 'warehouse/keep'])
    counts = []
    while True:
        result = delete_batch(client, 'bucket', request(target, 'folder'))
        counts.append(result['deleted'])
        if not result['has_more']:
            break
    assert counts == [1000, 1000, 5]
    assert all(len(batch) <= 1000 for batch in client.batches)
    assert client.objects == {'incoming/database/keep.csv', 'incoming/data', 'warehouse/keep'}


def test_partial_failure_reports_successes_and_remaining_errors():
    client = Store(['incoming/x/a', 'incoming/x/b'], failures=['incoming/x/b'])
    result = delete_batch(client, 'bucket', request('incoming/x/', 'folder'))
    assert result['deleted'] == 1 and result['has_more'] is True
    assert result['errors'] == [{'key': 'incoming/x/b', 'code': 'AccessDenied', 'message': 'Object is locked'}]
    assert client.objects == {'incoming/x/b'}


def test_active_multipart_upload_on_later_page_blocks_folder_deletion():
    client = Store(['incoming/x/a'], uploads=['incoming/x/pending'])
    with pytest.raises(ValueError, match='Finish or cancel'):
        delete_batch(client, 'bucket', request('incoming/x/', 'folder'))
    assert not client.batches and client.objects == {'incoming/x/a'}


def test_upload_of_different_file_with_same_prefix_does_not_block_file_delete():
    client = Store(['incoming/a'], uploads=['incoming/a-other'])
    assert delete_batch(client, 'bucket', request('incoming/a'))['deleted'] == 1
    with pytest.raises(ValueError, match='Finish or cancel'):
        delete_batch(Store(uploads=['incoming/a']), 'bucket', request('incoming/a'))


def test_empty_folder_is_already_complete():
    client = Store()
    assert delete_batch(client, 'bucket', request('incoming/empty/', 'folder')) == {
        'deleted': 0, 'has_more': False, 'errors': []}
    assert not client.batches


def test_unconfirmed_response_is_not_reported_as_success():
    client = Store(['incoming/file'])
    client.delete_objects = lambda **args: {}
    result = delete_batch(client, 'bucket', request('incoming/file'))
    assert result['deleted'] == 0 and result['errors'][0]['code'] == 'Unconfirmed'


def test_invalid_storage_listing_cannot_delete_a_sibling():
    client = Store(['incoming/x/a'])
    client.list_objects_v2 = lambda **args: {'Contents': [{'Key': 'incoming/xy/keep'}]}
    with pytest.raises(ValueError, match='outside'):
        delete_batch(client, 'bucket', request('incoming/x/', 'folder'))
    assert not client.batches
