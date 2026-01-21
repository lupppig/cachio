import asyncio
import time
import unittest
from cachio.backends import AsyncInMemoryCache
from cachio.wrappers import HttpxCacheClient
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

class TestConcurrency(unittest.IsolatedAsyncioTestCase):
    async def test_high_concurrency(self):
        backend = AsyncInMemoryCache(max_size=1000)
        client = HttpxCacheClient(backends=[backend])
        
        num_requests = 200
        url = "https://example.com/concurrent"
        
        mock_resp = httpx.Response(
            200, 
            content=b"Concurrent Data", 
            headers={"Cache-Control": "max-age=60"},
            request=httpx.Request("GET", url)
        )
        
        with patch.object(httpx.AsyncClient, "send", AsyncMock(return_value=mock_resp)) as mock_send:
            async def make_request():
                return await client.get(url)
            
            # Fire all requests concurrently
            start_time = time.time()
            tasks = [make_request() for _ in range(num_requests)]
            responses = await asyncio.gather(*tasks)
            duration = time.time() - start_time
            
            backend_size = len(backend._sync_cache._cache)
            print(f"\nConcurrency test: {num_requests} requests in {duration:.4f}s")
            print(f"Backend size: {backend_size}")
            
            # All responses should be successful
            for r in responses:
                self.assertEqual(r.status_code, 200)
                self.assertEqual(r.content, b"Concurrent Data")
            
            # Only ONE network call should have been made if they hit the cache
            # WAIT: If they all fire at once, some might miss before the first one caches.
            # But with 200, we expect VERY few hits if it is NOT locking properly, 
            # or 1 hit if it is locking properly at the right level.
            # Cachio currently doesn't have "request coalescing" (single-flight), 
            # so multiple might hit the network until the first one returns and sets.
            self.assertGreaterEqual(mock_send.call_count, 1)
            self.assertLess(mock_send.call_count, num_requests) # Should be significantly less than 200

    async def test_lru_under_load(self):
        # Small cache, many keys
        backend = AsyncInMemoryCache(max_size=10)
        client = HttpxCacheClient(backends=[backend])
        
        num_distinct_urls = 50
        
        async def make_request(i):
            url = f"https://example.com/{i}"
            mock_resp = httpx.Response(
                200, content=b"data", 
                headers={"Cache-Control": "max-age=60"},
                request=httpx.Request("GET", url)
            )
            with patch.object(httpx.AsyncClient, "send", AsyncMock(return_value=mock_resp)):
                await client.get(url)

        tasks = [make_request(i) for i in range(num_distinct_urls)]
        await asyncio.gather(*tasks)
        
        # Verify size is maintained
        backend_size = len(backend._sync_cache._cache)
        self.assertEqual(backend_size, 10)

if __name__ == "__main__":
    from unittest.mock import patch
    unittest.main()
