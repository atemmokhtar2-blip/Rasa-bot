import hashlib
from types import SimpleNamespace
import pytest
from framework.core.models import IntentPrediction
from framework.models.comparison import ModelComparator
from framework.models.evaluation import EvaluationEngine, EvaluationResult
from framework.models.runtime import ModelRuntimeCache, ModelRuntimeService
from framework.models.thresholds import ThresholdOptimizer
from framework.nlu.policy import ConfidencePolicy


def evaluation(model_id, version, intent_f1, entity_f1, fallback):
    return EvaluationResult(model_id, version, intent_f1, entity_f1, fallback, 1.0, {"high": 1, "medium": 0, "low": 0}, 1, intent_f1, intent_f1, intent_f1, entity_f1, entity_f1, entity_f1, {}, {}, {"high": intent_f1 == 1.0})


def test_threshold_optimizer_is_deterministic_and_classifies():
    samples = [
        {"prediction": IntentPrediction("book", 0.95), "expected_intent": "book"},
        {"prediction": IntentPrediction("cancel", 0.85), "expected_intent": "book"},
        {"prediction": IntentPrediction("fallback", 0.15), "expected_intent": "cancel"},
        {"prediction": IntentPrediction("cancel", 0.45), "expected_intent": "cancel"},
    ]
    optimizer = ThresholdOptimizer(step=0.05)
    result = optimizer.optimize(samples)
    assert result.samples == 4
    assert result.accept_threshold >= result.clarification_threshold >= result.fallback_threshold
    assert ThresholdOptimizer.classify(0.99, result) == "accept"
    assert result.to_dict() == optimizer.optimize(samples).to_dict()


def test_optimized_thresholds_drive_confidence_policy():
    policy = ConfidencePolicy()
    policy.apply_optimized_thresholds({"accept_threshold": 0.9, "clarification_threshold": 0.5, "fallback_threshold": 0.2})
    assert policy.classify(0.95).status == "accept"
    assert policy.classify(0.7).status == "clarify"
    assert policy.classify(0.1).status == "fallback"


def test_evaluation_engine_can_attach_threshold_optimization():
    samples = [{"prediction": IntentPrediction("book", 0.9), "expected_intent": "book", "expected_entities": {}, "entities": []}]
    result = EvaluationEngine().evaluate("m1", "v1", samples, optimize_thresholds=True)
    assert result.optimized_thresholds is not None
    assert result.optimized_thresholds["samples"] == 1


def test_model_comparator_ranks_by_weighted_quality():
    comparator = ModelComparator()
    result = comparator.compare([evaluation("weak", "v1", .7, .8, .2), evaluation("strong", "v2", .95, .9, .05)])
    assert result.winner_model_id == "strong"
    assert result.entries[0].rank == 1


class FakeRuntimeAdapter:
    def __init__(self): self.loaded = 0; self.unloaded = 0; self.served = 0
    async def load(self, discovery): self.loaded += 1; return {"version": discovery.version}
    async def validate(self, handle, discovery): return {"status": "ready", "version": discovery.version}
    async def serve(self, handle, text, metadata): self.served += 1; return {"text": text, "intent": {"name": "ok", "confidence": 1.0}}
    async def unload(self, handle): self.unloaded += 1


@pytest.mark.asyncio
async def test_runtime_discovers_validates_caches_serves_and_unloads(tmp_path):
    artifact = tmp_path / "model.tar.gz"
    artifact.write_bytes(b"real-artifact")
    model = SimpleNamespace(id="m1", version="v1", project_id="p1", artifact_uri=str(artifact), artifact_checksum=hashlib.sha256(b"real-artifact").hexdigest(), provider="rasa")
    adapter = FakeRuntimeAdapter()
    service = ModelRuntimeService(adapter=adapter, cache=ModelRuntimeCache(max_entries=1, ttl_seconds=60))
    first = await service.load(model)
    second = await service.load(model)
    assert first.state == "ready" and second is first and adapter.loaded == 1
    served = await service.serve(model, "hello", {"project_id": "p1"})
    assert served["intent"]["name"] == "ok" and adapter.served == 1
    status = await service.status("m1")
    assert status["state"] == "ready" and status["requests"] == 1
    unloaded = await service.unload("m1")
    assert unloaded["state"] == "unloaded" and adapter.unloaded == 1


@pytest.mark.asyncio
async def test_runtime_rejects_checksum_mismatch(tmp_path):
    artifact = tmp_path / "model.tar.gz"; artifact.write_bytes(b"actual")
    model = SimpleNamespace(id="m1", version="v1", project_id="p1", artifact_uri=str(artifact), artifact_checksum="bad", provider="rasa")
    service = ModelRuntimeService(adapter=FakeRuntimeAdapter())
    with pytest.raises(Exception, match="checksum mismatch"):
        await service.load(model)
