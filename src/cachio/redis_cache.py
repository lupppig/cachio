import json

import redis

from .cache import Cache


class RedisCache(Cache):
    def __init__(
        self,
        host: str,
        port: int,
        password: str = "",
        **extra_conn,
    ):
        self.host = host
        self.port = port
        self.password = password
        self.red = None
        if extra_conn:
            self.red = redis.StrictRedis(
                host=self.host,
                port=self.port,
                password=self.password,
                **extra_conn,
            )
        else:
            self.red = redis.StrictRedis(
                host=self.host,
                port=self.port,
                password=self.password,
            )
        if self.red:
            try:
                self.red.ping()
                print("redis connection successful")
            except redis.ConnectionError:
                print("Unable to connect to redis")
                return

    def set(self, cache_keys: str, cache_entry):
        if self.red:
            j_data = json.dumps(cache_entry)
            self.red.set(cache_keys, j_data)

    def get(self, cache_keys: str):
        if self.red:
            data = self.red.get(cache_keys)
            if not data:
                return None
            s_data = json.loads(data)
            return s_data

    def delete(self, cache_keys: str):
        if self.red:
            self.red.delete(cache_keys)
