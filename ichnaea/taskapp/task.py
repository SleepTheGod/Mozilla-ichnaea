"""
Contains a Celery base task.
"""

from celery import Task
from kombu.serialization import dumps as kombu_dumps, loads as kombu_loads
import markus

from ichnaea.cache import redis_pipeline
from ichnaea.conf import settings
from ichnaea.db import db_worker_session


METRICS = markus.get_metrics()


class BaseTask(Task):
    """A base task giving access to various outside connections."""

    _countdown = None
    _enabled = True
    _schedule = None
    _shard_model = None

    _auto_retry = True
    _shortname = None

    def __init__(self):
        self._shortname = self.shortname()

    @classmethod
    def shortname(cls):
        """
        A short name for the task, used in statsd metric names.
        """
        short = cls._shortname
        if short is None:
            # strip off ichnaea prefix and tasks module
            segments = cls.name.split(".")
            segments = [s for s in segments if s not in ("ichnaea", "tasks")]
            short = ".".join(segments)
        return short

    @classmethod
    def beat_config(cls):
        """
        Returns the beat schedule for this task, taking into account
        the optional shard_model to create multiple schedule entries.
        """
        if cls._shard_model is None:
            return {cls.shortname(): {"task": cls.name, "schedule": cls._schedule}}

        result = {}
        for shard_id in cls._shard_model.shards().keys():
            result[cls.shortname() + "_" + shard_id] = {
                "task": cls.name,
                "schedule": cls._schedule,
                "kwargs": {"shard_id": shard_id},
            }
        return result

    @classmethod
    def on_bound(cls, app):
        # Set up celery beat entry after celery app initialization is done.
        enabled = cls._enabled
        if callable(enabled):
            enabled = enabled()

        if enabled and cls._schedule:
            app.conf.beat_schedule.update(cls.beat_config())

    def __call__(self, *args, **kw):
        """
        Execute the task, capture a statsd timer for the task duration and
        automatically report exceptions into Sentry.
        """
        with METRICS.timer("task", tags=["task:" + self.shortname()]):
            try:
                result = super(BaseTask, self).__call__(*args, **kw)
            except Exception as exc:
                self.raven_client.captureException()
                if self._auto_retry and not settings("testing"):
                    raise self.retry(exc=exc)
                raise
        return result

    def apply(self, *args, **kw):
        """
        This method is only used when calling tasks directly and blocking
        on them. It's also used if always_eager is set, like in tests.

        If always_eager is set, we feed the task arguments through the
        de/serialization process to make sure the arguments can indeed
        be serialized into JSON.
        """
        if settings("testing"):
            # We do the extra check to make sure this was really used from
            # inside tests
            serializer = self.app.conf.task_serializer
            content_type, encoding, data = kombu_dumps(args, serializer)
            args = kombu_loads(data, content_type, encoding)

        return super(BaseTask, self).apply(*args, **kw)

    def apply_countdown(self, args=None, kwargs=None):
        """
        Run the task again after the task's default countdown.
        """
        self.apply_async(countdown=self._countdown, args=args, kwargs=kwargs)

    def db_session(self, commit=True, isolation_level=None):
        """
        Returns a database session usable as a context manager.

        :param commit: Should the session be committed or aborted at the end?
        :type commit: bool
        :param isolation_level: Set a new transaction isolation level for this session
        """
        return db_worker_session(
            self.app.db, commit=commit, isolation_level=isolation_level
        )

    def redis_pipeline(self, execute=True):
        """
        Returns a Redis pipeline usable as a context manager.

        :param execute: Should the pipeline be executed or aborted at the end?
        :type execute: bool
        """
        return redis_pipeline(self.redis_client, execute=execute)

    @property
    def geoip_db(self):
        """Exposes a :class:`~ichnaea.geoip.GeoIPWrapper`."""
        return self.app.geoip_db

    @property
    def raven_client(self):
        """Exposes a :class:`~raven.Client`."""
        return self.app.raven_client

    @property
    def redis_client(self):
        """Exposes a :class:`~ichnaea.cache.RedisClient`."""
        return self.app.redis_client
