import pytest
from framework.core.models import Entity, IntentPrediction
from framework.core.state import ContextEngine, DialogueManager, PolicyEngine, SessionManager
from framework.datasets.system import DatasetRegistry, DatasetValidator, DatasetVersion, TrainingExample
from framework.models.registry import ModelRegistry, ModelVersion
from framework.security.policy import FixedWindowRateLimiter, PermissionService

@pytest.mark.asyncio
async def test_session_context_dialogue_policy_layers():
    sessions = SessionManager()
    session = await sessions.get_or_create('p', 'u', 'c')
    intent = IntentPrediction('book_appointment', .99)
    entities = [Entity('date', '2026-08-18')]
    context = ContextEngine().build(session, intent, entities)
    assert context['current_intent'] == 'book_appointment'
    assert context['entities']['date'] == '2026-08-18'
    assert DialogueManager().next_state(session, intent, entities) == 'active'
    assert PolicyEngine().decide(intent, session, {'book_appointment'}).kind == 'action'


def test_dataset_validation_and_immutable_publish():
    example = TrainingExample('hello', 'greet')
    validator = DatasetValidator()
    assert validator.validate([example, example], {'greet'}, set()) == ['example[1] is duplicate']
    registry = DatasetRegistry()
    version = registry.publish(DatasetVersion('d1', 'v1', 'p1', (example,)))
    assert version.status == 'published'
    with pytest.raises(ValueError): registry.publish(DatasetVersion('d1', 'v1', 'p1', (example,)))


def test_model_registry_deployment_and_security_primitives():
    registry = ModelRegistry()
    registry.register(ModelVersion('m1', 'v1', 'rasa', 'd1', status='ready'))
    assert registry.deploy('p1', 'm1', 'v1').status == 'deployed'
    permissions = PermissionService()
    permissions.grant('key1', 'messages.read')
    assert permissions.check('key1', 'messages.read')
    limiter = FixedWindowRateLimiter(limit=1, window_seconds=60)
    assert limiter.allow('key1') is True
    assert limiter.allow('key1') is False
