# CityBuddy local-model evaluation

Generated: 2026-08-10T18:43:43.628029+00:00

| Model | Strict cases | Field accuracy | Grounding | Supported claims | Evidence coverage | Errors | Warm p95 |
|---|---:|---:|---:|---:|---:|---:|---:|
| `gemma3:4b` | 4/17 | 66.1% | 100.0% | 100.0% (3/3) | 100.0% (3/3) | 1 | 4.12 s |
| `llama3.1:8b` | 8/17 | 92.2% | 100.0% | 100.0% (4/4) | 100.0% (3/3) | 2 | 3.28 s |
| `qwen3:8b` | 10/17 | 90.2% | 100.0% | 100.0% (5/5) | 100.0% (3/3) | 0 | 4.52 s |
| `gemma3:12b-it-qat` | 12/17 | 95.5% | 100.0% | 100.0% (3/3) | 100.0% (3/3) | 0 | 7.91 s |

## gemma3:4b

- FAIL `museum_count` — categories, unsupported_constraints
- FAIL `italian_food` — categories, language, limit, nearby, unsupported_constraints
- FAIL `quiet_reading` — categories, limit, nearby, unsupported_constraints
- FAIL `outdoors` — categories, limit, unsupported_constraints
- FAIL `nightlife` — categories, language, limit, nearby, unsupported_constraints
- FAIL `market` — categories, limit, nearby, unsupported_constraints
- FAIL `worship` — Ollama model 'gemma3:4b' did not return valid structured output: 1 validation error for DiscoveryIntent
categories
  Value error, Unsupported CityBuddy category: places_of_worship [type=value_error, input_value=['places_of_worship', 'mosque'], input_type=list]
    For further information visit https://errors.pydantic.dev/2.13/v/value_error
- FAIL `accommodation` — categories, limit, nearby, unsupported_constraints
- FAIL `culture` — categories, limit, unsupported_constraints
- FAIL `transport` — categories, limit, nearby, unsupported_constraints
- FAIL `live_open` — categories, language, limit
- FAIL `unsupported_city` — categories, limit, nearby, unsupported_constraints
- FAIL `unverified_rating` — unsupported_constraints
- PASS `retrieved_only` — all checks
- PASS `transport_safety` — all checks
- PASS `missing_live_facts` — all checks
- PASS `no_retrieved_records` — all checks

## llama3.1:8b

- FAIL `museum_count` — limit
- FAIL `italian_food` — language
- PASS `quiet_reading` — all checks
- FAIL `outdoors` — Ollama model 'llama3.1:8b' did not return valid structured output: timed out
- FAIL `nightlife` — language
- PASS `market` — all checks
- FAIL `worship` — language, unsupported_constraints
- PASS `accommodation` — all checks
- PASS `culture` — all checks
- FAIL `transport` — wants_transport
- FAIL `live_open` — Ollama model 'llama3.1:8b' did not return valid structured output: timed out
- FAIL `unsupported_city` — categories, unsupported_constraints
- FAIL `unverified_rating` — unsupported_constraints
- PASS `retrieved_only` — all checks
- PASS `transport_safety` — all checks
- PASS `missing_live_facts` — all checks
- PASS `no_retrieved_records` — all checks

## qwen3:8b

- PASS `museum_count` — all checks
- FAIL `italian_food` — language, unsupported_constraints
- PASS `quiet_reading` — all checks
- PASS `outdoors` — all checks
- FAIL `nightlife` — language, unsupported_constraints
- PASS `market` — all checks
- FAIL `worship` — language, unsupported_constraints
- PASS `accommodation` — all checks
- PASS `culture` — all checks
- FAIL `transport` — categories, wants_transport
- FAIL `live_open` — categories, language
- FAIL `unsupported_city` — categories, city
- FAIL `unverified_rating` — unsupported_constraints
- PASS `retrieved_only` — all checks
- PASS `transport_safety` — all checks
- PASS `missing_live_facts` — all checks
- PASS `no_retrieved_records` — all checks

## gemma3:12b-it-qat

- FAIL `museum_count` — limit
- PASS `italian_food` — all checks
- PASS `quiet_reading` — all checks
- PASS `outdoors` — all checks
- PASS `nightlife` — all checks
- PASS `market` — all checks
- FAIL `worship` — categories
- PASS `accommodation` — all checks
- PASS `culture` — all checks
- FAIL `transport` — wants_transport, unsupported_constraints
- FAIL `live_open` — language
- PASS `unsupported_city` — all checks
- FAIL `unverified_rating` — unsupported_constraints
- PASS `retrieved_only` — all checks
- PASS `transport_safety` — all checks
- PASS `missing_live_facts` — all checks
- PASS `no_retrieved_records` — all checks
