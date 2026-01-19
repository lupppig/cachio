import asyncio
import httpx
import logging
from typing import List
from cachio.wrappers import HttpxCacheClient
from cachio.backends import AsyncInMemoryCache
from scripts.simulation.chaos import ChaosBackend

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("simulation")

async def worker(client, url, n):
    for _ in range(n):
        try:
            resp = await client.get(url)
            logger.info(f"Status: {resp.status_code} Source: {resp.headers.get('X-Cache', 'network')}")
        except Exception as e:
            logger.error(f"Request failed: {e}")

async def main():
    # Setup: 100% fail rate for chaos backend to guarantee failure logic testing
    # Stack: Memory (Good) -> Chaos (Bad) -> Network
    # If Memory misses, it hits Chaos. Chaos will throw Error.
    # Currently: HTTPCache should propagate Crash.
    
    # We use empty memory cache to force miss to next tier
    memory = AsyncInMemoryCache() 
    chaos = ChaosBackend(AsyncInMemoryCache(), failure_rate=1.0) # Always fails
    
    # Tiered logic not fully implemented for Async Backends list yet in runner?
    # HttpxCacheClient takes list of backends.
    
    async with HttpxCacheClient(backends=[memory, chaos]) as client:
        # 1. First fetch - Miss Memory -> Hit Chaos -> Crash?
        print("Starting simulation...")
        try:
            await client.get("http://localhost:8082/fast")
            print("SUCCESS: Survived Chaos Backend!")
        except Exception as e:
            print(f"FAILURE: Crashed as expected! Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
