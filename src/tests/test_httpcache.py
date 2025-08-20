import shutil
import unittest

from cachio.cache import Cache
from cachio.httpcache import HTTPCache
from cachio.redis_cache import RedisCache


class TestHTTPCache(unittest.TestCase):
    def setUp(self):
        self.store_cache = "test_cache"
        self.cache = Cache(self.store_cache)
        self.cache = HTTPCache(self.cache)
        self.test_url = "https://example.com/index.html"

    def tearDown(self):
        shutil.rmtree(self.store_cache)
        print("tearing down")

    def test_send_request_successful(self):
        resp = self.cache.get(self.test_url)
        self.assertIsNotNone(resp, msg="response should not be none")
        self.assertEqual(resp.status_code, 200)

        self.assertEqual(
            resp.headers.get(HTTPCache.X_CACHE), HTTPCache.X_NOT_FROM_CACHE
        )

    def test_cache_hits_on_second_trial(self):
        resp = self.cache.get(self.test_url)
        self.assertIsNotNone(resp, msg="response should not be none")
        self.assertEqual(resp.status_code, 200)

        resp = self.cache.get(self.test_url)
        self.assertIsNotNone(resp, msg="response should not be none")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            resp.headers.get(HTTPCache.X_CACHE), HTTPCache.X_FROM_CACHE
        )


class TestRedisCache(unittest.TestCase):
    def setUp(self):
        self.cache_store = RedisCache(host="localhost", port=6379, password="")
        self.cache = HTTPCache(self.cache_store)
        self.test_url = "https://example.com/index.html"

    def tearDown(self):
        keys = self.cache_store.red.keys()
        for key in keys:
            self.cache_store.delete(key)

    def test_send_request_successful(self):
        resp = self.cache.get(self.test_url)
        self.assertIsNotNone(resp, msg="response should not be none")
        self.assertEqual(resp.status_code, 200)

        self.assertEqual(
            resp.headers.get(HTTPCache.X_CACHE), HTTPCache.X_NOT_FROM_CACHE
        )

    def test_cache_hits_on_second_trial(self):
        resp = self.cache.get(self.test_url)
        self.assertIsNotNone(resp, msg="response should not be none")
        self.assertEqual(resp.status_code, 200)

        resp = self.cache.get(self.test_url)
        self.assertIsNotNone(resp, msg="response should not be none")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            resp.headers.get(HTTPCache.X_CACHE), HTTPCache.X_FROM_CACHE
        )
