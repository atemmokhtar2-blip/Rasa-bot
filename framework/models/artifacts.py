import hashlib
import io
import zipfile
from pathlib import Path
from framework.infrastructure.object_storage import S3ObjectStorage

class ModelArtifactService:
    def __init__(self, storage: S3ObjectStorage): self.storage = storage

    async def publish_directory(self, project_id: str, job_id: str, directory: str) -> tuple[str, str]:
        root = Path(directory)
        if not root.exists() or not root.is_dir(): raise FileNotFoundError(f"Training output directory does not exist: {directory}")
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            for path in sorted(root.rglob("*")):
                if path.is_file(): bundle.write(path, path.relative_to(root).as_posix())
        body = archive.getvalue()
        digest = hashlib.sha256(body).hexdigest()
        uri = await self.storage.put(f"models/{project_id}/{job_id}.zip", body, "application/zip")
        return uri, digest
