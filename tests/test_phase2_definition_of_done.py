from fastapi.testclient import TestClient
from framework.api.app import app

def test_definition_of_done_developer_project_key_message_core_flow():
    client = TestClient(app)
    developer = client.post('/api/v1/developers', json={'name': 'DoD Dev', 'email': 'dod-dev@example.com'}).json()['data']
    project = client.post('/api/v1/projects', json={'owner_id': developer['id'], 'name': 'DoD Project'}).json()['data']
    key = client.post('/api/v1/api-keys', json={'developer_id': developer['id'], 'project_id': project['id'], 'permissions': ['messages.write']}).json()['data']['secret']
    response = client.post('/api/v1/messages', headers={'X-API-Key': key}, json={'project_id': project['id'], 'user_id': 'dod-user', 'channel': 'api', 'text': '/start'})
    assert response.status_code == 200
    body = response.json()
    assert body['success'] is True
    assert body['data']['intent'] == 'start'
    assert body['data']['text']
    assert body['data']['trace'][-1] == 'RESPONSE'
