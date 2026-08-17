from fastapi.testclient import TestClient
from framework.api.app import app


def test_health_and_ready_contract():
    client = TestClient(app)
    health = client.get('/health')
    ready = client.get('/ready')
    assert health.status_code == 200
    assert health.json()['success'] is True
    assert ready.status_code == 200
    assert ready.json()['data']['status'] == 'ready'


def test_message_api_contract():
    client = TestClient(app)
    response = client.post('/api/v1/messages', json={
        'project_id': 'demo',
        'user_id': 'user-1',
        'text': '/start',
    })
    body = response.json()
    assert response.status_code == 200
    assert body['success'] is True
    assert body['data']['intent'] == 'start'
    assert response.headers['x-request-id']


def test_telegram_is_not_required_by_core_api():
    client = TestClient(app)
    response = client.post('/api/v1/messages', json={
        'project_id': 'demo',
        'user_id': 'user-1',
        'channel': 'api',
        'text': 'رسالة غير معروفة',
    })
    assert response.status_code == 200
    assert response.json()['data']['trace'][-1] == 'RESPONSE'


def test_developer_project_api_key_flow():
    client = TestClient(app)
    developer = client.post('/api/v1/developers', json={'name': 'Dev', 'email': 'dev@example.com'}).json()['data']
    project = client.post('/api/v1/projects', json={'owner_id': developer['id'], 'name': 'Demo'}).json()['data']
    key = client.post('/api/v1/api-keys', json={'developer_id': developer['id'], 'project_id': project['id'], 'permissions': ['messages.write']}).json()['data']
    assert key['secret'].startswith('adf_')
    assert key['project_id'] == project['id']
    assert 'secret_hash' not in key


def test_telegram_webhook_pipeline_without_real_token():
    client = TestClient(app)
    response = client.post('/api/v1/webhooks/telegram/project-a', json={
        'update_id': 1,
        'message': {
            'message_id': 7,
            'text': '/start',
            'from': {'id': 9},
            'chat': {'id': 10},
        },
    })
    assert response.status_code == 200
    assert response.json()['data']['intent'] == 'start'
