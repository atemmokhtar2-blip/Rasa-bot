from uuid import uuid4
from fastapi.testclient import TestClient
from framework.api.app import app

def test_developer_role_expands_to_project_permissions():
    client = TestClient(app)
    suffix = uuid4().hex
    developer = client.post('/api/v1/developers', json={'name': f'RBAC-{suffix}', 'email': f'rbac-{suffix}@example.com'}).json()['data']
    project = client.post('/api/v1/projects', json={'owner_id': developer['id'], 'name': f'RBAC Project-{suffix}'}).json()['data']
    secret = client.post('/api/v1/api-keys', json={'developer_id': developer['id'], 'project_id': project['id'], 'permissions': ['role:developer']}).json()['data']['secret']
    response = client.get(f"/api/v1/projects/{project['id']}", headers={'X-API-Key': secret})
    assert response.status_code == 200
    assert response.json()['data']['id'] == project['id']
