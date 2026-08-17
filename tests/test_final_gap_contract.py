import asyncio
from datetime import datetime, timezone, timedelta
from framework.models.evaluation import EvaluationEngine
from framework.core.models import Entity, IntentPrediction
from framework.observability.audit import AuditEvent, AuditLogger


def test_evaluation_engine_and_audit_export_contract():
    result = EvaluationEngine().evaluate('m1', 'v1', [{
        'prediction': IntentPrediction('greet', 0.95),
        'expected_intent': 'greet',
        'entities': [Entity('name', 'Ada')],
        'expected_entities': {'name': 'Ada'},
        'action_success': True,
    }])
    assert result.intent_accuracy == 1.0
    assert result.entity_accuracy == 1.0
    assert result.action_success_rate == 1.0

    async def scenario():
        logger = AuditLogger()
        await logger.record(AuditEvent('MODEL_EVALUATED', project_id='p1', changes={'token': 'secret', 'accuracy': 1.0}))
        exported = await logger.export_project('p1')
        assert b'MODEL_EVALUATED' in exported
        assert b'secret' not in exported
    asyncio.run(scenario())
