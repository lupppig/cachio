import unittest
import asyncio
import base64
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, AsyncMock
import httpx
from requests import Response, PreparedRequest
from requests.structures import CaseInsensitiveDict

from cachio import HTTPCache, InMemoryCache
from cachio.backends import AsyncInMemoryCache
from cachio.wrappers import HttpxCacheClient, AiohttpCacheSession

class TestRequirementSatisfaction(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.test_url = "https://example.com/api"

    @patch("requests.Session.send")
    def test_httpcache_404_caching(self, mock_send):
        # 1. Setup: Cache 404s
        cache = HTTPCache(backends=[InMemoryCache()], cacheable_status_codes=(200, 404))
        
        # Use lowercase headers to be safe with dict() conversions
        now_str = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
        
        mock_resp = Response()
        mock_resp.status_code = 404
        mock_resp.reason = "Not Found"
        mock_resp.url = self.test_url
        mock_resp.headers = CaseInsensitiveDict({
            "cache-control": "max-age=60",
            "date": now_str
        })
        mock_resp._content = b"Not Found Body"
        mock_send.return_value = mock_resp
        
        req = PreparedRequest()
        req.prepare_url(self.test_url, {})
        req.method = "GET"
        req.headers = CaseInsensitiveDict({})

        # 2. First Request (Miss)
        resp1 = cache.send(req)
        self.assertEqual(resp1.status_code, 404)
        self.assertEqual(resp1.headers.get("X-Cache"), "miss")

        # 3. Second Request (Hit)
        resp2 = cache.send(req)
        self.assertEqual(resp2.status_code, 404)
        self.assertEqual(resp2.headers.get("X-Cache"), "hits")
        self.assertEqual(resp2.content, b"Not Found Body")
        
        # Verify only 1 network call
        self.assertEqual(mock_send.call_count, 1)

    async def test_httpx_client_301_caching(self):
        backend = AsyncInMemoryCache()
        client = HttpxCacheClient(backends=[backend], cacheable_status_codes=(200, 301))
        
        mock_req = httpx.Request("GET", self.test_url)
        mock_resp = httpx.Response(
            301, 
            content=b"Redirect Body", 
            headers={"cache-control": "max-age=60", "location": "https://new.com"},
            request=mock_req
        )
        
        with patch.object(httpx.AsyncClient, "send", AsyncMock(return_value=mock_resp)) as mock_send:
            # First request (Miss)
            resp1 = await client.get(self.test_url)
            self.assertEqual(resp1.status_code, 301)
            self.assertEqual(resp1.headers.get("X-Cache"), "miss")
            
            # Second request (Hit)
            resp2 = await client.get(self.test_url)
            self.assertEqual(resp2.status_code, 301)
            self.assertEqual(resp2.headers.get("X-Cache"), "hits")
            self.assertEqual(resp2.content, b"Redirect Body")
            
            # Verify only 1 network call
            self.assertEqual(mock_send.call_count, 1)

    async def test_aiohttp_session_caching(self):
        backend = AsyncInMemoryCache()
        async with AiohttpCacheSession(backends=[backend], cacheable_status_codes=(200, 404)) as session:
            mock_resp = MagicMock()
            mock_resp.status = 404
            mock_resp.reason = "Not Found"
            mock_resp.url = self.test_url
            mock_resp.headers = {"cache-control": "max-age=60"}
            mock_resp._body = b"Aiohttp Not Found"
            mock_resp.get_encoding.return_value = "utf-8"
            
            mock_resp.read = AsyncMock(return_value=b"Aiohttp Not Found")
            mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
            mock_resp.__aexit__ = AsyncMock(return_value=None)
            
            with patch("aiohttp.ClientSession._request", AsyncMock(return_value=mock_resp)) as mock_request:
                # First request (Miss)
                async with session.get(self.test_url) as resp1:
                    self.assertEqual(resp1.status, 404)
                    self.assertEqual(resp1.headers.get("X-Cache"), "miss")
                
                # Second request (Hit)
                async with session.get(self.test_url) as resp2:
                    self.assertEqual(resp2.status, 404)
                    self.assertEqual(resp2.headers.get("X-Cache"), "hits")
                    self.assertEqual(await resp2.read(), b"Aiohttp Not Found")
                
                # Verify only 1 network call
                self.assertEqual(mock_request.call_count, 1)

if __name__ == "__main__":
    unittest.main()
