import os
import pytest
from framework.infrastructure.redis import RedisProvider
from framework.infrastructure.sql import SQLDatabase

pytestmark = pytest.mark.integration

@pytest.mark.asyncio
async def test_real_redis_provider():
    url = os.getenv('TEST_REDIS_URL')
    if not url: pytest.skip('TEST_REDIS_URL is not configured')
    redis = RedisProvider(url)
    key = 'framework:integration:test'
    try:
        assert await redis.ping()
        await redis.set(key, 'ok', 30)
        assert await redis.get(key) == 'ok'
        assert await redis.incr_with_expiry(key + ':counter', 30) == 1
    finally:
        await redis.delete(key)
        await redis.close()

@pytest.mark.asyncio
async def test_real_postgres_schema_and_query():
    url = os.getenv('TEST_DATABASE_URL')
    if not url: pytest.skip('TEST_DATABASE_URL is not configured')
    database = SQLDatabase(url)
    try:
        assert await database.ping()
        await database.create_schema()
        assert await database.ping()
    finally:
        await database.dispose()
