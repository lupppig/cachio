import json
from typing import Dict, Any, Optional

try:
    from pymemcache.client.base import Client  # type: ignore
except ImportError:
    Client = None

from ..interfaces import CacheBackend

class MemcachedBackend:
    def __init__(self, host: str, port: int, **kwargs: Any):
        if Client is None:
            raise ImportError("pymemcache is required for MemcachedBackend. Install it with `pip install pymemcache`.")
        
        self.client = Client((host, port), **kwargs)

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        val = self.client.get(key)
        if val is None:
            return None
        
        try:
            if isinstance(val, bytes):
                val = val.decode('utf-8')
            return json.loads(val)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None

    def set(self, key: str, value: Dict[str, Any], ttl: Optional[int] = None) -> None:
        val = json.dumps(value)
        expire = ttl if ttl is not None else 0
        self.client.set(key, val, expire=expire)

    def delete(self, key: str) -> None:
        self.client.delete(key)

    def clear(self) -> None:
        self.client.flush_all()
