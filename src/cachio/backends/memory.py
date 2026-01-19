import time
import threading
from collections import OrderedDict
from typing import Optional, Dict, Any
from ..interfaces import CacheBackend

class InMemoryCache:
    def __init__(self, max_size: int = 1000, default_ttl: Optional[int] = None):
        self.max_size = max_size
        self.default_ttl = default_ttl
        self._cache: OrderedDict[str, tuple[Dict[str, Any], float]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            if key not in self._cache:
                return None

            value, expiry = self._cache[key]

            if expiry != float('inf') and time.time() > expiry:
                del self._cache[key]
                return None

            self._cache.move_to_end(key)
            return value

    def set(self, key: str, value: Dict[str, Any], ttl: Optional[int] = None) -> None:
        with self._lock:
            ttl_val = ttl if ttl is not None else self.default_ttl
            expiry = time.time() + ttl_val if ttl_val is not None else float('inf')

            if key in self._cache:
                self._cache.move_to_end(key)
            self._cache[key] = (value, expiry)

            if len(self._cache) > self.max_size:
                self._cache.popitem(last=False)

    def delete(self, key: str) -> None:
        with self._lock:
            if key in self._cache:
                del self._cache[key]

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
