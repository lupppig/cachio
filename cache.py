import json
from collections import defaultdict
from typing import Dict, List, Tuple

import diskcache as dc
from requests import Response
from requests.structures import CaseInsensitiveDict


class Cache:
    def __init__(self, f_cache: str) -> None:
        self.cache_stor = dc.Cache(f_cache)

    def get(self, cache_keys: str) -> Dict[str, str] | None:
        resp = self.cache_stor.get(cache_keys)
        if not resp:
            return None

        dct_data = json.loads(resp)
        return dct_data

    def set(self, cache_keys: str, cache_entry) -> None:
        print(type(cache_entry))
        j_entry = json.dumps(cache_entry)
        self.cache_stor.set(cache_keys, j_entry)

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
