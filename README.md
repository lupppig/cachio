# cachio

**cachio** is an HTTP caching library for Python that enables efficient storage and retrieval of HTTP responses in both memory and on disk. It is designed to improve performance, reduce redundant network requests, and support persistent caching.

## Features

* **In-Memory Cache**
  Store responses in memory for fast, low-latency retrieval.

* **Disk Cache**
  Persist responses on disk for long-lived caching across sessions.

* **LRU Eviction**
  Implements a Least Recently Used (LRU) strategy to manage cache size and memory usage effectively.

* **Full Response Storage**
  Maintains the complete HTTP response, including headers, status code, and raw body content.

## Use Cases

* **Web Crawlers**
  Prevent re-downloading the same pages multiple times.

* **API Clients**
  Reduce API call frequency and improve response times.

* **Testing**
  Replay cached responses to simulate server behavior without hitting external services.

* **Offline Access**
  Access previously fetched data even when a network connection is unavailable.

## Installation

```bash
pip install cachio
```
or if using uv


```bash
uv add  cachio
```

## Example Usage

```python
from cachio import HTTPCache, InMemoryCache, DiskBackend, RedisBackend

if __name__ == "__main__":
    # Tiered caching: Memory -> Disk -> Redis
    backends = [
        InMemoryCache(max_size=100),
        DiskBackend(cache_dir=".cache"),
        RedisBackend(host="localhost", port=6379)
    ]
    cache = HTTPCache(backends=backends)

    # First request hits network, subsequent ones hit cache
    response = cache.get("https://www.example.com")
    print(f"Status: {response.status_code}, Source: {response.headers.get('X-Cache')}")
```

## Async Support

### Httpx

```python
import asyncio
from cachio.wrappers import HttpxCacheClient
from cachio.backends import AsyncInMemoryCache

async def main():
    async with HttpxCacheClient(backends=[AsyncInMemoryCache()]) as client:
        await client.get("https://example.com")

asyncio.run(main())
```

### Aiohttp

```python
import asyncio
from cachio.wrappers import AiohttpCacheSession
from cachio.backends import AsyncInMemoryCache

async def main():
    async with AiohttpCacheSession(backends=[AsyncInMemoryCache()]) as session:
        async with session.get("https://example.com") as resp:
            data = await resp.text()

asyncio.run(main())
```

## Architecture Overview

```
+------------------+
|   User Request   |
+--------+---------+
         |
         v
+------------------+      Cache Lookup
|  HTTPCache Core  |<--------------------+
+--------+---------+                     |
         |                               |
         v                               |
  +------+-------+      Miss             |
  | In-Memory LRU|---------------------->|
  +------+-------+                        |
         |                                |
         v                                |
  +------+-------+      Miss               |
  |   DiskCache  |------------------------>|
  +------+-------+                         |
         |                                 |
         v                                 |
  +------+-------+                         |
  |   HTTP Fetch |------------------------>|
  +--------------+                         
```

**NB:** I am unable to publish this package to PyPI. Please install it directly from the source or git repository.