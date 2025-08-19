# An HTTPCache pacakge  for caching user request
import hashlib
from collections import defaultdict
from datetime import datetime
from http import HTTPStatus
from http.client import HTTPResponse
from io import BytesIO
from typing import Dict, List, Optional, Tuple

import diskcache as dc
from requests import PreparedRequest, Response, Session
from requests.structures import CaseInsensitiveDict

from utils import check_date, to_date


class Cache:
    def __init__(self, f_cache: str) -> None:
        self.cache_stor = dc.Cache(f_cache)

    def get(self, cache_keys: str) -> bytes | None:
        resp = self.cache_stor.get(cache_keys)
        if not resp:
            return None
        print(resp)
        return resp

    def set(self, cache_keys: str, body: bytes, ttl: int = 0) -> None:
        self.cache_stor.set(cache_keys, body, ttl)

    def delete(self, cache_keys: str) -> None:
        self.cache_stor.delete(cache_keys, retry=True)

    def read_cache_resp(
        self, cache_keys: str
    ) -> Optional[Tuple[Dict[str, List[str]], bytes]]:
        respBody = self.get(cache_keys=cache_keys)
        if respBody is None:
            return None

        sock = BytesIO(respBody)
        response = HTTPResponse(sock)
        response.begin()
        headers = self._get_headers_as_dict(response.getheaders())

        body = response.read()

        print(headers)
        return headers, body

    def _get_headers_as_dict(
        self, headers: List[Tuple[str, str]]
    ) -> Dict[str, List[str, str]]:
        raw_headers = headers
        headers = defaultdict(list)
        for key, value in raw_headers:
            headers[key].append(value)
        return dict(headers)


class HTTPCache(Session):
    fresh = 1
    stale = 0
    X_CACHE = "X-Cache"

    def __init__(self, storage: Cache) -> None:
        super().__init__()
        self.storage = storage
        self.x_from_cache = "hits"
        self.x_not_from_cache = "miss"

    def _cache_keys(self, request: PreparedRequest) -> str:
        url = f"{request.method}:{request.url}"
        return hashlib.md5(url.encode()).hexdigest()

    def _parse_cache_control(self, req: PreparedRequest) -> Dict[str, str]:
        cache_control = req.headers.get("cache-control")
        cc: Dict[str, str] = {}
        if not cache_control:
            return cc
        split_cc = cache_control.split(",")
        for val in split_cc:
            val = val.strip(" ")
            if "=" in val:
                key, val = val.split("=")
                cc[key] = val
            else:
                cc[val] = ""
        return cc

    def _check_freshness(self, req: PreparedRequest, resp: Response) -> int:
        reqCache = self._parse_cache_control(req.headers)
        respCache = self._parse_cache_control(resp.headers)

        if reqCache.get("no-cache"):
            return 2
        if respCache.get("no-cache"):
            return self.stale
        if reqCache.get("only-if-cached"):
            return self.fresh

        date = check_date(resp)
        now = datetime.now()
        current_age = (now - date).total_seconds()

        resp_max_age = respCache.get("max-age")
        if resp_max_age is not None:
            resp_max_age = int(resp_max_age)
            if current_age <= resp_max_age:
                fresh = True
            else:
                fresh = False
        elif resp.headers.get("expires"):
            expires_dt = to_date(resp.headers["expires"])
            fresh = now <= expires_dt
        else:
            fresh = False

        max_stale = reqCache.get("max-stale")
        if not fresh and max_stale is not None:
            if max_stale == "":
                fresh = True
            else:
                max_stale_sec = int(max_stale)
                if (
                    resp_max_age is not None
                    and current_age - resp_max_age <= max_stale_sec
                ):
                    fresh = True

        min_fresh = reqCache.get("min-fresh")
        if fresh and min_fresh is not None:
            min_fresh_sec = int(min_fresh)
            if (
                resp_max_age is not None
                and resp_max_age - current_age < min_fresh_sec
            ):
                fresh = False

        return self.fresh if fresh else self.stale

    def send(self, req: PreparedRequest, **kwargs) -> Response:
        cached_key = self._cache_keys(req)
        cachable = (
            req.method == "GET" or req.method == "HEAD"
        ) and req.headers.get("range") is None
        cacheResp, cacheBody = self.storage.read_cache_resp(cached_key)

        if cacheResp and cachable:
            req.headers[HTTPCache.X_CACHE] = self.x_from_cache

        if self._feature_flag_matches(req, cacheResp) and (
            cachable and cacheResp
        ):
            fresh = self._check_freshness(req, cacheResp)
            if fresh == self.fresh:
                return self._build_response_from_cache(cacheResp, cacheBody)
            else:
                newReq = req
                changed = False
                cache_etag = cacheResp.get("etag")
                if cache_etag and req.headers.get("etag"):
                    changed = True
                    newReq.headers["if-none-matched"] = cache_etag

                lastmodifed_ = cacheResp.get("last-modified")
                if lastmodifed_ and req.headers.get("last_modified"):
                    changed = True
                    newReq.headers["if-modified-since"] = lastmodifed_

                if changed:
                    req = newReq

        resp = super().send(req, **kwargs)

        if cachable and resp.status_code == HTTPStatus.NOT_MODIFIED:
            ...

        return resp

    def _feature_flag_matches(
        self, req: PreparedRequest, resp: Response
    ) -> bool:
        req_flag = req.headers.get("x-cache-feature-flag", "")
        resp_falg = req.headers.get("x-cache-feature-flag", "")

        return req_flag == resp_falg

    def _build_response_from_cache(
        cache_resp: Dict, cache_body: bytes
    ) -> Response:
        resp = Response()
        resp.content = cache_body
        resp.status_code = cache_resp.get("status_code", 200)
        resp.headers = CaseInsensitiveDict(cache_resp.get("headers", {}))
        resp.url = cache_resp.get("url", "")
        resp.reason = cache_resp.get("reason", "OK")
        resp.encoding = cache_resp.get("encoding", None)

        return resp

    def _can_store(self, resp: Response) -> bool:
        return False if resp.headers.get("no-store") else True

    # def _get_headers_as_dict(
    #     self, r: Response | PreparedRequest
    # ) -> Dict[str, List[str]]:
    #     headers = r.headers
    #     headers_dict = defaultdict(list)
    #     for key, value in headers:
    #         headers_dict[key.lower()].append(value)
    #     return dict(headers_dict)


if "__main__" == __name__:
    c = Cache("cache")
    cache = HTTPCache(storage=c)
    cache.get(
        "https://www.example.com/path/to/resource?search=python&sort=asc#section1"
    )
