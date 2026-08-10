import time
from typing import Any

import httpx


OVERPASS_URLS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
)

USER_AGENT = "CityBuddy/0.1 (https://github.com/imranchy/citybuddy)"
_preferred_endpoint: str | None = None
_endpoint_cooldowns: dict[str, float] = {}


def fetch_overpass_json(
    query: str,
    *,
    timeout_seconds: float,
    attempts_per_endpoint: int = 2,
) -> tuple[dict[str, Any], str]:
    """Fetch one query with bounded retries across current public instances."""

    global _preferred_endpoint

    errors: list[str] = []
    endpoints = list(OVERPASS_URLS)
    if _preferred_endpoint in endpoints:
        endpoints.remove(_preferred_endpoint)
        endpoints.insert(0, _preferred_endpoint)

    now = time.monotonic()
    available_endpoints = [
        endpoint
        for endpoint in endpoints
        if _endpoint_cooldowns.get(endpoint, 0) <= now
    ]
    if not available_endpoints:
        available_endpoints = endpoints

    for endpoint in available_endpoints:
        for attempt in range(1, attempts_per_endpoint + 1):
            try:
                print(
                    f"Requesting Overpass data from {endpoint} "
                    f"(attempt {attempt}/{attempts_per_endpoint})..."
                )
                response = httpx.post(
                    endpoint,
                    data={"data": query},
                    headers={"User-Agent": USER_AGENT},
                    timeout=timeout_seconds,
                )
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise ValueError("Overpass returned a non-object JSON response.")
                _preferred_endpoint = endpoint
                return payload, endpoint
            except (httpx.HTTPError, ValueError) as error:
                errors.append(f"{endpoint} attempt {attempt}: {error}")
                print(f"Request failed: {error}")
                if (
                    isinstance(error, httpx.HTTPStatusError)
                    and error.response.status_code == 429
                ):
                    retry_after = error.response.headers.get("Retry-After")
                    try:
                        cooldown_seconds = max(30, int(retry_after or "0"))
                    except ValueError:
                        cooldown_seconds = 30
                    _endpoint_cooldowns[endpoint] = (
                        time.monotonic() + min(cooldown_seconds, 300)
                    )
                    print(
                        f"Cooling down {endpoint} after rate limiting; "
                        "trying another endpoint."
                    )
                    break
                if attempt < attempts_per_endpoint:
                    time.sleep(2 ** (attempt - 1))

    detail = " | ".join(errors[-3:])
    raise RuntimeError(f"All Overpass requests failed. Last failures: {detail}")
