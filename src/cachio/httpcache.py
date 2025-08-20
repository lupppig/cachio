# An HTTPCache pacakge  for caching user request
import hashlib
from datetime import datetime, timezone
from http import HTTPStatus
from io import StringIO
from typing import Dict, List

from requests import PreparedRequest, Response, Session

from .cache import Cache
from .utils import check_date, to_date


class HTTPCache(Session):
    fresh = 1
    stale = 0
    X_CACHE = "X-Cache"
    X_FROM_CACHE = "hits"
    X_NOT_FROM_CACHE = "miss"

    def __init__(self, storage: Cache) -> None:
        super().__init__()
        self.storage = storage

    def _cache_keys(self, request: str) -> str:
        return hashlib.md5(request.encode()).hexdigest()

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
        cached_key = self._cache_keys(req.url)
        cachable = (
            req.method == "GET" or req.method == "HEAD"
        ) and req.headers.get("range") is None
        cacheResp = self.storage.read_cache_resp(cached_key)

        if cacheResp and cachable:
            cacheResp.headers[HTTPCache.X_CACHE] = HTTPCache.X_FROM_CACHE

        if self._check_match_request(req, cacheResp):
            fresh = self._check_freshness(req, cacheResp)
            if fresh == self.fresh:
                return cacheResp
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
            cache_entry = {
                "status_line": f"HTTP/{resp.raw.version / 10:.1f} {resp.status_code} {resp.reason}",
                "url": resp.url,
                "status_code": resp.status_code,
                "headers": dict(resp.headers),
                "body": resp.content.decode(),
                "encoding": resp.encoding,
                "timestamp": datetime.now().isoformat(),
            }
            self.storage.set(cached_key, cache_entry)
        else:
            self.storage.delete(cached_key)
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

    def _check_match_request(
        self, req: PreparedRequest, resp: Response
    ) -> bool:
        if not resp:
            return False

        req_url = self.normalize_url(req.url)
        resp_url = self.normalize_url(resp.url)

        return self._cache_keys(req_url) == self._cache_keys(resp_url)

    def normalize_url(self, url: str) -> str:
        from urllib.parse import parse_qsl, urlencode, urlparse

        parsed = urlparse(url)
        query = urlencode(sorted(parse_qsl(parsed.query)))

        return (
            f"{parsed.scheme}://{parsed.netloc}{parsed.path}?{query}"
            if query
            else f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        )

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
