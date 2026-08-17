import pytest
from framework.infrastructure.sql import ProjectORM, SQLDatabase, SQLProjectRepository

@pytest.mark.asyncio
async def test_sql_repository_persists_project_on_real_sql_engine(tmp_path):
    database = SQLDatabase(f'sqlite+aiosqlite:///{tmp_path / "framework.sqlite3"}')
    await database.create_schema()
    repository = SQLProjectRepository(database)
    project = ProjectORM(id='sql-project-1', owner_id='developer-1', name='SQL Project', environment='development', status='active', configuration={})
    await repository.create(project)
    loaded = await repository.get(project.id)
    assert loaded is not None
    assert loaded.name == 'SQL Project'
    await database.dispose()
