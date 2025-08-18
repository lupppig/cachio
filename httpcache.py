# An HTTPCache pacakge  for caching user request
import hashlib
from datetime import datetime
from http.client import HTTPResponse
from io import BytesIO
from typing import Dict

import diskcache as dc
from requests import PreparedRequest, Response, Session

from utils import check_date, to_date


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
    fresh = 1
    stale = 0

    def __init__(self, storage: Cache) -> None:
        super().__init__()
        self.storage = storage

    def _cache_keys(self, request: PreparedRequest) -> str:
        url = f"{request.method}:{request.url}"
        return hashlib.md5(url.encode()).hexdigest()

    def _parse_cache_control(self, req: PreparedRequest) -> Dict[str, str]:
        cache_control = req.headers.get("Cache-Control")
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
        elif resp.headers.get("Expires"):
            expires_dt = to_date(resp.headers["Expires"])
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
        cacheResp = self.storage.get(cached_key)

        if cachable or cacheResp:
            ...

        resp = super().send(req, **kwargs)

        self._parse_cache_control(resp)
        print(resp.headers)
        return resp


if "__main__" == __name__:
    c = Cache("cache")
    cache = HTTPCache(storage=c)
    cache.get(
        "https://www.example.com/path/to/resource?search=python&sort=asc#section1"
    )
