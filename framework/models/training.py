import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

@dataclass
class TrainingJob:
    project_id: str
    dataset_version: str
    provider: str
    status: str = "queued"
    metrics: dict[str, float] = field(default_factory=dict)
    artifact_uri: str | None = None
    error: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

class RasaTrainer:
    def __init__(self, executable: str = "rasa"): self.executable = executable
    async def train(self, project_id: str, dataset_version: str, config_path: str, output_dir: str) -> TrainingJob:
        job = TrainingJob(project_id, dataset_version, "rasa", status="training")
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        process = await asyncio.create_subprocess_exec(self.executable, "train", "--config", config_path, "--out", output_dir, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            job.status = "failed"; job.error = stderr.decode(errors="replace")[-4000:]
            raise RuntimeError(f"Rasa training failed: {job.error}")
        job.status = "ready"; job.artifact_uri = output_dir
        return job
