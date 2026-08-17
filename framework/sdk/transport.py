from __future__ import annotations
import os
import time
import httpx
from framework.sdk.exceptions import APIError, AuthenticationError, PermissionError, NotFoundError, RateLimitError, TransportError, ValidationError
from framework.sdk.types import Response

class Transport:
    def __init__(self, api_key: str | None = None, base_url: str | None = None, timeout: float = 30.0):
        self.api_key = api_key or os.getenv("FRAMEWORK_API_KEY")
        self.base_url = (base_url or os.getenv("FRAMEWORK_BASE_URL") or "http://127.0.0.1:8000").rstrip("/")
        self.timeout = timeout
        self._client = httpx.Client(timeout=timeout)
    def _headers(self, idempotency_key: str | None = None) -> dict[str, str]:
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if self.api_key: headers["Authorization"] = f"Bearer {self.api_key}"
        if idempotency_key: headers["Idempotency-Key"] = idempotency_key
        return headers
    @staticmethod
    def _error(response: httpx.Response) -> Exception:
        try:
            body = response.json(); error = body.get("error") or {}
        except Exception:
            body, error = {}, {}
        kind = {401: AuthenticationError, 403: PermissionError, 404: NotFoundError, 422: ValidationError, 429: RateLimitError}.get(response.status_code, APIError)
        return kind(error.get("message") or response.text or "API request failed", status_code=response.status_code, code=error.get("code"), request_id=body.get("request_id"), details=error.get("details") or {})
    def request(self, method: str, path: str, *, json: dict | None = None, idempotency_key: str | None = None, retries: int = 2) -> Response:
        safe = method.upper() in {"GET", "HEAD", "OPTIONS"} or bool(idempotency_key); last = None
        for attempt in range(retries + 1 if safe else 1):
            try:
                response = self._client.request(method, self.base_url + path, json=json, headers=self._headers(idempotency_key))
                if response.status_code >= 400: raise self._error(response)
                body = response.json(); return Response(body.get("data"), body.get("success", True), body.get("request_id") or response.headers.get("X-Request-ID"), body.get("error"))
            except APIError: raise
            except Exception as exc:
                last = exc
                if attempt < retries: time.sleep(0.2 * (2 ** attempt)); continue
                raise TransportError(str(last)) from last
        raise TransportError(str(last))
    def close(self) -> None: self._client.close()

class AsyncTransport(Transport):
    def __init__(self, api_key: str | None = None, base_url: str | None = None, timeout: float = 30.0):
        super().__init__(api_key, base_url, timeout); self._client.close(); self._async_client = httpx.AsyncClient(timeout=timeout)
    async def request(self, method: str, path: str, *, json: dict | None = None, idempotency_key: str | None = None, retries: int = 2) -> Response:
        safe = method.upper() in {"GET", "HEAD", "OPTIONS"} or bool(idempotency_key); last = None
        for attempt in range(retries + 1 if safe else 1):
            try:
                response = await self._async_client.request(method, self.base_url + path, json=json, headers=self._headers(idempotency_key))
                if response.status_code >= 400: raise self._error(response)
                body = response.json(); return Response(body.get("data"), body.get("success", True), body.get("request_id") or response.headers.get("X-Request-ID"), body.get("error"))
            except APIError: raise
            except Exception as exc:
                last = exc
                if attempt < retries:
                    import asyncio; await asyncio.sleep(0.2 * (2 ** attempt)); continue
                raise TransportError(str(last)) from last
        raise TransportError(str(last))
    async def aclose(self) -> None:
        await self._async_client.aclose()
