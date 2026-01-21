import hashlib
import base64
import asyncio
from datetime import datetime
from typing import List, Any, Dict, Optional, Iterable

try:
    import aiohttp
    from aiohttp import ClientSession, ClientResponse
    from multidict import CIMultiDict
except ImportError:
    aiohttp = None # type: ignore
    ClientSession = object # type: ignore
    ClientResponse = object # type: ignore
    CIMultiDict = dict # type: ignore

from ..interfaces import AsyncCacheBackend
from ..policy import check_freshness, check_stale_if_error, parse_cache_control, FRESH, STALE

class CachedAiohttpResponse:
    """A mock-ish response object that behaves like aiohttp.ClientResponse."""
    def __init__(self, entry: Dict[str, Any], url: str, method: str):
        self.status = entry.get("status_code", 200)
        self.reason = entry.get("reason", "OK")
        self._url = url
        self.method = method
        self.headers = CIMultiDict(entry.get("headers", {}))
        self._body = base64.b64decode(entry.get("body", "")) if entry.get("body") else b""
        self._encoding = entry.get("encoding", "utf-8")
        self._timestamp = entry.get("timestamp")

    @property
    def url(self):
        return self._url

    async def read(self) -> bytes:
        return self._body

    async def json(self, **kwargs) -> Any:
        import json
        return json.loads(self._body.decode(self._encoding or "utf-8"))

    async def text(self, encoding: Optional[str] = None) -> str:
        return self._body.decode(encoding or self._encoding or "utf-8")

    def release(self):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    def get_encoding(self):
        return self._encoding

    @property
    def content(self):
        # Return an object that has a read method like a stream if possible
        class Content:
            def __init__(self, body): self.body = body
            async def read(self, n=-1): return self.body[:n] if n != -1 else self.body
        return Content(self._body)

class AiohttpCacheSession(ClientSession):
    """Subclass of aiohttp.ClientSession with caching support."""
    FRESH = FRESH
    STALE = STALE
    X_CACHE = "X-Cache"
    X_FROM_CACHE = "hits"
    X_NOT_FROM_CACHE = "miss"

    def __init__(
        self,
        backends: List[AsyncCacheBackend],
        cacheable_status_codes: Iterable[int] = (200,),
        **kwargs: Any
    ):
        if aiohttp is None:
             raise ImportError("aiohttp is required. Install `aiohttp`.")
        super().__init__(**kwargs)
        self.backends = backends
        self.cacheable_status_codes = set(cacheable_status_codes)

    def _cache_keys(self, request_url: str) -> str:
        return hashlib.md5(request_url.encode()).hexdigest()

    async def _request(self, method: str, str_or_url: Any, **kwargs: Any) -> ClientResponse:
        url = str(str_or_url)
        cachable_method = method.upper() in ("GET", "HEAD")
        headers = kwargs.get("headers", {})
        cachable = cachable_method and headers.get("range") is None
        cached_key = self._cache_keys(url)

        cache_entry: Optional[Dict[str, Any]] = None
        found_in_index = -1

        if cachable:
            for i, backend in enumerate(self.backends):
                try:
                    cache_entry = await backend.get(cached_key)
                    if cache_entry:
                        found_in_index = i
                        break
                except Exception:
                    continue

        cache_resp: Optional[CachedAiohttpResponse] = None
        if cache_entry:
            cache_resp = CachedAiohttpResponse(cache_entry, url, method)
            cache_resp.headers[self.X_CACHE] = self.X_FROM_CACHE
            
            if found_in_index > 0:
                for i in range(found_in_index):
                    try:
                        await self.backends[i].set(cached_key, cache_entry)
                    except Exception:
                        pass

        if cache_resp:
            freshness = check_freshness(dict(headers), dict(cache_resp.headers))
            if freshness == self.FRESH:
                return cache_resp # type: ignore

            etag = cache_resp.headers.get("etag")
            if etag:
                if "headers" not in kwargs: kwargs["headers"] = {}
                kwargs["headers"]["if-none-matched"] = etag
            last_modified = cache_resp.headers.get("last-modified")
            if last_modified:
                if "headers" not in kwargs: kwargs["headers"] = {}
                kwargs["headers"]["if-modified-since"] = last_modified

        resp = await super()._request(method, str_or_url, **kwargs)
        
        if resp.status == 304 and cache_resp:
            # Update cache headers
            for k, v in resp.headers.items():
                cache_resp.headers[k] = v
            entry = self._serialize_response(cache_resp) # type: ignore
            for backend in self.backends:
                try:
                    await backend.set(cached_key, entry)
                except Exception:
                    pass
            cache_resp.headers[self.X_CACHE] = self.X_FROM_CACHE
            return cache_resp # type: ignore

        if cachable and resp.status in self.cacheable_status_codes:
             resp_cc = parse_cache_control(dict(resp.headers))
             if "no-store" not in resp_cc:
                  await resp.read() # Read body to cache it
                  entry = self._serialize_response(resp)
                  for backend in self.backends:
                      try:
                         await backend.set(cached_key, entry)
                      except Exception:
                         pass
                  resp.headers[self.X_CACHE] = self.X_NOT_FROM_CACHE
        
        if resp.status != 304 and resp.status not in self.cacheable_status_codes:
             for backend in self.backends:
                 try:
                     await backend.delete(cached_key)
                 except Exception:
                     pass

        return resp

    def _serialize_response(self, resp: ClientResponse) -> Dict[str, Any]:
        return {
            "status_code": resp.status,
            "reason": resp.reason,
            "url": str(resp.url),
            "headers": dict(resp.headers),
            "body": base64.b64encode(resp._body).decode('ascii') if hasattr(resp, '_body') and resp._body else "",
            "encoding": resp.get_encoding() if hasattr(resp, 'get_encoding') else "utf-8",
            "timestamp": datetime.now().isoformat(),
        }
