# httpcache

**httpcache** is an HTTP caching library for Python that enables efficient storage and retrieval of HTTP responses in both memory and on disk. It is designed to improve performance, reduce redundant network requests, and support persistent caching.

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
pip install httpcache
```

## Example Usage

```python
from diskcache import Cache
from httpcache import HTTPCache

if __name__ == "__main__":
    c = Cache("cache")
    cache = HTTPCache(storage=c)

    response = cache.get("https://www.example.com/index.html")
```

**Notes:**

* The first request fetches the response from the network.
* Subsequent requests for the same URL are served from the cache.
* You can replace `Cache("cache")` with an in-memory cache if persistence is not required.

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

**Description:**

1. **In-Memory LRU Cache:** Fast retrieval for frequently accessed responses.
2. **Disk Cache:** Fallback for responses that are no longer in memory but were cached previously.
3. **HTTP Fetch:** Only triggered if the response is not available in memory or disk.

## NB: This repo is under construction and isn't suitable for production yet...