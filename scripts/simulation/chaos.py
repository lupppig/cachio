import random
from typing import Dict, Any, Optional
from cachio.interfaces import AsyncCacheBackend

class ChaosBackend(AsyncCacheBackend):
    def __init__(self, backend: AsyncCacheBackend, failure_rate: float = 0.5):
        self.backend = backend
        self.failure_rate = failure_rate

    async def _maybe_fail(self):
        if random.random() < self.failure_rate:
            raise ConnectionError("Chaos Monkey struck!")

    async def get(self, key: str) -> Optional[Dict[str, Any]]:
        await self._maybe_fail()
        return await self.backend.get(key)

    async def set(self, key: str, value: Dict[str, Any], ttl: Optional[int] = None) -> None:
        await self._maybe_fail()
        await self.backend.set(key, value, ttl)

    async def delete(self, key: str) -> None:
        await self._maybe_fail()
        await self.backend.delete(key)

    async def clear(self) -> None:
        await self._maybe_fail()
        await self.backend.clear()
