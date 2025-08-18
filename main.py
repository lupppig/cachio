# An HTTPCache pacakge  for caching user request
from urllib.parse import parse_qsl, urlencode, urlparse
import requests
import hashlib
from error import ErrorParseScheme


class HTTPCache:
    def __init__(self, url: str, **headers):
        self.url = url
        self.headers = headers

    def __cacheKeys(self, url: str) -> str:
        h_url = self.__cleanUrl(url)
        return hashlib.md5(h_url.encode()).hexdigest()

    def __cleanUrl(self, url: str) -> str:
        sorted_params = ""
        cleaned_url = self.url
        url_split = cleaned_url.split("?")
        queries = url_split[1] if len(url_split) == 2 else ""
        if queries != "":
            sorted_params = urlencode(
                sorted(parse_qsl(queries), key=lambda items: str(items[1]))
            )
            cleaned_url = url_split[0] + "?" + sorted_params

        cleaned_url = cleaned_url.strip().lower()
        parsed_url = urlparse(cleaned_url)

        if not parsed_url.scheme:
            raise ErrorParseScheme(
                "missing url scheme http or https missing in requests"
            )
        cleaned = parsed_url._replace(
            scheme=parsed_url.scheme.lower(), netloc=parsed_url.netloc.lower()
        )
        return cleaned.geturl()

    def set(self): ...

    def delete(self): ...

    def get(self): ...


if "__main__" == __name__:
    cache = HTTPCache("https://example.com?name=darasimi&age=12")

    cache.send_request()
