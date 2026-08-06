# CityBuddy ingestion

CityBuddy ingestion is configuration-driven and safe by default. Commands
preview changes unless `--apply` is explicitly supplied.

Run commands from `backend` with the virtual environment active.

## Destination ingestion

Preview every configured destination category for Turin:

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

## Transport ingestion

Preview transport separately:

```cmd
python -m scripts.import_osm_places --city turin --layer transport --limit 20
```

Transport records are deliberately excluded from the destination APIs. Do not
apply the full transport import until the dedicated transport API and map toggle
are ready.

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
Destination and transport categories must remain in separate layers.
