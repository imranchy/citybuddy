import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import urlparse

from app.core.place_catalog import DESTINATION_CATEGORIES


ALLOWED_INGESTION_SOURCES = frozenset({"osm", "wikimedia_commons"})
ALLOWED_TRIGGERS = frozenset({"manual", "scheduled"})


SAFE_ENRICHMENT_FIELDS = ("description", "opening_hours", "website", "operator")


def missing_enrichment_updates(
    current: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> dict[str, Any]:
    """Return source values that may safely fill currently missing production fields.

    This never proposes overwriting a populated production value. Conflict
    reconciliation remains a separate reviewed future capability.
    """

    updates: dict[str, Any] = {}
    for field in SAFE_ENRICHMENT_FIELDS:
        existing_value = current.get(field)
        candidate_value = candidate.get(field)
        existing_missing = existing_value is None or (
            isinstance(existing_value, str) and not existing_value.strip()
        )
        candidate_present = candidate_value is not None and not (
            isinstance(candidate_value, str) and not candidate_value.strip()
        )
        if existing_missing and candidate_present:
            updates[field] = candidate_value
    return updates


@dataclass(frozen=True, slots=True)
class ValidationFinding:
    code: str
    severity: str
    message: str
    field: str | None = None


def build_candidate_fingerprint(candidate: Mapping[str, Any]) -> str:
    """Return a stable digest for source data used in change detection."""

    serialized = json.dumps(
        candidate,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def validate_place_candidate(
    candidate: Mapping[str, Any],
) -> list[ValidationFinding]:
    """Apply deterministic checks before a place can be promoted."""

    findings: list[ValidationFinding] = []

    def error(
        code: str,
        message: str,
        field: str | None = None,
    ) -> None:
        findings.append(ValidationFinding(code, "error", message, field))

    source = candidate.get("source")
    if source != "osm":
        error("unsupported_source", "Place candidates must come from OSM.", "source")

    source_id = candidate.get("source_id")
    if not isinstance(source_id, str) or not source_id.strip():
        error("missing_source_id", "A source identifier is required.", "source_id")

    name = candidate.get("name")
    if not isinstance(name, str) or not name.strip():
        error("missing_name", "A place name is required.", "name")
    elif "temporary" in name.casefold():
        findings.append(
            ValidationFinding(
                "temporary_name_review_required",
                "warning",
                "The place name suggests temporary status and requires review.",
                "name",
            )
        )

    category = candidate.get("category")
    if category not in DESTINATION_CATEGORIES:
        error(
            "unsupported_category",
            "The category is not in the CityBuddy discovery catalog.",
            "category",
        )

    city = candidate.get("city")
    if not isinstance(city, str) or not city.strip():
        error("missing_city", "A configured city is required.", "city")

    address = candidate.get("address")
    if not isinstance(address, str) or address.strip() == "Address unavailable":
        findings.append(
            ValidationFinding(
                "missing_address_review_required",
                "warning",
                "The place has no usable street address.",
                "address",
            )
        )

    country_code = candidate.get("country_code")
    if (
        not isinstance(country_code, str)
        or len(country_code.strip()) != 2
    ):
        error(
            "invalid_country_code",
            "The country code must contain two letters.",
            "country_code",
        )

    latitude = candidate.get("latitude")
    if not isinstance(latitude, (int, float)) or not -90 <= latitude <= 90:
        error("invalid_latitude", "Latitude must be between -90 and 90.", "latitude")

    longitude = candidate.get("longitude")
    if not isinstance(longitude, (int, float)) or not -180 <= longitude <= 180:
        error(
            "invalid_longitude",
            "Longitude must be between -180 and 180.",
            "longitude",
        )

    website = candidate.get("website")
    if website:
        parsed = urlparse(str(website))
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            error(
                "invalid_website",
                "Website URLs must use HTTP or HTTPS and include a host.",
                "website",
            )

    lifecycle_tags = candidate.get("lifecycle_tags") or []
    if lifecycle_tags:
        findings.append(
            ValidationFinding(
                "lifecycle_review_required",
                "warning",
                "Lifecycle metadata requires review: "
                + ", ".join(str(tag) for tag in lifecycle_tags),
                "lifecycle_tags",
            )
        )

    return findings


def validate_image_candidate(
    candidate: Mapping[str, Any],
) -> list[ValidationFinding]:
    """Apply deterministic attribution and URL checks to an image candidate."""

    findings: list[ValidationFinding] = []

    def error(
        code: str,
        message: str,
        field: str | None = None,
    ) -> None:
        findings.append(ValidationFinding(code, "error", message, field))

    if candidate.get("source") != "wikimedia_commons":
        error(
            "unsupported_image_source",
            "Image candidates must come from Wikimedia Commons.",
            "source",
        )

    place_id = candidate.get("place_id")
    if not isinstance(place_id, int) or place_id < 1:
        error("invalid_place_id", "A production place ID is required.", "place_id")

    wikidata_id = candidate.get("wikidata_id")
    if not isinstance(wikidata_id, str) or not re.fullmatch(
        r"Q[1-9]\d*", wikidata_id
    ):
        error("invalid_wikidata_id", "A valid Wikidata ID is required.", "wikidata_id")

    source_image_id = candidate.get("source_image_id")
    if not isinstance(source_image_id, str) or not source_image_id.startswith("File:"):
        error(
            "invalid_source_image_id",
            "A Wikimedia Commons File: identifier is required.",
            "source_image_id",
        )

    required_urls = {
        "image_url": "upload.wikimedia.org",
        "source_page_url": "commons.wikimedia.org",
    }
    for field, expected_host in required_urls.items():
        value = candidate.get(field)
        parsed = urlparse(str(value or ""))
        if parsed.scheme != "https" or parsed.hostname != expected_host:
            error(
                f"invalid_{field}",
                f"{field} must use HTTPS on {expected_host}.",
                field,
            )

    thumbnail_url = candidate.get("thumbnail_url")
    if thumbnail_url:
        parsed = urlparse(str(thumbnail_url))
        if parsed.scheme != "https" or parsed.hostname != "upload.wikimedia.org":
            error(
                "invalid_thumbnail_url",
                "thumbnail_url must use HTTPS on upload.wikimedia.org.",
                "thumbnail_url",
            )

    if not str(candidate.get("attribution") or "").strip():
        error("missing_attribution", "Image attribution is required.", "attribution")
    if not str(candidate.get("license") or "").strip():
        error("missing_license", "Image license metadata is required.", "license")

    license_url = candidate.get("license_url")
    if license_url:
        parsed = urlparse(str(license_url))
        if parsed.scheme != "https" or not parsed.netloc:
            error(
                "invalid_license_url",
                "License URLs must use HTTPS and include a host.",
                "license_url",
            )

    return findings


def validation_status(findings: list[ValidationFinding]) -> str:
    if any(finding.severity == "error" for finding in findings):
        return "invalid"
    if any(finding.severity == "warning" for finding in findings):
        return "review_required"
    return "valid"


def limit_candidates_per_category(
    candidates: list[dict[str, Any]],
    limit: int,
) -> list[dict[str, Any]]:
    """Apply a stable per-category cap to pre-sorted candidates."""

    counts: Counter[str] = Counter()
    limited: list[dict[str, Any]] = []
    for candidate in candidates:
        category = str(candidate["category"])
        if counts[category] >= limit:
            continue
        limited.append(candidate)
        counts[category] += 1
    return limited
