import json

import redis

from httpcache import Cache


class RedisCache(Cache):
    def __init__(
        self,
        host: str,
        port: int,
        password: str = "",
        **kwargs,
    ):
        self.host = host
        self.port = port
        self.password = password
        self.red = None
        if kwargs:
            self.red = redis.StrictRedis(
                host=self.host, port=self.port, password=self.password, **kwargs
            )
        else:
            self.red = redis.StrictRedis(
                host=self.host, port=self.port, password=self.password, **kwargs
            )
        if self.red:
            try:
                self.red.ping()
                print("redis connection successful")
            except redis.ConnectionError:
                print("Unable to connect to redis")
                return

    def set(self, cache_key: str, data):
        j_data = json.dumps(data)
        self.red.set(cache_key, j_data)

    def get(self, cache_key: str):
        data = self.red.get(cache_key)
        s_data = json.loads(data)
        return s_data

    def delete(self, cache_key: str):
        self.red.delete(cache_key)
