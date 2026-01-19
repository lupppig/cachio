import json
from typing import Dict, Any, Optional
import redis
from ..interfaces import CacheBackend

class RedisBackend:
    def __init__(self, host: str, port: int, password: Optional[str] = None, **kwargs: Any):
        self.redis = redis.StrictRedis(
            host=host,
            port=port,
            password=password,
            decode_responses=True,
            **kwargs
        )

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        val = self.redis.get(key)
        if not val:
            return None
        try:
            if isinstance(val, str):
                 return json.loads(val)
        except json.JSONDecodeError:
            pass
        return None

    def set(self, key: str, value: Dict[str, Any], ttl: Optional[int] = None) -> None:
        val = json.dumps(value)
        self.redis.set(key, val, ex=ttl)

    def delete(self, key: str) -> None:
        self.redis.delete(key)

    def clear(self) -> None:
        self.redis.flushdb()
