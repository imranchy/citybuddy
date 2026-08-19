# CityBuddy grounded assistant

The first conversational API uses a provider-neutral structured-model contract
with Ollama as the configured local provider. It does not give the model SQL,
database credentials, or unrestricted tool access.

## Request flow

```text
POST /api/assistant/chat
  -> structured intent + bounded tool-intent extraction (small routed model)
  -> deterministic city/category/location validation
  -> one bounded branch:
       discovery -> controlled SQLAlchemy/PostGIS + RAG retrieval
       weather -> typed CityBuddy weather tool
       official live info -> reviewed place resolution -> typed official-site tool
  -> grounded response generation (response model)
  -> exact place/tool-claim validation
  -> deterministic response rendering/fallback
```

The intent model interprets the request and the response model selects and
explains retrieved candidates. Application
code owns category validation, city support, geographic filters, limits,
database access, factual validation, transport URLs, and safety disclaimers.
The final answer and reasons are rendered from validated database or bounded live-tool facts rather
than returning unrestricted model prose.

Before retrieval, application code re-validates language selection, supported
city, explicit result counts, proximity/radius behavior, transport intent, and
unsupported/live-fact flags. Model-produced precautionary flags that the user
did not request are discarded, so they cannot create irrelevant warnings or
change retrieval scope.

## Bounded live-tool routing

The intent schema exposes only these assistant-owned tool choices:

- `discovery`
- `weather`
- `official_opening`
- `official_menu`
- `official_exhibitions`
- `official_prices`

Qwen may choose one of those semantic intents, but it never receives SQL, a URL,
a database write, a shell, or an open-ended tool loop. CityBuddy application code
constructs the validated tool arguments. Weather uses the supported city and optional
validated coordinates. Official-site requests must first resolve to a reviewed
CityBuddy place; the model cannot supply the place ID or website URL. A single
conversation context place can be reused, otherwise the existing reviewed retrieval/RAG
path supplies a bounded candidate set and CityBuddy resolves the named place from it.

Live results are sent to the response model as bounded evidence. Non-abstaining
weather answers must include exact claims copied from the serialized weather result.
Official-site answers must include an exact supported field or a short exact excerpt
from the retrieved official text. If the official-site retrieval is unverified or
contains no readable static content, the response must abstain; validation rejects a
confident current-fact answer. The selected UI language remains authoritative after
tool execution.


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

`language` is an explicit user preference (`en`, `it`, `pt`, `de`, or `bn`) and overrides model
language inference. The selected language is authoritative for user-visible assistant output. For referential follow-ups such as "Which one is best for
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

## Bounded official-site question answering

Place-specific live questions may use the reviewed place's stored official website. The
assistant never receives arbitrary web access and neither the model nor caller can supply
a URL. Application code resolves a reviewed place first, reads only its stored website,
validates the official domain and public DNS target, follows only bounded same-domain
links discovered from that page, strips executable/style content, and caps response size.

Supported bounded routes include opening information, menus/dietary information,
exhibitions, prices, and general official-place information such as shops/brands,
collections, facilities, accessibility, services, parking and amenities. The user's
question may rank already-extracted same-domain links but cannot authorize a URL.

Before Gemma answers, CityBuddy selects a compact verbatim evidence window from the
verified official page. Claims must match that evidence (allowing whitespace-only HTML
layout differences). Today/now answers also receive the supported city's application-
owned local date and weekday. If a page is unverified, dynamically rendered with no
readable static content, or does not state the requested fact (for example halal status),
the assistant must abstain rather than infer it.

## Semantic planner and response-language policy

Interactive requests now use Qwen as a bounded semantic planner rather than treating the
model as a single-intent keyword classifier. The planner emits a validated `SemanticPlan`
containing request/response language, ordered tasks, canonical category requests with
per-category quantities, semantic preferences, conversational references, live-tool intent,
and a high-level goal (`recommend`, `describe`, `compare`, `itinerary`, or `answer`).
Application code validates catalog keys, limits, supported cities, reviewed-place identity,
and tool boundaries before any retrieval executes.

Language interpretation is model-owned in the planner path. The page language is the UI
fallback, while the current message language or an explicit response-language instruction
may select the response language. Application code validates the resulting language code but
does not need per-language number-word dictionaries for production planner requests. This
keeps future language additions primarily in UI copy, planner evaluation, and language
configuration rather than duplicating NLP rules throughout the backend.

Compound plans execute as a bounded sequence of ordinary CityBuddy retrieval/tool tasks.
Gemma receives the validated task results, reviewed place records, RAG evidence, structured
place facts, conversation context, distance/transit information, and application-owned time
context, then performs comparison, trade-off reasoning, itinerary synthesis, and natural
response composition. Models still have no arbitrary SQL, filesystem, shell, or unrestricted
network access.

Planner and response inference can be isolated operationally with
`OLLAMA_PLANNER_BASE_URL` and `OLLAMA_RESPONSE_BASE_URL`. If those variables are empty,
CityBuddy keeps the existing single-Ollama local behavior.
