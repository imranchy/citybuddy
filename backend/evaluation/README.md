# CityBuddy Production Evaluation Pack v1

Two model-agnostic benchmark suites for repeatable pre-deployment evaluation.

## planner_intent_v1
Cases: 115
Purpose: small planner/intent model. Covers every current CityBuddy leaf category, quantity preservation, multi-category prompts, multilingual input, nearby/radius parsing, routing, ambiguity, unsupported constraints, and no-tool controls.

## capability_suite_v1
Cases: 46
Purpose: larger reasoning/response/tool model. Covers semantic retrieval, BGE embedding retrieval, grounded RAG, weather and transport tools, prospective web search, multilingual tool use, fail-closed behavior, and multi-tool chaining.

## Versioning
Freeze released datasets. Create v2 instead of silently changing v1 after results exist.

## Recommended Git layout
``
evaluation/
  datasets/
    planner_intent_v1.csv
    planner_intent_v1.jsonl
    capability_suite_v1.csv
    capability_suite_v1.jsonl
  results/
    <model>/<timestamp>.jsonl
  README.md
```

## AWS storage
Keep small gold fixtures in Git. Mirror datasets and result artifacts to S3 for durable retention, CI runs, and future 1,000+ case corpora. Suggested prefix: `s3://<bucket>/citybuddy/evaluation/v1/`.

## Model-family policy
Use these same frozen datasets across model families. Do not create family-specific gold answers. This preserves comparability between Qwen and alternative candidates.

## Future scale
For 1,000+ cases, keep a manually curated locked gold subset, stratify by category/language/difficulty/tool, add adversarial cases, and continuously add anonymized production failure patterns.
