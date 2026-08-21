# CityBuddy vLLM model evaluation

CityBuddy evaluates open-weight models through the same OpenAI-compatible vLLM provider
used by the application. Evaluation does not expose an API route, change production data,
or require a database migration.

## Requirements

Start the target vLLM server and configure `VLLM_BASE_URL` and `VLLM_API_KEY` before
running evaluations. On the current laptop GPU, compare models sequentially rather than
assuming multiple models can remain resident together. The immediate planner/response
candidates are:

```text
Qwen/Qwen3-1.7B
Qwen/Qwen3-4B
```

A quantized approximately 8B model should be considered only if the smaller models do not
meet quality requirements.

## Full response evaluation

From `backend` with the project virtual environment active:

```cmd
python -m scripts.evaluate_llm_models
```

To run explicit models:

```cmd
python -m scripts.evaluate_llm_models --model Qwen/Qwen3-1.7B --model Qwen/Qwen3-4B
```

Reports are written to the ignored local `artifacts` directory as JSON and Markdown.

## Intent-model routing benchmark

Run the smaller intent-only suite before full grounded response evaluation:

```cmd
python -m scripts.evaluate_intent_models --model Qwen/Qwen3-1.7B --suite smoke
python -m scripts.evaluate_intent_models --model Qwen/Qwen3-1.7B --suite full
```

The suite contains the existing capability/safety cases and English/Italian taxonomy cases.
It measures strict case accuracy, field accuracy, schema validity, provider failures, and
cold/warm latency against the production structured intent contract. Safety-critical fields
such as unsupported city, live facts, nearby radius, transport intent, and explicit quantity
should be inspected separately from the aggregate score.

## Multilingual response check

```cmd
python -m scripts.evaluate_multilingual_responses --model Qwen/Qwen3-4B
```

The input remains fixed while the required response language changes. No separate translation
model is involved.

## RAG retrieval evaluation

Serve the configured embedding model through a vLLM OpenAI-compatible embedding endpoint.
The default model is `BAAI/bge-m3` and CityBuddy expects 1024-dimensional vectors. A dedicated
embedding server can be configured with `VLLM_EMBEDDING_BASE_URL` and
`VLLM_EMBEDDING_API_KEY`; otherwise the main vLLM endpoint/key are reused.

```cmd
python -m scripts.evaluate_rag
```

The report records Recall@3 and mean reciprocal rank (MRR). It evaluates retrieval rather
than answer quality.

## Optional LangSmith traces

LangSmith is optional and disabled by default. Only fixed synthetic evaluation prompts and
outputs are traced when `--langsmith` is explicitly supplied. `LANGSMITH_API_KEY` by itself
does not enable tracing. Do not enable production query tracing without a privacy, retention,
and sampling decision because user requests may contain location or other personal data.

```cmd
python -m scripts.evaluate_llm_models --langsmith
python -m scripts.evaluate_llm_models --langsmith --langsmith-project citybuddy-model-selection
```

## Evaluation gates

Use several metrics instead of one aggregate score: strict case accuracy, individual field
accuracy, JSON-schema validity, response success, grounding-check accuracy, supported-claim
rate, recommendation evidence coverage, entity/attribute hallucination rates, contradiction
rate, abstention accuracy, cold/warm latency, and provider errors. The production assistant
still enforces retrieved IDs, factual validation, and transport handling in application code.

## Automated tests

Automated tests use fake providers and HTTP mock transport and do not require a live model:

```cmd
python -m unittest discover -s tests -v
```

Versioned evaluation datasets live under `evaluation/datasets`. The frozen production v1 suites
are under `evaluation/datasets/v1`; historical fixtures remain under `evaluation/datasets/legacy`.
Generated planner and capability reports are written under `evaluation/results/planner` and
`evaluation/results/capability`; reviewed historical baselines remain under `evaluation/results/legacy`.
