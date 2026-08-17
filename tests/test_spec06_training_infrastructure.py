import asyncio
from pathlib import Path
from framework.datasets.pipeline import DatasetPipeline, DatasetSplit
from framework.datasets.system import TrainingExample
from framework.training import LocalArtifactStore, TrainingQueue, TrainingQueueItem, ModelRouter, ConfigurableQualityGate, DeploymentManager


def test_dataset_statistics_leakage_and_deterministic_split():
    examples = [TrainingExample("hello", "greet", conversation_id="c1"), TrainingExample("bye", "goodbye", conversation_id="c2"), TrainingExample("hello", "greet", conversation_id="c3")]
    pipeline = DatasetPipeline()
    report = pipeline.quality(examples, {"greet", "goodbye"}, set())
    assert "minimum_text_length" in report.statistics and "class_imbalance_ratio" in report.statistics
    first = pipeline.split(examples, seed=42); second = pipeline.split(examples, seed=42)
    assert first == second
    assert pipeline.leakage(DatasetSplit((examples[0],), (examples[0],), ()))['has_leakage'] is True


def test_local_artifact_store_checksum(tmp_path):
    source = tmp_path / "source"; source.mkdir(); (source / "model.bin").write_bytes(b"model")
    async def scenario():
        store = LocalArtifactStore(tmp_path / "artifacts")
        uri, checksum = await store.put_directory("p1", "a1", source)
        assert await store.exists(uri) and checksum == await store.checksum(uri)
    asyncio.run(scenario())


def test_training_queue_is_idempotent():
    async def scenario():
        queue = TrainingQueue(); item = TrainingQueueItem("j1", "p1", {})
        assert await queue.enqueue(item) is True and await queue.enqueue(item) is False and queue.size() == 1
    asyncio.run(scenario())


def test_router_quality_gate_and_deployment_rollback(tmp_path):
    class Store(LocalArtifactStore): pass
    async def scenario():
        store = Store(tmp_path / "artifacts"); source = tmp_path / "s"; source.mkdir(); (source / "m").write_text("v")
        uri1, _ = await store.put_directory("p", "a1", source); uri2, _ = await store.put_directory("p", "a2", source)
        gate = ConfigurableQualityGate({"f1": 0.8}); assert gate.evaluate({"f1": 0.9}).passed and not gate.evaluate({"f1": 0.7}).passed
        router = ModelRouter(); deployments = DeploymentManager(router, store)
        first = await deployments.deploy("p", "m", "v1", uri1); second = await deployments.deploy("p", "m", "v2", uri2)
        assert router.resolve("p", "production", "production") == ("m", "v2")
        rollback = await deployments.rollback("p")
        assert rollback["rolled_back_to"] == ("m", "v1")
    asyncio.run(scenario())
