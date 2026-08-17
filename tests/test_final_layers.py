import pytest
from framework.security.api_keys import generate_api_key, hash_api_key
from framework.security.redaction import SensitiveDataRedactor
from framework.models.deployment import ModelDeploymentService


def test_api_key_pepper_changes_digest_and_redaction_hides_secrets():
    secret, digest = generate_api_key('pepper-a')
    assert hash_api_key(secret, 'pepper-a') == digest
    assert hash_api_key(secret, 'pepper-b') != digest
    assert SensitiveDataRedactor().redact({'token': secret, 'nested': {'password': 'x'}, 'safe': 'ok'}) == {'token': '[REDACTED]', 'nested': {'password': '[REDACTED]'}, 'safe': 'ok'}

@pytest.mark.asyncio
async def test_model_deployment_canary_and_rollback():
    class Repo:
        def __init__(self): self.status = {}
        async def set_status(self, model_id, status): self.status[model_id] = status; return type('Model', (), {'id': model_id, 'status': status})()
    repo = Repo(); service = ModelDeploymentService(repo)
    canary = await service.deploy('p1', 'm1', canary=True)
    deployed = await service.deploy('p1', 'm1', canary=False)
    rolled = await service.rollback('p1')
    assert canary.status == 'canary'
    assert deployed.status == 'deployed'
    assert rolled.status == 'rolled_back'
    assert repo.status['m1'] == 'rolled_back'
