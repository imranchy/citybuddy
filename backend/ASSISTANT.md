# CityBuddy grounded assistant

The first conversational API uses a provider-neutral structured-model contract
with Ollama as the configured local provider. It does not give the model SQL,
database credentials, or unrestricted tool access.

## Request flow

```text
POST /api/assistant/chat
  -> structured intent extraction (small routed model)
  -> deterministic capability and location checks
  -> controlled SQLAlchemy/PostGIS retrieval
  -> grounded place selection (response model)
  -> exact place-ID and claim validation
  -> deterministic response rendering
```

The intent model interprets the request and the response model selects and
explains retrieved candidates. Application
code owns category validation, city support, geographic filters, limits,
database access, factual validation, transport URLs, and safety disclaimers.
The final answer and reasons are rendered from validated database facts rather
than returning unrestricted model prose.

Before retrieval, application code re-validates language selection, supported
city, explicit result counts, proximity/radius behavior, transport intent, and
unsupported/live-fact flags. Model-produced precautionary flags that the user
did not request are discarded, so they cannot create irrelevant warnings or
change retrieval scope.


## Grounded semantic evidence (Milestone A)

Approved production place rows can be converted into attributed evidence and
embedded locally with Ollama `bge-m3`. PostgreSQL stores the 1024-dimensional
vectors through pgvector. For qualitative, indirect, or contextual requests the assistant embeds the current
request and ranks evidence across reviewed places that pass deterministic city,
category, geographic and conversation-context filters. Simple explicit category
requests skip query embedding and use controlled database/PostGIS filtering directly,
which avoids an unnecessary embedding-model load while preserving semantic retrieval
for requests that benefit from it. It then materializes a small candidate shortlist
for the conversational model. This prevents an alphabetic
SQL limit from excluding the best semantic match. Every evidence ID selected by the response model is checked against its place.
Evidence remains internal to backend grounding, validation, and evaluation; the
public assistant response does not expose raw evidence excerpts or source metadata. Users receive the grounded explanation and one Google Maps action.
A separate transit action appears only when public transport was requested.

The indexer remains preview-first and never imports external documents:

```cmd
ollama pull bge-m3
python -m scripts.index_place_evidence --city Torino
python -m scripts.index_place_evidence --city Torino --apply
```

Re-running the command indexes only new or changed fingerprints. It is safe to
run after an approved staging promotion; it does not promote staged places and
does not bypass the ingestion review boundary.

## Example request

```json
{
  "message": "Recommend two museums in Turin",
  "language": "en",
  "history": [],
  "context_place_ids": [],
  "latitude": null,
  "longitude": null,
  "radius_km": null
}
```

`language` is an explicit user preference (`en` or `it`) and overrides model
language inference. For referential follow-ups such as "Which one is best for
cinema?", the client may send the previous recommendation IDs in
`context_place_ids`; controlled retrieval then limits the comparison to those
records. A new topic is not restricted by stale context IDs.

For a nearby request, provide both coordinates. The API accepts at most ten
recent user/assistant messages; the client owns conversation history in this
milestone, so no chat transcript is stored in the database.

## Grounding rules

- Only reviewed rows returned by the controlled retrieval service are eligible.
- Every model-selected place ID must be present in those retrieved rows.
- Every recommendation needs at least one exact, non-null database claim.
- When retrieved semantic evidence exists, every recommendation must cite valid
  evidence belonging to that same place.
- Unknown IDs, unsupported attributes, contradictions, duplicate IDs, and
  malformed abstentions cause deterministic fallback.
- When Ollama is unavailable or output validation fails, CityBuddy returns
  reviewed database results with an explicit warning.
- A nearby request without coordinates asks the client for location.
- Unsupported cities return no recommendations. Torino is the only supported
  city in this milestone.

## Public transport

The model never generates public-transport routes or live service facts.
Application code creates a key-free Google Maps transit URL for each recommended
place and returns `GOOGLE_MAPS_TRANSIT_DISCLAIMER`. Users must verify current
routes, departure times, disruptions, and availability in Google Maps.

## Local run

Start PostgreSQL/PostGIS and Ollama, then run the API from `backend`:

```cmd
uvicorn app.main:app --reload
```

The configured intent model defaults to `qwen3:8b`; the grounded response model
defaults to `gemma3:12b-it-qat`. Both are served by the same provider-neutral
interface and local Ollama API. Ollama hosts the models, while CityBuddy routes
each application task to the configured role. Interactive API docs are
available at `http://127.0.0.1:8000/docs`.

Before browser testing, run the intent-only benchmark and direct CLI assistant:

```cmd
python -m scripts.evaluate_intent_models --model qwen3:8b --suite smoke
python -m scripts.run_assistant_cli "Recommend two museums in Turin" --language en
python -m scripts.run_assistant_cli "Consigliami due musei a Torino" --language it
```

Model splitting can reduce generation cost, but two models may compete for GPU
memory. Compare warm latency and observe `ollama ps`; if model swapping erases
the speed benefit, CityBuddy can configure the response model for both roles
without changing the service flow.

Automated tests use fake providers and retrievers and do not require live model
calls:

```cmd
python -m unittest discover -s tests -v
```

## Observability and deployment

Synthetic evaluations may be traced to LangSmith explicitly. Production tracing
must remain opt-in until retention, redaction, and sampling are configured for
location-bearing user requests. Store production LangSmith service keys in the
deployment secret store, never in an image or repository.
