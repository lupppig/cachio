# An HTTPCache pacakge  for caching user request
import hashlib
from http.client import HTTPResponse
from io import BytesIO

import diskcache as dc
from requests import PreparedRequest, Response, Session


class Cache:
    def __init__(self, f_cache: str) -> None:
        self.cache_stor = dc.Cache(f_cache)

    def get(self, cache_keys: str) -> bytes | None:
        resp = self.cache_stor.get(cache_keys)
        if not resp:
            return None
        return bytes(resp)

    def set(self, cache_keys: str, body: bytes, ttl: int = 0) -> None:
        self.cache_stor.set(cache_keys, body, ttl)

    def delete(self, cache_keys: str) -> None:
        self.cache_stor.delete(cache_keys, retry=True)

    def read_cache_resp(self, cache_keys: str) -> list[tuple[str | str]] | None:
        respBody = self.get(cache_keys=cache_keys)
        if respBody is None:
            return None

        sock = BytesIO(respBody)
        response = HTTPResponse(sock)
        return response.getheaders()


class HTTPCache(Session):
    X_FROM_CACHE: int = 0
    X_CACHE: str = "miss"

    def __init__(self, storage: Cache) -> None:
        super().__init__()

        self.storage = storage

    def _cache_keys(self, request: PreparedRequest) -> str:
        """create cache key from request url string"""
        url = f"{request.method}:{request.url}"
        return hashlib.md5(url.encode()).hexdigest()

    def _parse_cache_control(self, req: PreparedRequest): ...

    def send(self, req: PreparedRequest, **kwargs) -> Response:
        cached_key = self._cache_keys(req)
        cachable = (
            req.method == "GET" or req.method == "HEAD"
        ) and req.headers.get("range") is None

        cacheResp = self.storage.get(cached_key)

        if cachable or cacheResp:
            ...

        resp = super().send(req, **kwargs)
        return resp


if "__main__" == __name__:
    c = Cache("cache")
    cache = HTTPCache(storage=c)
    cache.get("https://example.com/index.html")
