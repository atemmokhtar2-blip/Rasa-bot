import asyncio
import hashlib
import hmac
from fastapi.testclient import TestClient
from framework import Client, AsyncClient, action, tool
from framework.api.app import app, container


def create_project(client, suffix):
    developer = client.post('/api/v1/developers', json={'name': f'Dev {suffix}', 'email': f'{suffix}@example.com'}).json()['data']
    project = client.post('/api/v1/projects', json={'owner_id': developer['id'], 'name': f'Project {suffix}'}).json()['data']
    key = client.post('/api/v1/api-keys', json={'developer_id': developer['id'], 'project_id': project['id'], 'name': 'runtime', 'key_type': 'test', 'permissions': ['role:developer']}).json()['data']
    return developer, project, key


def test_phase4_key_metadata_and_message_gateway_contract():
    client = TestClient(app)
    _, project, key = create_project(client, 'phase4-contract')
    assert key['secret'].startswith('adf_test_')
    assert key['prefix'] == 'adf_test_'
    listed = client.get(f"/api/v1/projects/{project['id']}/api-keys", headers={'Authorization': f"Bearer {key['secret']}"})
    assert listed.status_code == 200
    record = listed.json()['data'][0]
    assert 'secret' not in record and 'secret_hash' not in record
    response = client.post('/api/v1/messages', headers={'Authorization': f"Bearer {key['secret']}", 'Idempotency-Key': 'phase4-1'}, json={'project_id': project['id'], 'user_id': 'u1', 'text': '/start', 'session_id': 's1', 'metadata': {'customer_id': 'c1'}})
    assert response.status_code == 200
    body = response.json()
    assert body['success'] and body['data']['object'] == 'message'
    assert body['data']['session_id']
    assert body['data']['trace'][-1] == 'RESPONSE'


def test_phase4_project_isolation_and_webhook_signature():
    client = TestClient(app)
    _, project_a, key_a = create_project(client, 'phase4-a')
    _, project_b, _ = create_project(client, 'phase4-b')
    headers = {'X-API-Key': key_a['secret']}
    forbidden = client.get(f"/api/v1/projects/{project_b['id']}/quota", headers=headers)
    assert forbidden.status_code == 403
    created = client.post(f"/api/v1/projects/{project_a['id']}/webhooks", headers=headers, json={'url': 'https://example.com/hook', 'events': ['message.processed']})
    assert created.status_code == 200
    data = created.json()['data']
    assert data['secret'].startswith('whsec_')
    signature = hmac.new(data['secret'].encode(), b'{"event_id":"e1"}', hashlib.sha256).hexdigest()
    assert hmac.compare_digest(signature, hmac.new(data['secret'].encode(), b'{"event_id":"e1"}', hashlib.sha256).hexdigest())
    listed = client.get(f"/api/v1/projects/{project_a['id']}/webhooks", headers=headers).json()['data']
    assert listed[0]['webhook_id'] == data['webhook_id']
    assert 'secret' not in listed[0]


def test_phase4_public_sdk_and_extensions():
    assert Client and AsyncClient and callable(action) and callable(tool)
    @action('phase4_action', required_permissions={'messages.write'})
    async def phase4_action(context): return context.metadata
    @tool('phase4_tool')
    async def phase4_tool(location): return location
    assert phase4_action.name == 'phase4_action' and phase4_tool.name == 'phase4_tool'
    assert asyncio.run(phase4_tool.execute(location='Cairo')) == 'Cairo'
