import hashlib
import base64
import asyncio
from datetime import datetime
from typing import List, Any, Dict, Optional

try:
    import aiohttp
    from aiohttp import ClientSession, ClientResponse
except ImportError:
    aiohttp = None # type: ignore

from ..interfaces import AsyncCacheBackend
from ..policy import check_freshness, check_stale_if_error, parse_cache_control, FRESH, STALE

class AiohttpCacheSession(ClientSession):
    """Subclass of aiohttp.ClientSession with caching support."""
    FRESH = FRESH
    STALE = STALE
    X_CACHE = "X-Cache"
    X_FROM_CACHE = "hits"
    X_NOT_FROM_CACHE = "miss"

    def __init__(self, backends: List[AsyncCacheBackend], **kwargs: Any):
        if aiohttp is None:
             raise ImportError("aiohttp is required. Install `aiohttp`.")
        super().__init__(**kwargs)
        self.backends = backends

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
                cache_entry = await backend.get(cached_key)
                if cache_entry:
                    found_in_index = i
                    break

        cache_resp: Optional[ClientResponse] = None
        if cache_entry:
            pass

        resp = await super()._request(method, str_or_url, **kwargs)
        
        if cachable and resp.status == 200:
             resp_cc = parse_cache_control(dict(resp.headers))
             if "no-store" not in resp_cc:
                 await resp.read() # Read body to cache it
                 entry = self._serialize_response(resp)
                 for backend in self.backends:
                     await backend.set(cached_key, entry)
        
        return resp

    def _serialize_response(self, resp: ClientResponse) -> Dict[str, Any]:
        return {
            "status_code": resp.status,
            "reason": resp.reason,
            "url": str(resp.url),
            "headers": dict(resp.headers),
            "body": base64.b64encode(resp._body).decode('ascii') if resp._body else "",
            "encoding": resp.get_encoding(),
            "timestamp": datetime.now().isoformat(),
        }
