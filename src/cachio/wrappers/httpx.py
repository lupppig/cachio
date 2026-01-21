import hashlib
import base64

from datetime import datetime
from typing import List, Any, Dict, Optional, Iterable

try:
    import httpx
except ImportError:
    httpx = None

from ..interfaces import AsyncCacheBackend
from ..policy import check_freshness, check_stale_if_error, parse_cache_control, FRESH, STALE

class HttpxCacheClient:
    """Wrapper for httpx.AsyncClient with caching support."""
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
        if httpx is None:
            raise ImportError("httpx is required. Install `httpx`.")
        self.client = httpx.AsyncClient(**kwargs)
        self.backends = backends
        self.cacheable_status_codes = set(cacheable_status_codes)

    async def __aenter__(self):
        await self.client.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        await self.client.__aexit__(exc_type, exc_value, traceback)

    async def aclose(self):
        """Close the client."""
        await self.client.aclose()

    def _cache_keys(self, request_url: str) -> str:
        return hashlib.md5(request_url.encode()).hexdigest()

    async def get(self, url: str, **kwargs: Any) -> httpx.Response:
        """Send a GET request."""
        return await self.request("GET", url, **kwargs)

    async def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        """Send a request with caching."""
        req = self.client.build_request(method, url, **kwargs)
        
        cachable_method = method in ("GET", "HEAD")
        cachable = cachable_method and req.headers.get("range") is None
        cached_key = self._cache_keys(str(req.url))

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
                    # Log error or silence it. Proceed to next backend.
                    continue

        cache_resp: Optional[httpx.Response] = None
        if cache_entry:
            cache_resp = self._build_response(cache_entry, req)
            cache_resp.headers[self.X_CACHE] = self.X_FROM_CACHE
            
            if found_in_index > 0:
                for i in range(found_in_index):
                    try:
                        await self.backends[i].set(cached_key, cache_entry)
                    except Exception:
                        pass

        if cache_resp:
            freshness = check_freshness(dict(req.headers), dict(cache_resp.headers))
            if freshness == self.FRESH:
                return cache_resp
            
            # Revalidation
            etag = cache_resp.headers.get("etag")
            if etag:
                req.headers["if-none-matched"] = etag
            last_modified = cache_resp.headers.get("last-modified")
            if last_modified:
                req.headers["if-modified-since"] = last_modified

        # Network Request
        try:
            resp = await self.client.send(req)
        except Exception:
             # Stale if error check ?
             if cache_resp and check_stale_if_error(dict(cache_resp.headers)):
                 cache_resp.headers["Stale-Warning"] = '110 - "Response is stale"'
                 return cache_resp
             raise

        if resp.status_code == 304 and cache_resp:
            # Update cache
            for k, v in resp.headers.items():
                cache_resp.headers[k] = v
            new_entry = self._serialize_response(cache_resp)
            for backend in self.backends:
                try:
                    await backend.set(cached_key, new_entry)
                except Exception:
                    pass
            cache_resp.headers[self.X_CACHE] = self.X_FROM_CACHE 
            return cache_resp
            
        if resp.status_code >= 500 and cache_resp and check_stale_if_error(dict(cache_resp.headers)):
             cache_resp.headers["Stale-Warning"] = '110 - "Response is stale"'
             return cache_resp

        if cachable and resp.status_code in self.cacheable_status_codes:
             resp_cc = parse_cache_control(dict(resp.headers))
             if "no-store" not in resp_cc:
                 resp.headers[self.X_CACHE] = self.X_NOT_FROM_CACHE
                 await resp.aread() # Ensure content is read
                 entry = self._serialize_response(resp)
                 for backend in self.backends:
                     try:
                         await backend.set(cached_key, entry)
                     except Exception:
                         pass
        
        if resp.status_code != 304 and resp.status_code not in self.cacheable_status_codes:
             for backend in self.backends:
                 try:
                     await backend.delete(cached_key)
                 except Exception:
                     pass

        return resp

    def _serialize_response(self, resp: httpx.Response) -> Dict[str, Any]:
        return {
            "status_code": resp.status_code,
            "reason": resp.reason_phrase,
            "url": str(resp.url),
            "headers": dict(resp.headers),
            "body": base64.b64encode(resp.content).decode('ascii'),
            "encoding": resp.encoding,
            "timestamp": datetime.now().isoformat(),
        }

    def _build_response(self, entry: Dict[str, Any], req: httpx.Request) -> httpx.Response:
        content = b""
        body = entry.get("body", "")
        if body:
             content = base64.b64decode(body)
             
        resp = httpx.Response(
            status_code=entry.get("status_code", 200),
            headers=entry.get("headers", {}),
            content=content,
            request=req
        )
        return resp
