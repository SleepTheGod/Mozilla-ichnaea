"""
Functionality related to custom Redis based queues.
"""

import json

from ichnaea.cache import redis_pipeline
from ichnaea import util


class DataQueue(object):
    """
    A Redis based queue which stores binary or JSON encoded items
    in lists. The queue uses a single static queue key.

    The lists maintain a TTL value corresponding to the time data has
    been last put into the queue.
    """

    queue_ttl = 86400  # Maximum TTL value for the Redis list.
    queue_max_age = 3600  # Maximum age that data can sit in the queue.

    def __init__(
        self, key, redis_client, data_type, batch=0, compress=False, json=True
    ):
        self.key = key
        self.redis_client = redis_client
        self.batch = batch
        self.compress = compress
        self.json = json
        self.tags = {"queue_type": "data", "data_type": data_type}

    def dequeue(self, batch=None):
        """
        Get batch number of items from the queue.
        """
        if batch is None:
            batch = self.batch

        with self.redis_client.pipeline() as pipe:
            pipe.multi()
            pipe.lrange(self.key, 0, batch - 1)
            if batch != 0:
                pipe.ltrim(self.key, batch, -1)
            else:
                # special case for deleting everything
                pipe.ltrim(self.key, 1, 0)
            result = pipe.execute()[0]

            if self.compress:
                result = [util.decode_gzip(item) for item in result]
            if self.json:
                result = [json.loads(item.decode("utf-8")) for item in result]

        return result

    def _push(self, pipe, items, batch):
        for i in range(0, len(items), batch):
            pipe.rpush(self.key, *items[i : i + batch])

        # expire key after it was created by rpush
        pipe.expire(self.key, self.queue_ttl)

    def enqueue(self, items, batch=None, pipe=None):
        """
        Put items into the queue.

        The items will be pushed into Redis as part of a single (given)
        pipe in batches corresponding to the given batch argument.
        """
        if batch is None:
            batch = self.batch

        if batch == 0:
            batch = len(items)

        if self.json:
            items = [json.dumps(item).encode("utf-8") for item in items]

        if self.compress:
            items = [util.encode_gzip(item) for item in items]

        if pipe is not None:
            self._push(pipe, items, batch)
        else:
            with redis_pipeline(self.redis_client) as pipe:
                self._push(pipe, items, batch)

    def ready(self, batch=None):
        """
        Returns True if the queue has either more than a certain
        batch number of items in it, or if the last time it has seen
        new data was more than an hour ago (queue_max_age).
        """
        if batch is None:
            batch = self.batch

        with self.redis_client.pipeline() as pipe:
            pipe.ttl(self.key)
            pipe.llen(self.key)
            ttl, size = pipe.execute()
        if ttl < 0:
            age = -1
        else:
            age = max(self.queue_ttl - ttl, 0)
        return bool(size > 0 and (size >= batch or age >= self.queue_max_age))

    def size(self):
        """Return the size of the queue."""
        return self.redis_client.llen(self.key)
