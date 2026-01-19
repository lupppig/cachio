import hashlib
from datetime import datetime, timezone
from http import HTTPStatus
from typing import Dict, List, Optional, Union, Any

from requests import PreparedRequest, Response, Session
from requests.structures import CaseInsensitiveDict

from .interfaces import CacheBackend
from .utils import check_date, to_date
from .error import DateDirectiveMissing

class HTTPCache(Session):
    FRESH = 1
    STALE = 0
    X_CACHE = "X-Cache"
    X_FROM_CACHE = "hits"
    X_NOT_FROM_CACHE = "miss"

    def __init__(self, backends: List[CacheBackend]) -> None:
        super().__init__()
        self.backends = backends

    def _cache_keys(self, request_url: str) -> str:
        return hashlib.md5(request_url.encode()).hexdigest()

    def _parse_cache_control(self, headers: CaseInsensitiveDict) -> Dict[str, Optional[str]]:
        cache_control = headers.get("cache-control")
        cc: Dict[str, Optional[str]] = {}
        if not cache_control:
            return cc
        
        split_cc = cache_control.split(",")
        for val in split_cc:
            val = val.strip()
            if "=" in val:
                key, value = val.split("=", 1)
                cc[key.lower()] = value
            else:
                cc[val.lower()] = None
        return cc

    def _check_freshness(self, req: PreparedRequest, resp: Response) -> int:
        req_headers = req.headers or CaseInsensitiveDict()
        req_cc = self._parse_cache_control(req_headers)
        resp_cc = self._parse_cache_control(resp.headers)

        if "no-cache" in req_cc:
            return 2
        if "no-cache" in resp_cc:
            return self.STALE
        if "only-if-cached" in req_cc:
            return self.FRESH

        try:
            date = check_date(resp)
        except DateDirectiveMissing:
            date = datetime.now(timezone.utc)
            
        now = datetime.now(timezone.utc)
        current_age = (now - date).total_seconds()

        resp_max_age = resp_cc.get("max-age")
        if resp_max_age is not None:
            try:
                if current_age <= int(resp_max_age):
                    fresh = True
                else:
                    fresh = False
            except ValueError:
                fresh = False
        elif resp.headers.get("expires"):
            expires_dt = to_date(resp.headers["expires"])
            fresh = now <= expires_dt
        else:
            fresh = False

        max_stale = req_cc.get("max-stale")
        if not fresh and max_stale is not None:
            if max_stale is None or max_stale == "":
                fresh = True
            else:
                try:
                    max_stale_sec = int(max_stale)
                    if resp_max_age is not None:
                         if current_age - int(resp_max_age) <= max_stale_sec:
                             fresh = True
                except ValueError:
                    pass

        min_fresh = req_cc.get("min-fresh")
        if fresh and min_fresh is not None:
            try:
                min_fresh_sec = int(min_fresh)
                if resp_max_age is not None:
                    if int(resp_max_age) - current_age < min_fresh_sec:
                        fresh = False
            except ValueError:
                pass

        return self.FRESH if fresh else self.STALE

    def send(self, request: PreparedRequest, **kwargs: Any) -> Response: # type: ignore
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
            freshness = self._check_freshness(request, cache_resp)
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

        if resp.status_code >= 500 and cache_resp and self._stale_error_check(cache_resp):
             cache_resp.headers["Stale-Warning"] = '110 - "Response is stale"'
             return cache_resp

        if cachable and resp.status_code == HTTPStatus.OK:
             resp_cc = self._parse_cache_control(resp.headers)
             if "no-store" not in resp_cc:
                 resp.headers[self.X_CACHE] = self.X_NOT_FROM_CACHE
                 
                 cache_entry = self._serialize_response(resp)
                 
                 for backend in self.backends:
                     backend.set(cached_key, cache_entry)
        
        if resp.status_code != HTTPStatus.NOT_MODIFIED and resp.status_code != HTTPStatus.OK:
             for backend in self.backends:
                 backend.delete(cached_key)

        return resp

    def _stale_error_check(self, resp: Response) -> bool:
        cc = self._parse_cache_control(resp.headers)
        stale_if_error = cc.get("stale-if-error")
        if not stale_if_error:
            return False
            
        try:
            stale_window = int(stale_if_error)
        except ValueError:
            return False

        try:
            date = check_date(resp)
        except DateDirectiveMissing:
            date = datetime.now(timezone.utc)
        now = datetime.now(timezone.utc)
        age = (now - date).total_seconds()
        
        return age <= stale_window

    def _serialize_response(self, resp: Response) -> Dict[str, Any]:
        return {
            "status_code": resp.status_code,
            "reason": resp.reason,
            "url": resp.url,
            "headers": dict(resp.headers),
            "body": resp.content.decode('utf-8', errors='replace') if resp.content else "",
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
        if isinstance(body, str):
            resp._content = body.encode('utf-8')
        else:
            resp._content = body
            
        return resp
