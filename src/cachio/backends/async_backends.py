import asyncio
import json
import time
from typing import Dict, Any, Optional
from ..interfaces import AsyncCacheBackend
from .memory import InMemoryCache
from .disk import DiskBackend

try:
    import redis.asyncio as redis
except ImportError:
    redis = None

class AsyncInMemoryCache:
    """Async wrapper around InMemoryCache using asyncio.Lock."""
    def __init__(self, max_size: int = 1000, default_ttl: Optional[int] = None):
        self._sync_cache = InMemoryCache(max_size, default_ttl)
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Retrieve value asynchronously."""
        async with self._lock:
            return self._sync_cache.get(key)

    async def set(self, key: str, value: Dict[str, Any], ttl: Optional[int] = None) -> None:
        """Set value asynchronously."""
        async with self._lock:
            self._sync_cache.set(key, value, ttl)

    async def delete(self, key: str) -> None:
        """Delete value asynchronously."""
        async with self._lock:
            self._sync_cache.delete(key)

    async def clear(self) -> None:
        """Clear cache asynchronously."""
        async with self._lock:
            self._sync_cache.clear()

class AsyncDiskBackend:
    """Async wrapper around DiskBackend using asyncio.to_thread."""
    def __init__(self, cache_dir: str, **kwargs: Any):
        self._sync_backend = DiskBackend(cache_dir, **kwargs)

    async def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Retrieve value offloading to thread."""
        return await asyncio.to_thread(self._sync_backend.get, key)

    async def set(self, key: str, value: Dict[str, Any], ttl: Optional[int] = None) -> None:
        """Set value offloading to thread."""
        await asyncio.to_thread(self._sync_backend.set, key, value, ttl)

    async def delete(self, key: str) -> None:
        """Delete value offloading to thread."""
        await asyncio.to_thread(self._sync_backend.delete, key)

    async def clear(self) -> None:
        """Clear cache offloading to thread."""
        await asyncio.to_thread(self._sync_backend.clear)

class AsyncRedisBackend:
    """Async Redis backend implementation."""
    def __init__(self, host: str, port: int, password: Optional[str] = None, **kwargs: Any):
        if redis is None:
            raise ImportError("redis-py with async support is required. Install `redis`.")
        self.redis = redis.StrictRedis(
            host=host,
            port=port,
            password=password,
            decode_responses=True,
            **kwargs
        )

    async def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Retrieve value from Redis."""
        val = await self.redis.get(key)
        if not val:
            return None
        try:
            if isinstance(val, str):
                 return json.loads(val)
        except json.JSONDecodeError:
            pass
        return None

    async def set(self, key: str, value: Dict[str, Any], ttl: Optional[int] = None) -> None:
        """Set value in Redis with optional TTL."""
        val = json.dumps(value)
        await self.redis.set(key, val, ex=ttl)

    async def delete(self, key: str) -> None:
        """Delete value from Redis."""
        await self.redis.delete(key)

    async def clear(self) -> None:
        """Flush Redis database."""
        await self.redis.flushdb()
