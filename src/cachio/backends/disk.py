import json
from typing import Dict, Any, Optional
import diskcache as dc
from ..interfaces import CacheBackend

class DiskBackend:
    def __init__(self, cache_dir: str, **kwargs: Any):
        self.cache = dc.Cache(cache_dir, **kwargs)

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        val = self.cache.get(key)
        if val is None:
            return None
        if isinstance(val, str):
            try:
                return json.loads(val)
            except json.JSONDecodeError:
                return None
        return val

    def set(self, key: str, value: Dict[str, Any], ttl: Optional[int] = None) -> None:
        try:
            val = json.dumps(value)
            self.cache.set(key, val, expire=ttl)
        except (TypeError, ValueError):
            raise

    def delete(self, key: str) -> None:
        self.cache.delete(key)

    def clear(self) -> None:
        self.cache.clear()
