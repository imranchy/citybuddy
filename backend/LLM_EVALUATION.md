# CityBuddy local-model evaluation

This milestone compares local text models before CityBuddy selects a default.
It does not expose an API route, query PostgreSQL, change production data, or
require a migration.

## Requirements

Run Ollama locally at `http://127.0.0.1:11434` and download the models being
tested. The default comparison set is:

```text
gemma3:4b
llama3.1:8b
qwen3:8b
gemma3:12b-it-qat
```

Verify GPU placement separately with `ollama ps`. A model that is partly
offloaded to CPU may have materially different latency.

## Run the evaluation

From `backend` with the Python environment active:

```cmd
python -m scripts.evaluate_llm_models
```

To run one or several explicit models:

```cmd
python -m scripts.evaluate_llm_models --model qwen3:8b --model gemma3:12b-it-qat
```

Reports are written to the ignored local `artifacts` directory as JSON and
Markdown. The JSON report contains each structured output, individual check,
machine-checkable claim result, and latency breakdown; the Markdown report is
a compact comparison.

## Optional LangSmith traces

LangSmith is optional and disabled by default. Create a LangSmith API key, copy
the variables from `.env.example` into your local `.env`, install the updated
requirements, and explicitly opt in:

```cmd
python -m scripts.evaluate_llm_models --langsmith
```

You can select a project without editing `.env`:

```cmd
python -m scripts.evaluate_llm_models --langsmith --langsmith-project citybuddy-model-selection
```

Only the fixed synthetic benchmark prompts and model outputs are traced by this
command. `LANGSMITH_API_KEY` alone does not enable tracing. Do not later enable
production query tracing without a privacy and retention decision because user
queries may contain location or other personal information.

## What is measured

The fixed cases cover English and Italian requests, direct and indirect
categories, multiple categories, nearby/radius intent, requested limits,
transport requests, live facts that CityBuddy cannot verify, and an unsupported
city. Grounding cases provide a closed set of retrieved place IDs and check
that the model uses only those IDs and avoids selected unsupported claims.

The report deliberately provides several metrics instead of treating one score
as a deployment gate:

- **Strict case accuracy**: every check in a case passed. Useful for regression,
  but harsh because one incorrect field fails the full case.
- **Field accuracy**: percentage of individual intent and grounding checks that
  passed.
- **Schema validity**: calls that returned the exact validated response shape.
  Timeouts and connection failures are excluded from this denominator and are
  reported separately; they are not incorrectly labelled schema failures.
- **Response success**: cases that completed without a provider, timeout, or
  schema/output error.
- **Grounding check accuracy**: retrieved IDs, uniqueness, evidence coverage,
  prohibited claims, and correct abstention.
- **Supported-claim rate**: structured claims whose entity, field, and value
  exactly match a supplied record. Reports include both the percentage and its
  numerator/denominator so a tiny sample cannot look deceptively conclusive.
- **Recommendation evidence coverage**: recommendations backed by at least one
  exact supported claim, also shown as a fraction.
- **Entity hallucination rate**: claims referencing a place not retrieved.
- **Attribute hallucination rate**: claims about a missing or null field.
- **Contradiction rate**: claims whose value conflicts with the retrieved value.
- **Abstention accuracy**: whether the model correctly declines when the supplied
  records cannot answer the request.
- **Cold and warm latency**: the first call/load is reported separately from the
  warm average, median, and p95.
- **Errors**: timeout, invalid schema/output, and other provider failures are
  counted independently from reasoning mistakes.

These are application-specific metrics, not a general model benchmark. The
structured claim ledger makes factual checks deterministic, while text scans
remain only a regression signal for specific invented assertions in prose.
Safe refusals such as saying departure information is unavailable are not
treated as hallucinations merely because they mention the word "departure".
The production assistant must still
enforce retrieved IDs, fact validation, and transport handling in application
code. A model reaching 80% on one aggregate metric is not by itself ready for
deployment; safety-critical checks should reach 100% on a larger held-out set.

The transport case evaluates only the model's grounded recommendation. Current
public-transport data is outside the model contract: deterministic application
code must add CityBuddy's Google Maps transit URL and safety disclaimer.

Ollama calls use JSON Schema structured output, deterministic sampling, a 4096
token context, and `think=false`. Models run sequentially and are unloaded
after their batch.

## Automated tests

Automated tests use a fake provider and HTTP mock transport. They never require
a running model:

```cmd
python -m unittest discover -s tests -v
```

## Versioned conversational and RAG datasets

`evaluation_datasets/conversations-v1.json` contains English and Italian
multi-turn, nearby, transport-safety, unsupported-city, and live-fact cases.
It is the repository source of truth. Synchronizing it to LangSmith is an
explicit operation—not something enabled by an API key alone:

```cmd
python -m scripts.sync_langsmith_dataset
```

`evaluation_datasets/rag-v2.json` is the default multilingual retrieval
benchmark. Its 68 cases cover every canonical leaf category in both English
and Italian, including deliberately adjacent categories such as bar/pub,
museum/gallery, park/garden, nightclub/music venue, hotel/hostel, and each
distinct place-of-worship category. `rag-v1.json` remains as the original smoke
test for comparison.
After installing `bge-m3`, run:

```cmd
python -m scripts.evaluate_rag
```

The report records Recall@3 and mean reciprocal rank (MRR). It tests retrieval,
not answer quality, and should be expanded with held-out production-like cases
before deployment. JSON artifacts are local and ignored unless a reviewed
baseline is deliberately copied into `evaluation_results`.
