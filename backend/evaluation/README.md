# CityBuddy Production Evaluation

CityBuddy keeps one canonical, versioned evaluation tree under `backend/evaluation`.
Small frozen benchmark fixtures are committed to Git so model and prompt changes can be
regression-tested reproducibly. Larger future corpora and generated run artifacts can be
mirrored to S3 without changing the local dataset schema.

## Layout

```text
evaluation/
  datasets/
    legacy/                 # historical fixtures retained for reproducibility
    v1/                     # frozen production benchmark fixtures
      planner_intent_v1.csv
      planner_intent_v1.jsonl
      capability_suite_v1.csv
      capability_suite_v1.jsonl
      dataset_manifest.csv
  results/
    legacy/                 # reviewed historical baselines
    planner/                # generated planner benchmark reports
    capability/             # generated capability/RAG/tool reports
```

## Planner benchmark

`planner_intent_v1` contains 115 model-agnostic cases covering every current CityBuddy
leaf category, quantity preservation, multi-category prompts, multilingual input,
nearby/radius parsing, routing, ambiguity, unsupported constraints, and no-tool controls.

The current production planner contract cannot represent a small number of deliberately
forward-looking/no-tool cases. The evaluator therefore reports those as **unscorable**
instead of treating a schema mismatch as a model failure. `production` is the release-gate
suite; `all` records both scored and skipped cases.

```powershell
python -m scripts.evaluate_intent_models --model Qwen/Qwen3-1.7B --suite smoke
python -m scripts.evaluate_intent_models --model Qwen/Qwen3-1.7B --suite production
python -m scripts.evaluate_intent_models --model Qwen/Qwen3-4B --suite production
```

Use the same frozen fixture for every candidate model family. Do not create model-specific
gold answers.

## Capability benchmark

`capability_suite_v1` contains 46 cases spanning semantic retrieval, BGE embedding
retrieval, grounded RAG, weather, transport, prospective web search, multilingual tool use,
fail-closed behavior, tool-selection controls, and multi-tool chaining.

The first capability runner validates and summarizes the frozen fixture independently of a
live model. Live tool/RAG execution is layered onto this loader so benchmark-definition
errors are not confused with provider/model failures.

```powershell
python -m scripts.evaluate_capabilities
python -m scripts.evaluate_rag
```

## Fresh database bootstrap

For a brand-new local Docker volume, the PostgreSQL image initializes PostGIS and pgvector
automatically. Application schema remains migration-owned and is applied with Alembic via:

```powershell
python -m scripts.bootstrap_database
```

This separation mirrors production: infrastructure extensions belong to PostgreSQL setup;
application tables and schema evolution belong to committed migrations.

## Versioning

Released fixtures are immutable. Create `v2`, `v3`, and so on rather than silently changing
a benchmark after results have been recorded. Keep a manually reviewed regression subset
when the corpus grows to thousands of cases.

## AWS storage

Git remains the source of truth for compact gold fixtures. Mirror datasets and generated
result artifacts to S3 for durable retention, CI/evaluation runs, and future large corpora.
A suitable prefix is:

```text
s3://<bucket>/citybuddy/evaluation/v1/
```

Do not store API keys, database credentials, user conversations, or other secrets in these
fixtures or result directories.
