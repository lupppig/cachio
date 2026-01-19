import unittest
import asyncio
from unittest.mock import MagicMock, patch
import httpx
from cachio.backends.async_backends import AsyncInMemoryCache
from cachio.wrappers.httpx import HttpxCacheClient

class TestAsyncCache(unittest.IsolatedAsyncioTestCase):
    async def test_async_memory_backend(self):
        backend = AsyncInMemoryCache()
        await backend.set("key", {"foo": "bar"})
        val = await backend.get("key")
        self.assertEqual(val, {"foo": "bar"})

    async def test_httpx_wrapper(self):
        backend = AsyncInMemoryCache()
        client = HttpxCacheClient(backends=[backend])
        
        # Mock httpx response
        mock_req = httpx.Request("GET", "https://example.com/api")
        mock_resp = httpx.Response(200, json={"data": 1}, headers={"Cache-Control": "max-age=60"}, request=mock_req)
        # We need to mock the internal client's send method
        
        with patch.object(httpx.AsyncClient, 'send', return_value=mock_resp) as mock_send:
             # 1. Miss
             resp1 = await client.get("https://example.com/api")
             self.assertEqual(resp1.status_code, 200)
             self.assertEqual(resp1.headers.get("X-Cache"), "miss")
             
             # 2. Hit
             resp2 = await client.get("https://example.com/api")
             self.assertEqual(resp2.status_code, 200)
             self.assertEqual(resp2.headers.get("X-Cache"), "hits")
             
             # Verify only 1 network call
             self.assertEqual(mock_send.call_count, 1)

if __name__ == "__main__":
    unittest.main()
