# CityBuddy ingestion

CityBuddy ingestion is configuration-driven and safe by default. Commands
preview changes unless `--apply` is explicitly supplied.

Run commands from `backend` with the virtual environment active.

## Place ingestion

Preview every configured discovery category for Turin:

```cmd
python -m scripts.import_osm_places --city turin
```

Preview one category:

```cmd
python -m scripts.import_osm_places --city turin --category library
```

Apply a reviewed category import:

```cmd
python -m scripts.import_osm_places --city turin --category library --apply
```

Use `--limit 20` during small validation runs. The importer reports records
returned per category, new candidates, existing records, incomplete records,
and records deferred by the limit.

Inspect detailed OSM metadata before approving ambiguous categories:

```cmd
python -m scripts.import_osm_places --city turin --category market --show-details
```

Use `--source-id` to restrict a preview or import to explicitly reviewed OSM
elements. Repeat the option when approving multiple records.

Preview operational metadata refreshes for existing records:

```cmd
python -m scripts.import_osm_places --city turin --category market --source-id node/1314042685 --source-id way/25568763 --refresh-existing --show-details
```

Apply only after reviewing the exact same command without `--apply`:

```cmd
python -m scripts.import_osm_places --city turin --category market --source-id node/1314042685 --source-id way/25568763 --refresh-existing --show-details --apply
```

`--refresh-existing` updates only `opening_hours`, `website`, and `operator`.
It requires at least one explicitly approved `--source-id`. Preview mode never
writes database changes.

## Discovery taxonomy

Every record stores one stable leaf category. The application derives its
display group from `app/core/place_catalog.py`; category groups are not copied
into the database.

- Food & Drink
- Culture & Attractions
- Nature & Recreation
- Nightlife
- Shopping & Markets
- Learning & Community
- Places of Worship
- Accommodation

Public-transport stops are intentionally outside the CityBuddy catalog. The
future assistant may provide a key-free Google Maps transit directions link,
but it must not invent routes or departure times. It must also tell users that
routes, times, disruptions, and availability can change and should be verified.

## Wikimedia image enrichment

Preview images for a configured city:

```cmd
python -m scripts.import_wikimedia_images --city turin --limit 10
```

Apply a reviewed preview:

```cmd
python -m scripts.import_wikimedia_images --city turin --limit 10 --apply
```

For safer human-reviewed imports, explicitly select approved Wikidata matches
by repeating `--wikidata-id` for each reviewed entity.

Preview an approved allowlist without writing records:

```cmd
python -m scripts.import_wikimedia_images --city turin --wikidata-id Q3902364 --wikidata-id Q975240
```

Apply the same approved allowlist only after verifying its preview:

```cmd
python -m scripts.import_wikimedia_images --city turin --wikidata-id Q3902364 --wikidata-id Q975240 --apply
```

When one or more `--wikidata-id` options are supplied, all other Wikidata
mappings are excluded from both preview and import. Always preview the exact
same allowlist without `--apply` before writing image records.

## Duplicate report

Report same-name and same-category places within 100 metres:

```cmd
python -m scripts.report_place_duplicates --city turin
```

Adjust the reporting radius when investigating data quality:

```cmd
python -m scripts.report_place_duplicates --city turin --radius-metres 50
```

The report never modifies the database.

## Adding a city

Add a `CityConfig` entry to `app/core/cities.py` with its key, display name,
country code, bounding box, default language, and supported languages. Always
preview category counts before applying an import for a new city.

## Adding a category

Add the normalized category and its OSM selectors to
`app/core/place_catalog.py`, then extend `get_category()` with its tag mapping.
Assign each category one canonical display group and add tests for its OSM tag
normalization. Ambiguous categories should be previewed with `--show-details`
and imported only through an explicit reviewed source-ID allowlist.

## Post-deployment automation design

Keep automated collection separate from publication. A scheduled job may fetch
OSM and Wikimedia candidates into staging, run deterministic schema, duplicate,
lifecycle, attribution, and URL checks, and then ask an agent to rank or flag
records for review. Only approved source IDs should be promoted by the existing
allowlist-based import commands. Agents must never write arbitrary records
directly to production.

Recommended pipeline: fetch to staging, validate, agent-assisted review, human
approval, allowlisted promotion, audit report. Start with daily collection and
manual promotion; automate promotion only after quality thresholds and rollback
procedures have been proven in production.
