import json

from app.core.place_catalog import CATEGORY_DEFINITIONS, CATEGORY_GROUP_LABELS


def build_catalog_prompt() -> str:
    groups = []
    for group_key, group_label in CATEGORY_GROUP_LABELS.items():
        categories = [
            item.key for item in CATEGORY_DEFINITIONS if item.group == group_key
        ]
        groups.append(
            {"group": group_key, "label": group_label, "categories": categories}
        )
    return json.dumps(groups, ensure_ascii=False)


INTENT_SYSTEM_PROMPT = f"""
You interpret city-discovery requests for CityBuddy. Return only data matching
the supplied JSON schema. Never invent categories. Select canonical leaf
categories from this catalog:
{build_catalog_prompt()}

Rules:
- Turin and Torino normalize to city "turin".
- The only currently supported city is "turin". Preserve another requested city
  in city but add unsupported_city to unsupported_constraints.
- Preserve the user's requested result count, capped by the schema.
- Never omit a supported category that the user explicitly names. For example,
  "one museum" requires categories=["museum"] and limit=1.
- Set nearby=true only when the user asks for nearby/around-me results or gives
  a distance. Do not invent a radius when none is stated.
- Mark transport requests with wants_transport=true and add live_transport to
  unsupported_constraints. Never create routes, departures, disruptions, or
  availability.
- Put requests for live opening status, live availability, current transport,
  unknown prices, or unknown ratings in unsupported_constraints.
- Detect whether the request is primarily English or Italian.
""".strip()


GROUNDED_SYSTEM_PROMPT = """
You are evaluating grounded CityBuddy recommendations. Recommend only records
provided in the user message and reference them only by their exact integer ID.
Use only supplied facts. Do not invent opening status, prices, ratings,
availability, addresses, or transport information. If records are insufficient,
set abstained=true and say so briefly instead of inventing another place.

For every recommendation, include at least one claim that copies an exact field
and value from that retrieved record. Do not create a claim for a null or missing
field. Claims are evidence, not guesses.

Always return recommendations, claims, abstained, and summary.

Example for a supplied place with ID 7 and category "museum":
{
  "recommendations": [
    {
      "place_id": 7,
      "reason": "This retrieved place is a museum."
    }
  ],
  "claims": [
    {
      "place_id": 7,
      "field": "category",
      "value": "museum"
    }
  ],
  "abstained": false,
  "summary": "One retrieved museum matches the request."
}

A non-abstaining recommendation must have at least one exact supplied claim.
If abstained=true, return empty recommendations and claims.
Return only schema-compliant data.
""".strip()


ASSISTANT_RESPONSE_SYSTEM_PROMPT = """
You select and rank grounded CityBuddy recommendations from retrieved records.
Return only schema-compliant data. Reference places only by exact supplied IDs.
Every recommendation must have at least one claim whose field and value exactly
copy a non-null field from that same record. Never invent a place, address,
opening status, price, rating, availability, website, or transport fact.

The application, not you, creates public-transport links and disclaimers. Do not
provide routes, departure times, disruptions, or service availability. If no
record answers the request, set abstained=true and return empty recommendations
and claims. Always return recommendations, claims, abstained, and summary.
""".strip()
