.. _deploy:

==========
Deployment
==========

.. Note:: 2022-01-06: In the process of being updated.

Mozilla deploys Ichnaea in an Amazon AWS environment, and there are some
optional dependencies on specific AWS services like Amazon S3. The
documentation assumes you are also using a AWS environment, but Ichnaea can be
run in non-AWS environments as well.

Mozilla's Production Deployment
===============================

Mozilla's deployment of Ichnaea looks something like this:

.. Source document:
.. https://docs.google.com/drawings/d/1v0Db941NtZQoaKYETHXNYMK9MvZx7FlIw5QzQiiI2fI/edit?usp=sharing

.. image:: deploy.png
   :height: 417px
   :width: 921px
   :scale: 75%
   :align: center
   :alt: Deployment Diagram

The required parts are:

* One or more **WebApp workers** running the user-facing web page and APIs.
  Mozilla uses 20 EC2 instances in an Auto Scaling Group (ASG), behind an
  Elastic Load Balancer (ELB).
* One or more **Async workers** that run Celery tasks that process
  observations, update the station database, create map tiles, export data, and
  other tasks.  Mozilla uses 5 EC2 instances in an ASG.
* A **Celery scheduler** to schedule periodic tasks. Mozilla uses an EC2 instance.
* A **MySQL or compatible database**, to store station data. Mozilla uses Amazon's
  Relational Database Service (RDS), MySQL 5.7, in Multi-AZ mode. The
  user-facing website does not write to a database, and reads from a read-only
  replica.
* A **Redis cache server**, for cached data, Celery tasks queues, and observation
  data pipelines. Mozilla uses Amazon's ElastiCache Redis, in Multi-AZ mode.

The optional parts are:

* An **S3 asset bucket** to store map tiles and public data like cell exports.
  Mozilla uses Cloudfront as a CDN in front of the asset bucket.
* An **S3 backup bucket** to store observation samples.
* An **Admin node**, to provide interactive access to the cluster and to run
  database migration. Mozilla uses an EC2 instance.
* **DNS entries** to publish on the Internet. Mozilla uses AWS's Route 53.

Optional parts not shown on the diagram:

* A **statsd-compatible metrics server**. Mozilla uses InfluxDB.
* A **log aggregator**. Mozilla uses Google Cloud Logging.
* **Sentry**, for aggregating captured exceptions.

MySQL / Amazon RDS
==================

The application is written and tested against MySQL 5.7.x or Amazon RDS
of the same versions. MariaDB 10.5 has also been tested in the development
environment.

The default configuration works for the most part, but ensure you are using
UTF-8 to store strings. For example in ``my.cnf``:

.. code-block:: ini

    [mysqld]
    character-set-server = utf8
    collation-server = utf8_general_ci
    init-connect='SET NAMES utf8'

The WebApp frontend role only needs access to a read-only version of the
database, for example a read-replica. The Async Worker backend role needs
access to the read-write primary database.

You need to create a database called `location` and a user with DDL
privileges for that database.

Mozilla's MLS deployment processes 500 milliom to 1,000 milliom observations
a day. We've had issues in the past with replica lag and transaction log sizes
(used disk space), and both should be monitored. We reduced replica lag to 2
seconds or less by increasing ``innodb_log_file_size`` from 125 MB to 2 GB.
See :doc:`/rate_control` for more information.

Redis / Amazon ElastiCache
==========================

The application uses Redis as a queue for the asynchronous task workers and
also uses it directly as a cache and to track API key rate limitations.

You can install a standard Redis or use Amazon ElastiCache (Redis).
The application is tested against Redis 3.2.


Amazon S3
=========

The application uses Amazon S3 for various tasks, including backup of
:term:`observations`, export of the aggregated cell table and hosting of
the data map image tiles.

All of these are triggered by asynchronous jobs and you can disable them
if you are not hosted in an AWS environment.

If you use Amazon S3 you might want to configure a lifecycle policy to
delete old export files after a couple of days and :term:`observation`
data after one year.


Statsd / Sentry
===============

The application uses Statsd to aggregate metrics and Sentry to log
exception messages.

To use Statsd and Sentry, you need to configure them via environment
variables as detailed in :ref:`the config section <config>`.

Installation of Statsd and Sentry are outside the scope of this documentation.


Image Tiles
===========

The code includes functionality to render out image tiles for a data map
of places where observations have been made.

You can trigger this functionality periodically via a cron job, by
calling the application container with the map argument.


Docker Config
=============

The :ref:`the development section <localdev>` describes how to set up an
environment used for working on and developing Ichnaea itself. For a
production install, you should use pre-packaged docker images, instead
of installing and setting up the code from Git.

Start by looking up the version number of the last stable release on
https://github.com/mozilla/ichnaea/releases.

Than get the corresponding docker image:

.. code-block:: bash

    docker pull mozilla/location:2.1.0

To test if the image was downloaded successfully, you can create a
container and open a shell inside of it:

.. code-block:: bash

    docker run -it --rm mozilla/location:2.1.0 shell

Close the container again, either via ``exit`` or ``Ctrl-D``.

Next up create the application config as a docker environment file,
for example called `env.txt`:

.. code-block:: ini

    DB_HOST=domain.name.for.mysql
    DB_USER=location
    DB_PASSWORD=secret
    GEOIP_PATH=/app/geoip/GeoLite2-City.mmdb
    REDIS_HOST=domain.name.for.redis
    SECRET_KEY=change_this_value_or_it_will_not_be_secret

