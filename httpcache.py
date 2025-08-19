# An HTTPCache pacakge  for caching user request
import hashlib
from collections import defaultdict
from datetime import datetime, timezone
from http import HTTPStatus
from io import StringIO
from typing import Dict, List, Tuple

import diskcache as dc
from requests import PreparedRequest, Response, Session
from requests.structures import CaseInsensitiveDict

from utils import check_date, to_date


class Cache:
    def __init__(self, f_cache: str) -> None:
        self.cache_stor = dc.Cache(f_cache)

    def get(self, cache_keys: str) -> Dict[str, str] | None:
        resp = self.cache_stor.get(cache_keys)
        if not resp:
            return None
        return resp

    def set(self, cache_keys: str, cache_entry) -> None:
        self.cache_stor.set(cache_keys, cache_entry)

    def delete(self, cache_keys: str) -> None:
        self.cache_stor.delete(cache_keys, retry=True)

    def read_cache_resp(self, cache_keys: str) -> Response | None:
        respBody = self.get(cache_keys=cache_keys)
        if respBody is None:
            return None
        return self._build_response_from_cache(respBody)

    def _get_headers_as_dict(
        self, headers: List[Tuple[str, str]]
    ) -> Dict[str, List[str]]:
        raw_headers = headers
        headers = defaultdict(list)
        for key, value in raw_headers:
            headers[key].append(value)
        return dict(headers)

    def _build_response_from_cache(
        self, cache_resp: Dict[str, str]
    ) -> Response:
        resp = Response()
        resp._content = cache_resp.get("body", bytes())
        resp.status_code = cache_resp.get("status_code", 200)
        resp.headers = CaseInsensitiveDict(cache_resp.get("headers", {}))
        resp.url = cache_resp.get("url", "")
        resp.reason = cache_resp.get("reason", "OK")
        resp.encoding = cache_resp.get("encoding", None)

        return resp


class HTTPCache(Session):
    fresh = 1
    stale = 0
    X_CACHE = "X-Cache"
    X_FROM_CACHE = "hits"
    X_NOT_FROM_CACHE = "miss"

    def __init__(self, storage: Cache) -> None:
        super().__init__()
        self.storage = storage

    def _cache_keys(self, request: PreparedRequest) -> str:
        url = f"{request.method}:{request.url}"
        return hashlib.md5(url.encode()).hexdigest()

    def _parse_cache_control(
        self, req: PreparedRequest | Response
    ) -> Dict[str, str | None]:
        cache_control = req.headers.get("cache-control")
        cc: Dict[str, str | None] = {}
        if not cache_control:
            return cc
        split_cc = cache_control.split(",")
        for val in split_cc:
            val = val.strip(" ")
            if "=" in val:
                key, val = val.split("=")
                cc[key.lower()] = val
            else:
                cc[val.lower()] = None
        return cc

    def _check_freshness(self, req: PreparedRequest, resp: Response) -> int:
        reqCache = self._parse_cache_control(req)
        respCache = self._parse_cache_control(resp)

        if reqCache.get("no-cache"):
            return 2
        if respCache.get("no-cache"):
            return self.stale
        if reqCache.get("only-if-cached"):
            return self.fresh

        date = check_date(resp)
        now = datetime.now(timezone.utc)
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
        cacheResp = self.storage.read_cache_resp(cached_key)

        if cacheResp and cachable:
            cacheResp.headers[HTTPCache.X_CACHE] = HTTPCache.X_FROM_CACHE

        print("---------------->2")
        if self._feature_flag_matches(req, cacheResp) and (
            cachable and cacheResp
        ):
            print("=================> 3")
            fresh = self._check_freshness(req, cacheResp)
            if fresh == self.fresh:
                return cacheResp
            else:
                print("---------> 4")
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
        print(resp.status_code, "---------> 5")
        if resp.status_code == HTTPStatus.NOT_MODIFIED and cachable:
            resp_headers = self._get_headers(resp)
            cache_resp = cacheResp
            for h in resp_headers:
                cache_resp.headers[h] = resp.headers[h]
            resp = cache_resp

        elif resp.status_code >= 500 and cachable and self.stale_error(resp):
            cache_resp.headers["Stale-Warning"] = '110 - "Response is stale"'
            return cache_resp
        else:
            if resp.status_code != HTTPStatus.OK:
                self.storage.delete(cached_key)
                return resp

        if (
            cachable
            and self._can_store(resp)
            and resp.status_code == HTTPStatus.OK
        ):
            resp.headers[HTTPCache.X_CACHE] = HTTPCache.X_NOT_FROM_CACHE
            resp.headers["X-Cache-Feature-Flag"] = "disk-cached"
            cache_entry = {
                "status_line": f"HTTP/{resp.raw.version / 10:.1f} {resp.status_code} {resp.reason}",
                "url": resp.url,
                "status_code": resp.status_code,
                "headers": dict(resp.headers),
                "body": resp.content,
                "encoding": resp.encoding,
                "timestamp": datetime.now().isoformat(),
            }
            self.storage.set(cached_key, cache_entry)
        return resp

    def _feature_flag_matches(
        self, req: PreparedRequest, resp: Response
    ) -> bool:
        req_flag = req.headers.get("x-cache-feature-flag", "")
        resp_falg = req.headers.get("x-cache-feature-flag", "")

        return req_flag == resp_falg

    def stale_error(self, resp: Response) -> bool:
        stale = resp.headers.get("stale-if-error")
        if not stale:
            return False

        response_time = check_date(resp)

        current_age = (
            datetime.now(timezone.utc) - response_time
        ).total_seconds()
        stale_sec = int(stale)
        return current_age > stale_sec

    def _can_store(self, resp: Response) -> bool:
        return False if resp.headers.get("no-store") else True

    def _get_headers(self, resp: Response) -> List[str]:
        hop_headers = [
            "Connection",
            "Keep-Alive",
            "Proxy-Authenticate",
            "Proxy-Authorization",
            "TE",
            "Trailer",
            "Transfer-Encoding",
            "Upgrade",
        ]

        # treat connection headers as hop-by-hop header also
        if resp.headers.get("connection"):
            conn_headers = resp.headers["connection"].split(",")
            for c_header in conn_headers:
                c_header = c_header.strip()
                hop_headers.append(c_header)
        header = [header for header in hop_headers if resp.headers.get(header)]
        return header

    def _construct_proper_response(self, resp: Response):
        buffer = StringIO()

        version = getattr(resp, "version", 11)
        http_version = {10: "HTTP/1.0", 11: "HTTP/1.1", 20: "HTTP/2.0"}.get(
            version, "HTTP/1.1"
        )
        buffer.write(f"{http_version} {resp.status_code} {resp.reason} \r\n")
        for k, v in resp.headers:
            buffer.write(f"{k}:{v}\r\n")
        buffer.write("\r\n")
        if resp.content:
            try:
                body = resp.content.decode(
                    resp.encoding or "utf-8", errors="replace"
                )
            except Exception:
                body = resp.content
            if isinstance(body, str):
                buffer.write(body)
            else:
                return buffer.getvalue().encode() + body
        return buffer.getvalue()


if "__main__" == __name__:
    c = Cache("cache")
    cache = HTTPCache(storage=c)
    resp = cache.get("https://www.example.com/index.html")

    print(resp.content)
    print(resp.headers)
