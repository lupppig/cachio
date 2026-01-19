from typing import Protocol, Optional, Any, Dict, runtime_checkable

@runtime_checkable
class CacheBackend(Protocol):
    """
    Protocol for synchronous cache backends.
    """
    def get(self, key: str) -> Optional[Dict[str, Any]]: 
        """Retrieve a value by key."""
        ...
    def set(self, key: str, value: Dict[str, Any], ttl: Optional[int] = None) -> None: 
        """Set a value by key with optional TTL."""
        ...
    def delete(self, key: str) -> None: 
        """Delete a key."""
        ...
    def clear(self) -> None: 
        """Clear the cache."""
        ...

@runtime_checkable
class AsyncCacheBackend(Protocol):
    """
    Protocol for asynchronous cache backends.
    """
    async def get(self, key: str) -> Optional[Dict[str, Any]]: 
        """Retrieve a value by key."""
        ...
    async def set(self, key: str, value: Dict[str, Any], ttl: Optional[int] = None) -> None: 
        """Set a value by key with optional TTL."""
        ...
    async def delete(self, key: str) -> None: 
        """Delete a key."""
        ...
    async def clear(self) -> None: 
        """Clear the cache."""
        ...
