import pytest
from types import SimpleNamespace
from framework.workers.training import TrainingJobWorker

class Queue:
    def __init__(self, payload): self.payload = payload
    async def consume(self, *_args, **_kwargs):
        if self.payload is None: return None
        payload, self.payload = self.payload, None
        return {"payload": payload}

class Jobs:
    def __init__(self): self.rows = {"job-1": SimpleNamespace(id="job-1", cancel_requested=False, status="queued")}
    async def get(self, job_id): return self.rows.get(job_id)
    async def update(self, job_id, **values):
        for key, value in values.items(): setattr(self.rows[job_id], key, value)
        return self.rows[job_id]

class Models:
    def __init__(self): self.rows = {}
    async def save(self, row): self.rows[row.id] = row; return row
    async def update_fields(self, model_id, **values):
        for key, value in values.items(): setattr(self.rows[model_id], key, value)
        return self.rows[model_id]

class Trainer:
    async def train(self, *_args): return SimpleNamespace(status="ready", artifact_uri="/tmp/rasa-model", metrics={"loss": 0.1}, logs=[], metadata={})

@pytest.mark.asyncio
async def test_phase3_training_e2e_marks_model_ready_after_quality_gate():
    payload = {"job_id": "job-1", "project_id": "project-1", "dataset_version": "dataset-v1", "provider": "rasa", "config_path": "config.yml", "output_dir": "/tmp/models", "training_config": {}, "evaluation_samples": [{"expected_intent": "greet", "predicted_intent": "greet", "confidence": 0.99, "expected_entities": {}, "entities": [], "action_success": True}], "quality_gate": {"min_intent_f1": 0.9, "min_entity_f1": 0.9, "max_fallback_rate": 0.1}}
    jobs, models = Jobs(), Models()
    worker = TrainingJobWorker(Queue(payload), jobs, Trainer(), models)
    assert await worker.run_once() is True
    assert jobs.rows["job-1"].status == "completed"
    assert models.rows["job-1"].status == "ready"
    assert models.rows["job-1"].evaluation_report["quality_gate"]["passed"] is True

@pytest.mark.asyncio
async def test_phase3_training_e2e_rejects_ready_without_evaluation_data():
    payload = {"job_id": "job-1", "project_id": "project-1", "dataset_version": "dataset-v1", "provider": "rasa", "config_path": "config.yml", "output_dir": "/tmp/models", "training_config": {}, "evaluation_samples": []}
    jobs, models = Jobs(), Models()
    worker = TrainingJobWorker(Queue(payload), jobs, Trainer(), models)
    assert await worker.run_once() is True
    assert models.rows["job-1"].status == "failed"
    assert "evaluation_data_missing" in models.rows["job-1"].evaluation_report["quality_gate"]["failures"]
