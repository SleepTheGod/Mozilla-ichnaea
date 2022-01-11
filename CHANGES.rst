=========
Changelog
=========

See the
`tags page <https://github.com/mozilla/ichnaea/tags>`_
for releases after November 2019.

See the
`releases page <https://github.com/mozilla/ichnaea/releases>`_
for releases from August 2017 to August 2019.

2.2.0 (2017-08-23)
==================

Migrations
~~~~~~~~~~

- a0ee5e10f44b: Remove allow_transfer column from API key table.

- 138cb0d71dfb: Drop cell OCID tables.

- 5797389a3842: Add fallback_schema column to API key table.

- 30a4df7eafd5: Add allow_region column to API key table.

- 73c5f5ae5b23: Drop shortname column from API key table.

Changes
~~~~~~~

- Remove unfinished transfer HTTP API.

- #508: Add support for unwiredlabs as a fallback provider.

- Combine rate limit and unique IP counting into one Redis call.

- Add new cleanup stat task.

- Remove the monitor queue size task.

- Check API keys for region requests.

- Avoid filling the datamap queues if the web content is disabled.

- Internal optmization in SQL export queries.


2.1.0 (2017-06-27)
==================

Compatibility
~~~~~~~~~~~~~

- Move back to Celery 3.

- Drop support for Python 2.7, require Python 3.6.

Changes
~~~~~~~

- Rely on `cleanup_datamap` task to remove old datamap entries.

- Use mysql-connector for datamap and local dump script.

- Remove tabzilla, update web site style.

- Add Zilla Slab font files, remove non-woff fonts.

- Replace custom base map with `mapbox.dark`.

- Update CSS/JS dependencies.

- Replace bower in CSS/JS dev setup with npm.

- Install MySQL 5.7 and Redis command line utilities.

- Remove radio field workaround in cell locate API.

- Adjust the text on the download and stats pages.

- Use SQLAlchemy core instead of ORM in various places.


2.0 (2017-03-22)
================

Compatibility
~~~~~~~~~~~~~

- Application configuration moved to environment variables.

- Moved initial database schema creation into an alembic migration.

- Test against Redis 3.2 instead of 2.8.

- Test against MySQL 5.7 instead of 5.6.

- No longer create `lbcheck` database user in `location_initdb` script.

- Drop support for Python 2.6.

Migrations
~~~~~~~~~~

- d2d9ecb12edc: Add modified index on `datamap_*` tables.

- cad2875fd8cb: Add `store_sample_*` columns to api_key table.

- Removed old migrations. The database needs to be at least at version
  `1bdf1028a085` or `385f842b2526` before upgrading to this version.

Changes
~~~~~~~

- #496: Don't store queries if all networks where seen today.

- #492: Add new datamap cleanup task to delete old datamap rows.

- Update to botocore/boto3.

- No longer use secondary cell tables during lookups.

- Remove continous cell import functionality.

- Relax GeoIP database check to allow `GeoLite2-City` databases.

- Update region specific statistics once per day.

- Add in-memory API key cache.

- Add `/contribute.json` view.

- Update to Celery 4.

- Remove `/leaders` HTTP redirects.

- Replace the `/apps` page with a link to the Wiki.
