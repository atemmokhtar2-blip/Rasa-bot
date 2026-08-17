from uuid import uuid4
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
from framework.api.app import app


def test_project_management_and_usage_contract():
    client = TestClient(app)
    suffix = uuid4().hex
    developer = client.post('/api/v1/developers', json={'name': f'Dev-{suffix}', 'email': f'{suffix}@example.com'}).json()['data']
    project = client.post('/api/v1/projects', json={'owner_id': developer['id'], 'name': f'Project-{suffix}'}).json()['data']

    admin_key = client.post('/api/v1/api-keys', json={'developer_id': developer['id'], 'project_id': project['id'], 'permissions': ['*']}).json()['data']['secret']
    headers = {'X-API-Key': admin_key}
    listed = client.get('/api/v1/projects', headers=headers).json()
    assert any(row['id'] == project['id'] for row in listed['data'])

    updated = client.patch(f"/api/v1/projects/{project['id']}", headers=headers, json={'description': 'production project', 'status': 'active'})
    assert updated.status_code == 200
    assert updated.json()['data']['description'] == 'production project'

    usage = client.get(f"/api/v1/projects/{project['id']}/usage", headers=headers)
    assert usage.status_code == 200
    assert usage.json()['data']['totals'] == {}


def test_expired_api_key_is_rejected():
    from framework.api.app import container
    suffix = uuid4().hex
    import asyncio
    async def scenario():
        developer = await container.developers.create_developer(f'Expiry-{suffix}', f'expiry-{suffix}@example.com')
        project = await container.developers.create_project(developer.id, f'ExpiryProject-{suffix}')
        created = await container.developers.create_api_key(developer.id, project.id, 'development', {'messages.write'})
        container.developers.api_keys[created.key_id].expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        try:
            await container.developers.authenticate(created.secret)
        except Exception as exc:
            assert getattr(exc, 'code', None) == 'INVALID_API_KEY'
        else:
            raise AssertionError('expired API key was accepted')
    asyncio.run(scenario())


def test_api_key_management_contract():
    client = TestClient(app)
    suffix = uuid4().hex
    developer = client.post('/api/v1/developers', json={'name': f'KeyDev-{suffix}', 'email': f'key-{suffix}@example.com'}).json()['data']
    project = client.post('/api/v1/projects', json={'owner_id': developer['id'], 'name': f'KeyProject-{suffix}'}).json()['data']
    key = client.post('/api/v1/api-keys', json={'developer_id': developer['id'], 'project_id': project['id'], 'permissions': ['keys.read', 'keys.write']}).json()['data']

    listed = client.get(f"/api/v1/projects/{project['id']}/api-keys", headers={'X-API-Key': key['secret']})
    assert listed.status_code == 200
    assert listed.json()['data'][0]['key_id'] == key['key_id']

    rotated = client.post(f"/api/v1/api-keys/{key['key_id']}/rotate", headers={'X-API-Key': key['secret']})
    assert rotated.status_code == 200
    assert rotated.json()['data']['secret'].startswith('adf_')