You can use either a single database user with DDL/DML privileges
(`DB_USER` / `DB_PASSWORD`) or separate users for DDL, read-write and
read-only privileges as detailed in :ref:`the config section <config>`.


Database Setup
==============

The user with DDL privileges and a database called `location` need to
be created manually. If multiple users are used, the initial database
setup will create the read-only / read-write users.

Next up, run the initial database setup:

.. code-block:: bash

    docker run -it --rm --env-file env.txt \
        mozilla/location:2.1.0 alembic stamp base

And update the database schema to the latest version:

.. code-block:: bash

    docker run -it --rm --env-file env.txt \
        mozilla/location:2.1.0 alembic upgrade head

The last command needs to be run whenever you upgrade to a new version
of Ichnaea. You can inspect available database schema changes via
alembic with the `history` and `current` sub-commands.


GeoIP
=====

The application uses a Maxmind GeoIP City database for various tasks.
It works both with the commerically available and Open-Source GeoLite
databases in binary format.

You can download the
`GeoLite database <https://dev.maxmind.com/geoip/geoip2/geolite2/>`_ 
for free from MaxMind after
`signing up for a GeoLite2 account <https://www.maxmind.com/en/geolite2/signup>`_.

Download and untar the downloaded file. Put the `GeoLite2-City.mmdb`
into a directory accessible to docker (for example `/opt/geoip`).
The directory will get volume mounted into the running docker containers.

You can update this file on a regular basis. Typically once a month
is enough for the GeoLite database. Make sure to stop any containers
accessing the file before updating it and start them again afterwards.
The application code doesn't tolerate having the file being changed
underneath it.


Docker Runtime
==============

Finally you are ready to start containers for the three different
application roles.

There is a web frontend, a task worker and a task scheduler role.
The scheduler role is limited to a single running container. You need
to make sure to never have two containers for the scheduler running at
the same time. If you use multiple physical machines, the scheduler
must only run on one of them.

The web app and task worker roles both scale out and you can run
as many of them as you want. They internally look at the number of
available CPU cores in the docker container and run an appropriate
number of sub-processes. So you can run a single docker container
per physical/virtual machine.

All roles communicate via the database and Redis only, so can be run
on different virtual or physical machines. The task workers load
balance their work internally via data structures in Redis.

If you run multiple web frontend roles, you need to put a load balancer
in front of them. The application does not use any sessions or cookies,
so the load balancer can simply route traffic via round-robin.

You can configure the load balancer to use the `/__lbheartbeat__` HTTP
endpoint to check for application health.

If you want to use docker as your daemon manager run:

.. code-block:: bash

    docker run -d --env-file env.txt \
        --volume /opt/geoip:/app/geoip
        mozilla/location:2.1.0 scheduler

The `/opt/geoip` directory is the directory on the docker host, with
the `GeoLite2-City.mmdb` file inside it. The `/app/geoip/` directory
corresponds to the `GEOIP_PATH` config section in the `env.txt` file.

The two other roles are started in the same way:

.. code-block:: bash

    docker run -d --env-file env.txt \
        --volume /opt/geoip:/app/geoip
        mozilla/location:2.1.0 worker

    docker run -d --env-file env.txt \
        --volume /opt/geoip:/app/geoip
        -p 8000:8000/tcp
        mozilla/location:2.1.0 web

The web role can take an additional argument to map the port 8000 from
inside the container to port 8000 of the docker host machine.

You can put a web server (e.g. Nginx) in front of the web role and
proxy pass traffic to the docker container running the web frontend.


Runtime Checks
==============

To check whether or not the application is running, you can check the
web role, via:

.. code-block:: bash

    curl -i http://localhost:8000/__heartbeat__

This should produce output like::

    HTTP/1.1 200 OK
    Server: gunicorn/19.7.1
    Date: Tue, 04 Jul 2017 13:27:13 GMT
    Connection: close
    Access-Control-Allow-Origin: *
    Access-Control-Max-Age: 2592000
    Content-Type: application/json
    Content-Length: 125

    {"database": {"up": true, "time": 2},
     "geoip": {"up": true, "time": 0, "age_in_days": 389},
     "redis": {"up": true, "time": 0}}

The `__lbheartbeat__` endpoint has simpler output and doesn't check
the database / Redis backend connections. The application is designed
to degrade gracefully and continue to work with limited capabilities
without working database and Redis backends.

The `__version__` endpoint shows what version of the software is
currently running.

To test one of the HTTP API endpoints, you can use:

.. code-block:: bash

    curl -H "X-Forwarded-For: 81.2.69.192" \
        http://localhost:8000/v1/geolocate?key=test

This should produce output like::

    {"location": {"lat": 51.5142, "lng": -0.0931}

Test this with different IP addresses like `8.8.8.8` to make sure
the database file was picked up correctly.


Upgrade
=======

In order to upgrade a running installation of Ichnaea to a new version,
first check and get the docker image for the new version, for example:

.. code-block:: bash

    docker pull mozilla/location:2.2.0

Next up stop all containers running the scheduler and task worker roles.
If you use docker's own daemon support, the `ps`, `stop` and `rm` commands
can be used to accomplish this.

Now run the database migrations found in the new image:

.. code-block:: bash

    docker run -it --rm --env-file env.txt \
        mozilla/location:2.2.0 alembic upgrade head

The web app role can work with both the old database and new database
schemas. The worker role might require the new database schema right
away.

Start containers for the scheduler, worker and web roles based on the
new image.

Depending on how you run your web tier, swich over the traffic from
the old web containers to the new ones. Once all traffic is going to
the new web containers, stop the old web containers.
