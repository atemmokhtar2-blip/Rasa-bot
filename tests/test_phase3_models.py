import pytest
from framework.models.evaluation import EvaluationEngine, QualityGate
from framework.models.registry import ModelRegistry, ModelVersion
from framework.core.models import IntentPrediction

def samples(): return [{'prediction': IntentPrediction('greet', .95), 'expected_intent': 'greet', 'expected_entities': {}, 'entities': [], 'action_success': True}, {'prediction': IntentPrediction('cancel_order', .9), 'expected_intent': 'cancel_order', 'expected_entities': {}, 'entities': [], 'action_success': True}, {'prediction': IntentPrediction('fallback', .3), 'expected_intent': 'unknown', 'expected_entities': {}, 'entities': [], 'action_success': True}]

def test_evaluation_metrics_and_quality_gate():
    result = EvaluationEngine().evaluate('m1', 'v1', samples(), hard_set=True)
    assert result.intent_f1 > 0 and result.per_intent['greet']['f1'] == 1
    assert result.confusion_matrix['unknown']['fallback'] == 1
    passed, failures = QualityGate(min_intent_f1=.5, require_artifact=True).check(result, 's3://artifact')
    assert passed and not failures

def test_model_registry_environment_deploy_and_rollback():
    registry = ModelRegistry()
    first = registry.register(ModelVersion('m1', 'v1', 'rasa', 'd1', status='ready', artifact_uri='a1', project_id='p1'))
    second = registry.register(ModelVersion('m1', 'v2', 'rasa', 'd2', status='ready', artifact_uri='a2', project_id='p1'))
    registry.deploy('p1', 'm1', 'v1', 'staging'); registry.deploy('p1', 'm1', 'v2', 'staging')
    assert registry.active('p1', 'staging') == 'v2'
    assert registry.rollback('p1', 'staging').version == 'v1'
    assert registry.active('p1', 'staging') == 'v1'
    with pytest.raises(ValueError): registry.deploy('p2', 'm1', 'v1', 'production')
