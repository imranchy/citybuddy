# CityBuddy ingestion

CityBuddy ingestion is configuration-driven and safe by default. Commands
preview changes unless `--apply` is explicitly supplied.

Run commands from `backend` with the virtual environment active.

## Staging control plane

The staging workflow is the supported foundation for scheduled collection.
Collection and production promotion are deliberately separate operations.
Neither a scheduled job nor a future LLM agent can promote arbitrary records.

Apply the latest migration before using the staging commands:

```cmd
alembic upgrade head
```

Preview an OSM collection without writing anything:

```cmd
python -m scripts.collect_osm_staging --city turin --category museum --limit 20
```

Preview every discovery category with a manageable, deterministic cap per
category:

```cmd
python -m scripts.collect_osm_staging --city turin --limit-per-category 50
```

Write the same source results to staging only:

```cmd
python -m scripts.collect_osm_staging --city turin --category museum --limit 20 --apply
```

Jobs invoked by a deployment scheduler use the same command and record their
trigger explicitly:

```cmd
python -m scripts.collect_osm_staging --city turin --category museum --trigger scheduled --apply
```

For one manual or scheduled command that collects all place categories and
licensed images for existing production places, use:

```cmd
python -m scripts.run_city_collection --city turin --place-limit-per-category 50 --image-limit 100
```

After reviewing both previews, the scheduler can write both result sets to
staging with:

```cmd
python -m scripts.run_city_collection --city turin --place-limit-per-category 50 --image-limit 100 --trigger scheduled --apply
```

This command never promotes places or images into production.

All-category OSM collection batches the configured selectors into the eight
CityBuddy discovery groups. This substantially reduces public Overpass request
volume. If one group exhausts all configured Overpass endpoints, candidates
from successful groups are still written to staging and the run records both
`successful_source_groups` and `failed_source_groups`. A failed group is
inconclusive and remains pending for a later collection; it is never treated as
evidence that the city has zero places in that group. If every group fails, the
run is marked failed and no place candidates are staged.

Public Overpass instances can return `429`, `502`, or `504` responses. The
collector retries across configured instances and temporarily cools down an
endpoint after a `429`. Avoid immediately repeating preview and apply runs,
because each command performs a fresh source collection.

The scheduling platform should run one collection at the chosen daily time.
Scheduling remains outside the application process so restarting FastAPI does
not create duplicate timers. Each applied run is recorded in `ingestion_runs`.

Inspect all candidates and validation findings from a completed run:

```cmd
python -m scripts.report_staged_places --run-id 12
```

Preview an explicitly reviewed promotion batch:

```cmd
python -m scripts.promote_staged_places --staged-id 101 --staged-id 102
```

Apply the exact same approved IDs only after reviewing the preview:

```cmd
python -m scripts.promote_staged_places --staged-id 101 --staged-id 102 --apply
```

For large all-category runs, preview every deterministically valid, pending
record as one reviewed batch:

```cmd
python -m scripts.promote_staged_places --run-id 12 --all-eligible
```

Apply that run-level selection only after checking its category summary:

```cmd
python -m scripts.promote_staged_places --run-id 12 --all-eligible --apply
```

Candidates with lifecycle warnings require the additional explicit
`--approve-warnings` flag. Invalid candidates cannot be promoted. Existing
production source IDs are skipped instead of overwritten. Promotion batches
are recorded for audit purposes. Missing addresses, temporary names, duplicate
names within a run, and names matching another production record are classified
as `review_required` and excluded from the default bulk selection.

The older `import_osm_places` command remains available for existing manual
workflows, but automated collection should use `collect_osm_staging`; scheduled
jobs must never call a direct production importer.

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

The supported automated workflow writes images to staging first. Preview
licensed image candidates for every image-eligible category:

```cmd
python -m scripts.collect_wikimedia_staging --city turin --limit 100
```

Write the same collection to image staging only:

```cmd
python -m scripts.collect_wikimedia_staging --city turin --limit 100 --apply
```

The collector follows explicit OSM Wikidata identifiers to Wikidata P18 and
then Wikimedia Commons. It validates Wikimedia hosts, source identifiers,
attribution, licenses, and license URLs. Places that already have a Commons
image are skipped.

Review an image run summary, then request details when needed:

```cmd
python -m scripts.report_staged_images --run-id 13
python -m scripts.report_staged_images --run-id 13 --show-details
```

Preview and apply all valid pending images from the reviewed run:

```cmd
python -m scripts.promote_staged_images --run-id 13 --all-eligible
python -m scripts.promote_staged_images --run-id 13 --all-eligible --apply
```

