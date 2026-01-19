import hashlib
import base64
from datetime import datetime, timezone
from http import HTTPStatus
from typing import Dict, List, Optional, Union, Any

from requests import PreparedRequest, Response, Session
from requests.structures import CaseInsensitiveDict

from .interfaces import CacheBackend
from .utils import check_date, to_date
from .error import DateDirectiveMissing

from .policy import check_freshness, check_stale_if_error, parse_cache_control, FRESH, STALE

class HTTPCache(Session):
    """
    Subclass of requests.Session with tiered caching support.
    """
    FRESH = FRESH
    STALE = STALE
    X_CACHE = "X-Cache"
    X_FROM_CACHE = "hits"
    X_NOT_FROM_CACHE = "miss"

    def __init__(self, backends: List[CacheBackend]) -> None:
        super().__init__()
        self.backends = backends

    def _cache_keys(self, request_url: str) -> str:
        return hashlib.md5(request_url.encode()).hexdigest()

    def send(self, request: PreparedRequest, **kwargs: Any) -> Response: # type: ignore
        """Send a request with caching logic."""
        if not request.url:
            return super().send(request, **kwargs)

        cached_key = self._cache_keys(request.url)
        cachable_method = request.method in ("GET", "HEAD")
        cachable = cachable_method and request.headers.get("range") is None

        cache_entry: Optional[Dict[str, Any]] = None
        found_in_index = -1

        if cachable:
            for i, backend in enumerate(self.backends):
                cache_entry = backend.get(cached_key)
                if cache_entry:
                    found_in_index = i
                    break
        
        cache_resp: Optional[Response] = None
        if cache_entry:
            cache_resp = self._build_response_from_cache(cache_entry)
            cache_resp.headers[self.X_CACHE] = self.X_FROM_CACHE
            
            if found_in_index > 0:
                for i in range(found_in_index):
                    self.backends[i].set(cached_key, cache_entry)

        if cache_resp:
            req_headers = dict(request.headers) if request.headers else {}
            freshness = check_freshness(req_headers, dict(cache_resp.headers))
            
            if freshness == self.FRESH:
                return cache_resp
            
            if request.headers is None:
                request.headers = CaseInsensitiveDict()
            
            etag = cache_resp.headers.get("etag")
            if etag:
                request.headers["if-none-matched"] = etag
            
            last_modified = cache_resp.headers.get("last-modified")
            if last_modified:
                request.headers["if-modified-since"] = last_modified

        try:
            resp = super().send(request, **kwargs)
        except Exception:
            raise

        if resp.status_code == HTTPStatus.NOT_MODIFIED and cache_resp:
            for k, v in resp.headers.items():
                cache_resp.headers[k] = v
            
            new_entry = self._serialize_response(cache_resp)
            for backend in self.backends:
                backend.set(cached_key, new_entry)
            
            cache_resp.headers[self.X_CACHE] = self.X_FROM_CACHE 
            return cache_resp

        if resp.status_code >= 500 and cache_resp and check_stale_if_error(dict(cache_resp.headers)):
             cache_resp.headers["Stale-Warning"] = '110 - "Response is stale"'
             return cache_resp

        if cachable and resp.status_code == HTTPStatus.OK:
             resp_cc = parse_cache_control(dict(resp.headers))
             if "no-store" not in resp_cc:
                 resp.headers[self.X_CACHE] = self.X_NOT_FROM_CACHE
                 
                 cache_entry = self._serialize_response(resp)
                 
                 for backend in self.backends:
                     backend.set(cached_key, cache_entry)
        
        if resp.status_code != HTTPStatus.NOT_MODIFIED and resp.status_code != HTTPStatus.OK:
             for backend in self.backends:
                 backend.delete(cached_key)

        return resp


    def _serialize_response(self, resp: Response) -> Dict[str, Any]:
        return {
            "status_code": resp.status_code,
            "reason": resp.reason,
            "url": resp.url,
            "headers": dict(resp.headers),
            "body": base64.b64encode(resp.content).decode('ascii') if resp.content else "",
            "encoding": resp.encoding,
            "timestamp": datetime.now().isoformat(),
        }

    def _build_response_from_cache(self, entry: Dict[str, Any]) -> Response:
        resp = Response()
        resp.status_code = entry.get("status_code", 200)
        resp.reason = entry.get("reason", "OK")
        resp.url = entry.get("url", "")
        resp.headers = CaseInsensitiveDict(entry.get("headers", {}))
        resp.encoding = entry.get("encoding")
        
        body = entry.get("body", "")
        if isinstance(body, str) and body:
            resp._content = base64.b64decode(body)
        else:
            resp._content = b""
            
        return resp
