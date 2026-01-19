import json
import shutil
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from requests import Response
from requests.structures import CaseInsensitiveDict

from cachio import HTTPCache, InMemoryCache, DiskBackend, RedisBackend, MemcachedBackend
from cachio.interfaces import CacheBackend

class MockBackend(CacheBackend):
    def __init__(self):
        self._data = {}
    
    def get(self, key):
        return self._data.get(key)
    
    def set(self, key, value, ttl=None):
        self._data[key] = value

    def delete(self, key):
        if key in self._data:
            del self._data[key]

    def clear(self):
        self._data.clear()

class TestInMemoryCache(unittest.TestCase):
    def test_lru_eviction(self):
        cache = InMemoryCache(max_size=2)
        cache.set("a", {"data": 1})
        cache.set("b", {"data": 2})
        self.assertIsNotNone(cache.get("a"))
        self.assertIsNotNone(cache.get("b"))
        
        cache.set("c", {"data": 3})
        # 'a' should be evicted
        self.assertIsNone(cache.get("a"))
        self.assertIsNotNone(cache.get("b"))
        self.assertIsNotNone(cache.get("c"))

    def test_ttl(self):
        cache = InMemoryCache(default_ttl=1)
        cache.set("a", {"data": 1})
        self.assertIsNotNone(cache.get("a"))
        time.sleep(1.1)
        self.assertIsNone(cache.get("a"))

class TestHTTPCacheLogic(unittest.TestCase):
    def setUp(self):
        self.memory_backend = MockBackend()
        self.disk_backend = MockBackend()
        self.http_cache = HTTPCache(backends=[self.memory_backend, self.disk_backend])
        
        self.test_url = "https://example.com/api"
        
    @patch("requests.Session.send")
    def test_cache_miss_then_hit(self, mock_send):
        # Setup mock response
        mock_resp = Response()
        mock_resp.status_code = 200
        mock_resp._content = b'{"foo": "bar"}'
        mock_resp.url = self.test_url
        mock_resp.headers = CaseInsensitiveDict({"Cache-Control": "max-age=60"})
        mock_send.return_value = mock_resp
        
        # 1. First Request (Miss)
        req = MagicMock()
        req.url = self.test_url
        req.method = "GET"
        req.headers = {}
        
        resp1 = self.http_cache.send(req)
        self.assertEqual(resp1.headers[HTTPCache.X_CACHE], HTTPCache.X_NOT_FROM_CACHE)
        self.assertEqual(resp1.status_code, 200)
        
        # Verify stored in both backends
        key = self.http_cache._cache_keys(self.test_url)
        self.assertIsNotNone(self.memory_backend.get(key))
        self.assertIsNotNone(self.disk_backend.get(key))
        
        # 2. Second Request (Hit from Memory)
        resp2 = self.http_cache.send(req)
        self.assertEqual(resp2.headers[HTTPCache.X_CACHE], HTTPCache.X_FROM_CACHE)
        
        # 3. Simulate Memory Eviction / Disk Hit
        self.memory_backend.clear()
        resp3 = self.http_cache.send(req)
        self.assertEqual(resp3.headers[HTTPCache.X_CACHE], HTTPCache.X_FROM_CACHE)
        # Verify populated back to memory (Read Repair)
        self.assertIsNotNone(self.memory_backend.get(key))

class TestDiskBackendActual(unittest.TestCase):
    def setUp(self):
        self.cache_dir = "test_disk_cache"
        self.backend = DiskBackend(cache_dir=self.cache_dir)

    def tearDown(self):
        shutil.rmtree(self.cache_dir, ignore_errors=True)

    def test_set_get(self):
        val = {"test": 123}
        self.backend.set("key", val)
        retrieved = self.backend.get("key")
        self.assertEqual(retrieved, val)

class TestBinaryStorage(unittest.TestCase):
    def test_binary_storage(self):
        backend = InMemoryCache()
        cache = HTTPCache([backend])
        
        binary_data = b'\x1f\x8b\x08\x00\x00\x00\x00\x00'
        
        mock_resp = Response()
        mock_resp.status_code = 200
        mock_resp._content = binary_data
        mock_resp.url = "https://example.com/image.png"
        mock_resp.headers = {"Content-Type": "application/gzip", "Cache-Control": "max-age=3600"}
        
        with patch("requests.Session.send", return_value=mock_resp):
            req = MagicMock()
            req.url = "https://example.com/image.png"
            req.method = "GET"
            req.headers = {}
            
            resp1 = cache.send(req)
            self.assertEqual(resp1.content, binary_data)
            
            resp2 = cache.send(req)
            self.assertEqual(resp2.headers[HTTPCache.X_CACHE], HTTPCache.X_FROM_CACHE)
            self.assertEqual(resp2.content, binary_data)