Image promotion remains a separate, explicit production operation. Existing
Commons images are never overwritten, and a promoted image becomes primary
only when the place has no existing image.

### Legacy direct image importer

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

The direct importer remains available for compatibility, but scheduled jobs
must use `collect_wikimedia_staging` instead.

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

## Milestone C bounded ingestion agents

CityBuddy now has three bounded operational roles built on the existing staging
control plane rather than a parallel ingestion system:

1. **Discovery role** — `collect_osm_staging`, `collect_wikimedia_staging`, and
   `run_city_collection` collect approved sources into staging only. Wikimedia
   collection continues to revisit production places that lack Commons images.
2. **Review / enrichment role** — `review_staged_candidates` runs deterministic
   validation first. Only `review_required` candidates call Qwen; Qwen may
   escalate genuine ambiguity once to Gemma. The result is an advisory
   `agent_review_decisions` record and never a production write authorization.
3. **Indexing role** — `index_place_evidence` keeps the existing fingerprinted,
   incremental bge-m3 path and therefore embeds only new or changed reviewed
   production evidence.

Apply the latest migration before persisting agent review decisions:

```cmd
alembic upgrade head
```

Preview bounded review for one staging run. Start with a small real-data smoke
batch before reviewing a large run:

```cmd
python -m scripts.review_staged_candidates --run-id 12 --limit 10
```

Offline ingestion review uses a minimum 90-second Ollama timeout by default,
without changing the latency-oriented assistant timeout. Override it only for a
specific review run with `--timeout-seconds`. Each candidate is attempted twice
by default; a repeated local-model failure is reported as `model_error_pending`
and the runner continues to the next candidate instead of aborting the batch.

Persist review metadata only (still no production promotion):

```cmd
python -m scripts.review_staged_candidates --run-id 12 --apply
```

Applied decisions are committed incrementally. Re-running the command skips an
already-persisted decision for the same staged candidate fingerprint, so an
interrupted review batch can resume without repeating successful model work.

By default deterministically valid rows are skipped to avoid unnecessary model
work. Add `--include-valid` if an audit run should persist those deterministic
approval decisions too. Deterministically invalid rows never call an LLM and are
always rejected by the review graph.

The graph has a hard Qwen -> optional Gemma escalation bound. A second
`escalate` decision terminates conservatively as a rejection for later human
review, so agent loops cannot become unbounded.

Agent decisions are deliberately separate from promotion. Existing
`promote_staged_places` and `promote_staged_images` commands remain the only
production publication boundary and retain their validation/explicit-approval
requirements.

Report current primary-image coverage at any time:

```cmd
python -m scripts.report_image_coverage --city turin
```

Include one image staging run's validation/promotion counts:

```cmd
python -m scripts.report_image_coverage --city turin --run-id 13
```

This provides the Milestone C coverage baseline without exposing image license
or provenance metadata in the user-facing assistant UI.

## Official-site knowledge refresh

The daily refresh also has a bounded official-document indexing role for relatively
stable visitor knowledge. `index_official_documents` starts only from reviewed
production places that already have an official website stored by CityBuddy. The
caller/model never supplies a URL. Retrieval reuses the official-site security
boundary: HTTP(S) only, public DNS/IPs, same reviewed domain, same-domain links,
bounded responses, sanitized text, and isolated source failures.

The first supported stable document topics are accessibility, visitor services,
permanent collections/highlights, shopping directories/collections, and dietary
policy information. Volatile facts such as today's opening status, current menu
items/prices, temporary closures, and current availability remain live-tool facts
and are not treated as durable RAG knowledge.

Each successful official document chunk is stored in `place_evidence` with its
place ID, content type, exact official source URL, fetch timestamp, fingerprint,
and embedding model. The source ID is application-owned and stable per topic/chunk.
Only new or fingerprint-changed chunks are sent to bge-m3. A successfully refreshed
topic may retire superseded chunk tails; a failed retrieval never deletes the last
known evidence for that topic.

Preview a small batch before applying it:

```cmd
python -m scripts.index_official_documents --city Torino --place-limit 2
```

Apply only after the preview looks reasonable:

```cmd
python -m scripts.index_official_documents --city Torino --place-limit 2 --apply
```

The normal daily runner invokes this phase automatically. It can be disabled for a
specific run with `--skip-official-docs` or bounded with
`--official-doc-place-limit` during smoke testing.

This phase deliberately does not yet convert prose into typed production place
columns. Structured fact extraction is a separate safety boundary: it should use a
small schema, deterministic validation, advisory Qwen review only when necessary,
and application-owned promotion before any database field is changed.
