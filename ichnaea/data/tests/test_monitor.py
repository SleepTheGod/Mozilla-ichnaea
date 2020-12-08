from datetime import timedelta
import random

from ichnaea.data.tasks import (
    monitor_api_key_limits,
    monitor_api_users,
    monitor_queue_size,
    sentry_test,
)
from ichnaea import util


class TestMonitorApiKeys:
    def test_monitor_api_keys_empty(self, celery, metricsmock):
        monitor_api_key_limits.delay().get()
        metricsmock.assert_not_gauge("api.limit")

    def test_monitor_api_keys_one(self, celery, redis, metricsmock):
        today = util.utcnow().strftime("%Y%m%d")
        rate_key = "apilimit:no_key_1:v1.geolocate:" + today
        redis.incr(rate_key, 13)

        monitor_api_key_limits.delay().get()
        metricsmock.assert_gauge_once(
            "api.limit", value=13, tags=["key:no_key_1", "path:v1.geolocate"]
        )

    def test_monitor_api_keys_multiple(self, celery, redis, metricsmock):
        now = util.utcnow()
        today = now.strftime("%Y%m%d")
        yesterday = (now - timedelta(hours=24)).strftime("%Y%m%d")
        data = {
            "test": {"v1.search": 11, "v1.geolocate": 13},
            "no_key_1": {"v1.search": 12},
            "no_key_2": {"v1.geolocate": 15},
        }
        for key, paths in data.items():
            for path, value in paths.items():
                rate_key = "apilimit:%s:%s:%s" % (key, path, today)
                redis.incr(rate_key, value)
                rate_key = "apilimit:%s:%s:%s" % (key, path, yesterday)
                redis.incr(rate_key, value - 10)

        # add some other items into Redis
        redis.lpush("default", 1, 2)
        redis.set("cache_something", "{}")

        monitor_api_key_limits.delay().get()
        metricsmock.assert_gauge_once(
            "api.limit", value=13, tags=["key:test", "path:v1.geolocate"]
        )
        metricsmock.assert_gauge_once(
            "api.limit", value=11, tags=["key:test", "path:v1.search"]
        )
        metricsmock.assert_gauge_once(
            "api.limit", value=12, tags=["key:no_key_1", "path:v1.search"]
        )
        metricsmock.assert_gauge_once(
            "api.limit", value=15, tags=["key:no_key_2", "path:v1.geolocate"]
        )


class TestMonitorAPIUsers:
    @property
    def today(self):
        return util.utcnow().date()

    @property
    def today_str(self):
        return self.today.strftime("%Y-%m-%d")

    def test_empty(self, celery, metricsmock):
        monitor_api_users.delay().get()
        metricsmock.assert_not_gauge("submit.user")
        metricsmock.assert_not_gauge("locate.user")

    def test_one_day(self, celery, geoip_data, redis, metricsmock):
        bhutan_ip = geoip_data["Bhutan"]["ip"]
        london_ip = geoip_data["London"]["ip"]
        redis.pfadd("apiuser:submit:test:" + self.today_str, bhutan_ip, london_ip)
        redis.pfadd("apiuser:submit:valid_key:" + self.today_str, bhutan_ip)
        redis.pfadd("apiuser:locate:valid_key:" + self.today_str, bhutan_ip)

        monitor_api_users.delay().get()
        metricsmock.assert_gauge_once(
            "submit.user", value=2, tags=["key:test", "interval:1d"]
        )
        metricsmock.assert_gauge_once(
            "submit.user", value=2, tags=["key:test", "interval:7d"]
        )
        metricsmock.assert_gauge_once(
            "submit.user", value=1, tags=["key:valid_key", "interval:1d"]
        )
        metricsmock.assert_gauge_once(
            "submit.user", value=1, tags=["key:valid_key", "interval:7d"]
        )
        metricsmock.assert_gauge_once(
            "locate.user", value=1, tags=["key:valid_key", "interval:1d"]
        )
        metricsmock.assert_gauge_once(
            "locate.user", value=1, tags=["key:valid_key", "interval:7d"]
        )

    def test_many_days(self, celery, geoip_data, redis, metricsmock):
        bhutan_ip = geoip_data["Bhutan"]["ip"]
        london_ip = geoip_data["London"]["ip"]
        days_6 = (self.today - timedelta(days=6)).strftime("%Y-%m-%d")
        days_7 = (self.today - timedelta(days=7)).strftime("%Y-%m-%d")
        redis.pfadd("apiuser:submit:test:" + self.today_str, "127.0.0.1", bhutan_ip)
        # add the same IPs + one new one again
        redis.pfadd("apiuser:submit:test:" + days_6, "127.0.0.1", bhutan_ip, london_ip)
        # add one entry which is too old
        redis.pfadd("apiuser:submit:test:" + days_7, bhutan_ip)

        monitor_api_users.delay().get()
        metricsmock.assert_gauge_once(
            "submit.user", value=2, tags=["key:test", "interval:1d"]
        )
        # We count unique IPs over the entire 7 day period, so it's just 3 uniques.
        metricsmock.assert_gauge_once(
            "submit.user", value=3, tags=["key:test", "interval:7d"]
        )

        # the too old key was deleted manually
        assert not redis.exists("apiuser:submit:test:" + days_7)


class TestMonitorQueueSize:
    def test_empty_queues(self, celery, redis, metricsmock):
        data = {name: 0 for name in celery.all_queues}

        monitor_queue_size.delay().get()
        for key, val in data.items():
            metricsmock.assert_gauge_once("queue", value=0, tags=["queue:" + key])

    def test_nonempty(self, celery, redis, metricsmock):
        data = {}
        for name in celery.all_queues:
            data[name] = random.randint(1, 10)

        for key, val in data.items():
            redis.lpush(key, *range(val))

        monitor_queue_size.delay().get()
        for key, val in data.items():
            metricsmock.assert_gauge_once("queue", value=val, tags=["queue:" + key])


class TestSentryTest:
    def test_basic(self, celery, raven_client):
        sentry_test.delay(msg="test message")
        msgs = [item["message"] for item in raven_client.msgs]
        assert msgs == ["test message"]

        raven_client._clear()
