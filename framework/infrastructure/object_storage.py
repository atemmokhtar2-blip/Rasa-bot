import asyncio
from dataclasses import dataclass
from typing import BinaryIO
import boto3

@dataclass
class ObjectStorageSettings:
    endpoint_url: str | None
    bucket: str
    region: str = "us-east-1"
    access_key: str | None = None
    secret_key: str | None = None

class S3ObjectStorage:
    def __init__(self, settings: ObjectStorageSettings):
        if not settings.bucket: raise ValueError("S3 bucket is required")
        self.settings = settings
        self.client = boto3.client("s3", endpoint_url=settings.endpoint_url, region_name=settings.region, aws_access_key_id=settings.access_key, aws_secret_access_key=settings.secret_key)
    async def put(self, key: str, body: bytes, content_type: str = "application/octet-stream") -> str:
        await asyncio.to_thread(self.client.put_object, Bucket=self.settings.bucket, Key=key, Body=body, ContentType=content_type)
        return f"s3://{self.settings.bucket}/{key}"
    async def get(self, key: str) -> bytes:
        response = await asyncio.to_thread(self.client.get_object, Bucket=self.settings.bucket, Key=key)
        return await asyncio.to_thread(response["Body"].read)
    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self.client.delete_object, Bucket=self.settings.bucket, Key=key)
