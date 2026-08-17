import json
from framework.infrastructure.object_storage import S3ObjectStorage
from framework.infrastructure.sql import DatasetORM, SQLDatabase

class DatasetArtifactService:
    def __init__(self, storage: S3ObjectStorage, database: SQLDatabase): self.storage, self.database = storage, database
    async def publish(self, dataset: DatasetORM) -> str:
        key = f"datasets/{dataset.project_id}/{dataset.version}/{dataset.id}.json"
        uri = await self.storage.put(key, json.dumps({'id': dataset.id, 'project_id': dataset.project_id, 'version': dataset.version, 'schema_version': dataset.schema_version, 'examples': dataset.examples}, default=str).encode(), 'application/json')
        async with self.database.session() as session:
            row = await session.get(DatasetORM, dataset.id)
            row.artifact_uri = uri
            row.lineage = {'dataset_id': dataset.id, 'version': dataset.version, 'artifact_key': key}
            await session.commit()
        return uri
