import asyncio
import os
from logging.config import fileConfig
from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config
from framework.infrastructure.sql import Base

config = context.config
if config.config_file_name: fileConfig(config.config_file_name)
target_metadata = Base.metadata

def get_url() -> str:
    return os.getenv('DATABASE_URL') or config.get_main_option('sqlalchemy.url')

def run_migrations_offline() -> None:
    context.configure(url=get_url(), target_metadata=target_metadata, literal_binds=True, dialect_opts={'paramstyle': 'named'})
    with context.begin_transaction(): context.run_migrations()

async def run_async_migrations() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration['sqlalchemy.url'] = get_url().replace('postgresql://', 'postgresql+asyncpg://')
    connectable = async_engine_from_config(configuration, prefix='sqlalchemy.', poolclass=pool.NullPool)
    async with connectable.connect() as connection:
        await connection.run_sync(lambda sync_conn: context.configure(connection=sync_conn, target_metadata=target_metadata))
        async with connection.begin(): await connection.run_sync(lambda sync_conn: context.run_migrations())
    await connectable.dispose()

def run_migrations_online() -> None: asyncio.run(run_async_migrations())

if context.is_offline_mode(): run_migrations_offline()
else: run_migrations_online()
