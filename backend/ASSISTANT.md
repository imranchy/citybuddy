# CityBuddy grounded assistant

The first conversational API uses a provider-neutral structured-model contract
with Ollama as the configured local provider. It does not give the model SQL,
database credentials, or unrestricted tool access.

## Request flow

```text
POST /api/assistant/chat
  -> structured intent extraction
  -> deterministic capability and location checks
  -> controlled SQLAlchemy/PostGIS retrieval
  -> grounded place selection
  -> exact place-ID and claim validation
  -> deterministic response rendering
```

The model interprets the request and selects retrieved candidates. Application
code owns category validation, city support, geographic filters, limits,
database access, factual validation, transport URLs, and safety disclaimers.
The final answer and reasons are rendered from validated database facts rather
than returning unrestricted model prose.

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

The configured model defaults to `gemma3:12b-it-qat`. Interactive API docs are
available at `http://127.0.0.1:8000/docs`.

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
