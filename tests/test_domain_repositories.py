import pytest
from framework.infrastructure.sql import BotORM, DatasetORM, ModelORM, SQLDatabase, TrainingJobORM
from framework.infrastructure.domain_repositories import BotRepository, DatasetRepository, ModelRepository, TrainingJobRepository

@pytest.mark.asyncio
async def test_domain_repositories_persist_all_core_records(tmp_path):
    db = SQLDatabase(f'sqlite+aiosqlite:///{tmp_path / "domain.sqlite3"}')
    await db.create_schema()
    dataset = await DatasetRepository(db).save(DatasetORM(id='d1', project_id='p1', version='v1', status='validated', schema_version='1', examples=[]))
    model = await ModelRepository(db).save(ModelORM(id='m1', project_id='p1', version='v1', dataset_id=dataset.id, artifact_uri='file:///models/m1', status='ready', metrics={}))
    job = await TrainingJobRepository(db).save(TrainingJobORM(id='j1', project_id='p1', dataset_version='v1', provider='rasa', status='queued', metrics={}))
    bot = await BotRepository(db).save(BotORM(id='b1', project_id='p1', name='bot', token_secret_ref='secret://telegram', status='disabled', metadata_json={}))
    assert (await DatasetRepository(db).get(dataset.id)).version == 'v1'
    assert (await ModelRepository(db).set_status(model.id, 'deployed')).status == 'deployed'
    assert (await TrainingJobRepository(db).update(job.id, status='running')).status == 'running'
    assert (await BotRepository(db).set_status(bot.id, 'enabled')).status == 'enabled'
    await db.dispose()
