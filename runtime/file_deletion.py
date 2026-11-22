"""Bounded deletes for uploaded R2 objects; table storage stays read-only."""


def delete_target(data):
    if not isinstance(data, dict):
        raise ValueError('Expected a deletion request')
    key, kind = data.get('key'), data.get('kind')
    if (not isinstance(key, str) or not key.startswith('incoming/') or key == 'incoming/'
            or '\\' in key or any(ord(c) < 32 for c in key)
            or any(part in ('.', '..', '') for part in key.rstrip('/').split('/'))
            or len(key.encode('utf-8')) > 1024):
        raise ValueError('Only files and subfolders inside incoming/ can be deleted')
    if kind not in ('file', 'folder') or (kind == 'folder') != key.endswith('/'):
        raise ValueError('Folders must end with /; files must use an exact object key')
    if data.get('confirmation') != key:
        raise ValueError('Confirm the exact file or folder path before deleting')
    return key, kind


def delete_batch(client, bucket, data):
    key, kind = delete_target(data)
    # Pending uploads are not objects yet. Refuse the delete rather than leave an
    # upload able to recreate a just-deleted path when it completes or resumes.
    uploads = client.get_paginator('list_multipart_uploads')
    for page in uploads.paginate(Bucket=bucket, Prefix=key):
        if any(kind == 'folder' or upload['Key'] == key for upload in page.get('Uploads', [])):
            raise ValueError('Finish or cancel active uploads at this path before deleting')
    if kind == 'folder':
        page = client.list_objects_v2(Bucket=bucket, Prefix=key, MaxKeys=1000)
        keys = [item['Key'] for item in page.get('Contents', [])]
    else:
        keys = [key]
    if not keys:
        return {'deleted': 0, 'has_more': False, 'errors': []}
    # Do not trust a listing to broaden the requested target, even on a faulty
    # S3-compatible backend. Validate the entire batch before any mutation.
    if any(not item.startswith(key) if kind == 'folder' else item != key for item in keys):
        raise ValueError('Storage returned an object outside the selected path')
    response = client.delete_objects(Bucket=bucket, Delete={
        'Objects': [{'Key': item} for item in keys], 'Quiet': False})
    deleted = {item['Key'] for item in response.get('Deleted', []) if item.get('Key') in keys}
    errors = [{'key': item.get('Key', ''), 'code': item.get('Code', 'DeleteFailed'),
               'message': item.get('Message', 'Object was not deleted')}
              for item in response.get('Errors', [])]
    reported = deleted | {item['key'] for item in errors}
    errors += [{'key': item, 'code': 'Unconfirmed', 'message': 'Storage did not confirm deletion'}
               for item in keys if item not in reported]
    # Always list from the beginning of the remaining prefix. Deleting while
    # advancing an old continuation token can skip objects on some backends.
    more = bool(client.list_objects_v2(Bucket=bucket, Prefix=key, MaxKeys=1).get('Contents')) \
        if kind == 'folder' and not errors else bool(errors)
    return {'deleted': len(deleted), 'has_more': more, 'errors': errors}
