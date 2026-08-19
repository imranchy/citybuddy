from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
import ipaddress
import re
import socket
from typing import Literal
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx
from pydantic import BaseModel, ConfigDict


OfficialPageType = Literal[
    "general",
    "menu",
    "exhibitions",
    "prices",
    "opening_info",
]

OfficialRetrievalReason = Literal[
    "no_readable_static_content",
    "static_retrieval_blocked",
]

ALLOWED_CONTENT_TYPES = {
    "text/html",
    "text/plain",
    "application/xhtml+xml",
}
MAX_RESPONSE_BYTES = 512_000
MAX_TEXT_CHARS = 12_000
MAX_REDIRECTS = 3
MAX_QUERY_CANDIDATE_PAGES = 3
BLOCKED_STATIC_STATUS_CODES = {401, 403, 406, 429}
REQUEST_TIMEOUT = httpx.Timeout(8.0, connect=5.0)
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/136.0.0.0 Safari/537.36 CityBuddy/0.1"
)
REQUEST_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "text/plain;q=0.8,*/*;q=0.5"
    ),
    "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
}

# Temporary deterministic routing hints for the MVP.
# These do not authorize URLs: candidate links must still come from the reviewed
# official domain. A later bounded semantic ranker can replace these hints without
# changing the network-security boundary.
PAGE_HINTS: dict[OfficialPageType, tuple[str, ...]] = {
    "general": (
        "brand", "brands", "shop", "shops", "store", "stores", "collection",
        "collections", "directory", "facility", "facilities", "service", "services",
        "amenities", "accessibility", "parking", "negozi", "servizi", "parcheggio",
    ),
    "menu": (
        "menu",
        "menus",
        "carta",
        "food",
        "drink",
        "drinks",
        "cucina",
        "ristorante",
    ),
    "exhibitions": (
        "exhibition",
        "exhibitions",
        "exhibit",
        "mostra",
        "mostre",
        "events",
        "eventi",
    ),
    "prices": (
        "price",
        "prices",
        "pricing",
        "prezzi",
        "tariffe",
        "tickets",
        "biglietti",
        "rates",
    ),
    "opening_info": (
        "opening",
        "hours",
        "orari",
        "visit",
        "visita",
        "access",
        "apertura",
        "aperto",
        "chiuso",
    ),
}


class OfficialSiteEvidence(BaseModel):
    """Bounded evidence retrieved only from a reviewed place's official site."""

    model_config = ConfigDict(extra="forbid")

    place_id: int
    place_name: str
    page_type: OfficialPageType
    official_host: str
    source_url: str
    fetched_at: datetime
    verified: bool
    reason: OfficialRetrievalReason | None
    title: str | None
    text: str | None
    truncated: bool


class _PageExtractor(HTMLParser):
    """Extract visible text and same-page links without executing HTML content."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._ignored_depth = 0
        self._in_title = False
        self._current_href: str | None = None
        self._current_link_text: list[str] = []
        self._text_parts: list[str] = []
        self._title_parts: list[str] = []
        self.links: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.casefold()
        if lowered in {"script", "style", "noscript", "svg", "template"}:
            self._ignored_depth += 1
            return
        if self._ignored_depth:
            return
        if lowered == "title":
            self._in_title = True
        if lowered == "a":
            href = next((value for key, value in attrs if key.casefold() == "href"), None)
            self._current_href = href
            self._current_link_text = []

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.casefold()
        if lowered in {"script", "style", "noscript", "svg", "template"}:
            if self._ignored_depth:
                self._ignored_depth -= 1
            return
        if self._ignored_depth:
            return
        if lowered == "title":
            self._in_title = False
        if lowered == "a" and self._current_href:
            text = " ".join(self._current_link_text).strip()
            self.links.append((self._current_href, text))
            self._current_href = None
            self._current_link_text = []

    def handle_data(self, data: str) -> None:
        if self._ignored_depth:
            return
        cleaned = " ".join(unescape(data).split())
        if not cleaned:
            return
        if self._in_title:
            self._title_parts.append(cleaned)
        if self._current_href is not None:
            self._current_link_text.append(cleaned)
        self._text_parts.append(cleaned)

    @property
    def title(self) -> str | None:
        title = " ".join(self._title_parts).strip()
        return title or None

    @property
    def text(self) -> str:
        return "\n".join(self._text_parts)


class StaticRetrievalBlockedError(ValueError):
    """The reviewed official site declined bounded static retrieval."""

    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        super().__init__(
            f"Official website blocks static retrieval (HTTP {status_code})."
        )


def _canonical_host(host: str) -> str:
    normalized = host.rstrip(".").casefold()
    if normalized.startswith("www."):
        normalized = normalized[4:]
    return normalized


def _normalize_official_url(value: str) -> str:
    candidate = value.strip()
    if not candidate:
        raise ValueError("The reviewed place does not have an official website URL.")
    if "://" not in candidate:
        candidate = f"https://{candidate}"

    parsed = urlsplit(candidate)
    if parsed.scheme.casefold() not in {"http", "https"}:
        raise ValueError("Official website URLs must use HTTP or HTTPS.")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Official website URLs may not contain embedded credentials.")
    if not parsed.hostname:
        raise ValueError("Official website URL has no valid hostname.")

    try:
        hostname = parsed.hostname.encode("idna").decode("ascii").casefold()
    except UnicodeError as exc:
        raise ValueError("Official website hostname is invalid.") from exc

    port = parsed.port
    if port is not None and port not in {80, 443}:
        raise ValueError("Official website URL uses a non-standard network port.")

    netloc = hostname
    if port is not None:
        netloc = f"{hostname}:{port}"
    path = parsed.path or "/"
    return urlunsplit((parsed.scheme.casefold(), netloc, path, parsed.query, ""))


def _default_resolver(host: str, port: int) -> set[str]:
    try:
        results = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError("Official website hostname could not be resolved.") from exc
    return {item[4][0] for item in results}


def validate_public_http_url(
    url: str,
    *,
    expected_official_host: str,
    resolver: Callable[[str, int], set[str]] = _default_resolver,
) -> str:
    """Validate scheme/domain/DNS before any official-site network request."""

    normalized = _normalize_official_url(url)
    parsed = urlsplit(normalized)
    assert parsed.hostname is not None

    if _canonical_host(parsed.hostname) != _canonical_host(expected_official_host):
        raise ValueError("Official-site redirects must stay on the reviewed official domain.")

    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    addresses = resolver(parsed.hostname, port)
    if not addresses:
        raise ValueError("Official website hostname did not resolve to an address.")

    for value in addresses:
        try:
            address = ipaddress.ip_address(value)
        except ValueError as exc:
            raise ValueError("Official website resolved to an invalid IP address.") from exc
        if not address.is_global:
            raise ValueError("Official website resolved to a non-public network address.")

    return normalized


def _extract_page(content: str) -> _PageExtractor:
    parser = _PageExtractor()
    parser.feed(content)
    parser.close()
    return parser


# Small deterministic aliases improve navigation on Italian official sites without
# allowing the model to invent URLs. Candidate links still have to be extracted from
# the reviewed official page and remain on the reviewed domain.
QUERY_TERM_ALIASES: dict[str, tuple[str, ...]] = {
    "shop": ("negozio", "negozi", "bottega", "botteghe", "artigiano", "artigiani"),
    "shops": ("negozio", "negozi", "bottega", "botteghe", "artigiano", "artigiani"),
    "store": ("negozio", "negozi", "bottega", "botteghe"),
    "stores": ("negozio", "negozi", "bottega", "botteghe"),
    "brand": ("marchio", "marchi"),
    "brands": ("marchio", "marchi"),
    "directory": ("elenco", "mappa", "botteghe", "artigiani"),
    "facilities": ("strutture", "servizi", "come-funziona", "informazioni"),
    "amenities": ("servizi", "strutture", "comfort"),
    "visitor": ("visita", "visitatori", "informazioni", "info"),
    "highlights": ("opere", "capolavori", "percorsi", "collezioni"),
    "policy": ("informazioni", "allergeni", "intolleranze"),
    "men": ("uomo",),
    "women": ("donna",),
    "kids": ("bambini", "bambino"),
    "menu": ("carta", "menu", "menù", "piatti", "cucina"),
    "vegetarian": ("vegetariano", "vegetariana", "vegetariani", "vegetariane"),
    "vegan": ("vegano", "vegana", "vegani", "vegane"),
    "dietary": ("alimentare", "alimentari", "dietetiche", "dietetici"),
    "gluten": ("glutine", "celiachia", "celiaco", "celiaca"),
    "allergens": ("allergeni", "allergie"),
    "allergen": ("allergeni", "allergie"),
    "food": ("cibo", "cucina", "mangiare", "ristorazione"),
    "parking": ("parcheggio", "parcheggi"),
    "services": ("servizi",),
    "service": ("servizio", "servizi"),
    "facilities": ("strutture", "servizi"),
    "family": ("famiglia", "famiglie"),
    "children": ("bambini", "bambino", "famiglie"),
    "barrier": ("barriere", "senza-barriere"),
    "accessibility": ("accessibilita", "accessibilità"),
    "accessible": ("accessibile", "accessibili"),
    "disabled": ("disabili", "disabilita", "disabilità"),
    "wheelchair": ("sedia", "rotelle"),
    "collections": ("collezione", "collezioni"),
    "collection": ("collezione", "collezioni"),
    "permanent": ("permanente", "permanenti"),
    "halal": ("halal",),
}


def _query_terms(query: str | None) -> tuple[str, ...]:
    if not query:
        return ()
    words = re.findall(r"[\wÀ-ÿ]+", query.casefold(), flags=re.UNICODE)
    expanded: list[str] = []
    for word in words:
        if len(word) < 3:
            continue
        expanded.append(word)
        expanded.extend(QUERY_TERM_ALIASES.get(word, ()))
    return tuple(dict.fromkeys(expanded))[:64]


def _link_term_matches(haystack: str, term: str) -> bool:
    """Match whole words/phrases so short terms never match inside other words."""

    escaped = re.escape(term.casefold()).replace(r"\ ", r"[\s/_-]+")
    return re.search(rf"(?<!\w){escaped}(?!\w)", haystack.casefold(), re.UNICODE) is not None


def _rank_same_domain_links(
    parser: _PageExtractor,
    *,
    base_url: str,
    page_type: OfficialPageType,
    official_host: str,
    query: str | None = None,
) -> list[str]:
    """Rank bounded same-domain candidates extracted from one verified page."""

    hints = PAGE_HINTS[page_type]
    query_terms = _query_terms(query)
    if not hints and not query_terms:
        return []

    candidates: list[tuple[int, int, str]] = []
    seen: set[str] = set()
    for index, (href, anchor_text) in enumerate(parser.links):
        absolute = urljoin(base_url, href)
        parsed = urlsplit(absolute)
        if parsed.scheme.casefold() not in {"http", "https"} or not parsed.hostname:
            continue
        if _canonical_host(parsed.hostname) != _canonical_host(official_host):
            continue
        absolute = urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", parsed.query, ""))
        if absolute in seen or absolute == base_url:
            continue
        seen.add(absolute)
        haystack = f"{parsed.path} {parsed.query} {anchor_text}".casefold()
        hint_score = sum(3 for hint in hints if _link_term_matches(haystack, hint))
        query_score = sum(5 for term in query_terms if _link_term_matches(haystack, term))
        if query_terms and query_score == 0:
            continue
        score = hint_score + query_score
        if score:
            candidates.append((-score, index, absolute))

    candidates.sort()
    return [url for _, _, url in candidates]


def _choose_same_domain_link(
    parser: _PageExtractor,
    *,
    base_url: str,
    page_type: OfficialPageType,
    official_host: str,
    query: str | None = None,
) -> str | None:
    ranked = _rank_same_domain_links(
        parser,
        base_url=base_url,
        page_type=page_type,
        official_host=official_host,
        query=query,
    )
    return ranked[0] if ranked else None


def _page_query_score(
    parser: _PageExtractor,
    *,
    source_url: str,
    query: str | None,
) -> int:
    """Score fetched page content against the bounded caller query."""

    terms = _query_terms(query)
    if not terms:
        return 0
    metadata = f"{source_url} {parser.title or ''}"
    body = parser.text[:MAX_TEXT_CHARS]
    metadata_score = sum(4 for term in terms if _link_term_matches(metadata, term))
    body_score = sum(1 for term in terms if _link_term_matches(body, term))
    return metadata_score + body_score


def _read_bounded_stream(response: httpx.Response) -> tuple[str, bool]:
    content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().casefold()
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise ValueError(
            f"Official website returned unsupported content type: {content_type or 'unknown'}."
        )

    declared = response.headers.get("content-length")
    if declared is not None:
        try:
            declared_bytes = int(declared)
        except ValueError:
            declared_bytes = None
        if declared_bytes is not None and declared_bytes > MAX_RESPONSE_BYTES:
            raise ValueError("Official website response is larger than CityBuddy's safety limit.")

    body = bytearray()
    truncated = False
    for chunk in response.iter_bytes():
        remaining = MAX_RESPONSE_BYTES - len(body)
        if remaining <= 0:
            truncated = True
            break
        if len(chunk) > remaining:
            body.extend(chunk[:remaining])
            truncated = True
            break
        body.extend(chunk)

    encoding = response.encoding or "utf-8"
    return bytes(body).decode(encoding, errors="replace"), truncated


def _request_page(
    client: httpx.Client,
    url: str,
    *,
    official_host: str,
    resolver: Callable[[str, int], set[str]],
) -> tuple[str, str, bool]:
    current = url
    for redirect_count in range(MAX_REDIRECTS + 1):
        current = validate_public_http_url(
            current,
            expected_official_host=official_host,
            resolver=resolver,
        )
        try:
            with client.stream(
                "GET",
                current,
                headers=REQUEST_HEADERS,
                follow_redirects=False,
            ) as response:
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        raise ValueError(
                            "Official website returned a redirect without a destination."
                        )
                    if redirect_count >= MAX_REDIRECTS:
                        raise ValueError("Official website exceeded CityBuddy's redirect limit.")
                    current = urljoin(current, location)
                    continue

                if response.status_code in BLOCKED_STATIC_STATUS_CODES:
                    raise StaticRetrievalBlockedError(response.status_code)
                response.raise_for_status()
                text, truncated = _read_bounded_stream(response)
                return current, text, truncated
        except httpx.TimeoutException as exc:
            raise ValueError("Official website request timed out.") from exc
        except httpx.HTTPStatusError as exc:
            raise ValueError(
                f"Official website returned HTTP {exc.response.status_code}."
            ) from exc
        except httpx.RequestError as exc:
            raise ValueError("Official website request failed.") from exc

    raise ValueError("Official website exceeded CityBuddy's redirect limit.")


def fetch_official_site(
    *,
    place_id: int,
    place_name: str,
    website: str,
    page_type: OfficialPageType,
    query: str | None = None,
    client: httpx.Client | None = None,
    resolver: Callable[[str, int], set[str]] = _default_resolver,
) -> OfficialSiteEvidence:
    """Fetch bounded evidence from only the reviewed place's stored official domain."""

    official_url = _normalize_official_url(website)
    official_host = urlsplit(official_url).hostname
    assert official_host is not None

    owns_client = client is None
    http_client = client or httpx.Client(timeout=REQUEST_TIMEOUT)
    try:
        try:
            source_url, content, truncated = _request_page(
                http_client,
                official_url,
                official_host=official_host,
                resolver=resolver,
            )
        except StaticRetrievalBlockedError:
            return OfficialSiteEvidence(
                place_id=place_id,
                place_name=place_name,
                page_type=page_type,
                official_host=_canonical_host(official_host),
                source_url=official_url,
                fetched_at=datetime.now(timezone.utc),
                verified=False,
                reason="static_retrieval_blocked",
                title=None,
                text=None,
                truncated=False,
            )

        parsed = _extract_page(content)

        if query:
            # One bounded hop only. Rank links discovered on the reviewed homepage,
            # fetch at most a few top candidates, and keep whichever fetched page
            # has the strongest deterministic query evidence. The model never
            # supplies or selects a URL.
            best_url = source_url
            best_parser = parsed
            best_truncated = truncated
            best_score = _page_query_score(parsed, source_url=source_url, query=query)
            ranked = _rank_same_domain_links(
                parsed,
                base_url=source_url,
                page_type=page_type,
                official_host=official_host,
                query=query,
            )
            for candidate_url in ranked[:MAX_QUERY_CANDIDATE_PAGES]:
                try:
                    candidate_source, candidate_content, candidate_truncated = _request_page(
                        http_client,
                        candidate_url,
                        official_host=official_host,
                        resolver=resolver,
                    )
                except (StaticRetrievalBlockedError, ValueError):
                    # A broken/blocked candidate must not discard a readable reviewed
                    # homepage or prevent trying another bounded same-domain candidate.
                    continue
                candidate_parser = _extract_page(candidate_content)
                candidate_score = _page_query_score(
                    candidate_parser,
                    source_url=candidate_source,
                    query=query,
                )
                if candidate_score > best_score:
                    best_url = candidate_source
                    best_parser = candidate_parser
                    best_truncated = truncated or candidate_truncated
                    best_score = candidate_score
            source_url = best_url
            parsed = best_parser
            truncated = best_truncated
        else:
            selected = _choose_same_domain_link(
                parsed,
                base_url=source_url,
                page_type=page_type,
                official_host=official_host,
                query=None,
            )
            if selected is not None and selected != source_url:
                source_url, content, selected_truncated = _request_page(
                    http_client,
                    selected,
                    official_host=official_host,
                    resolver=resolver,
                )
                parsed = _extract_page(content)
                truncated = truncated or selected_truncated

        text = parsed.text.strip()
        if len(text) > MAX_TEXT_CHARS:
            text = text[:MAX_TEXT_CHARS].rstrip()
            truncated = True
        if not text:
            return OfficialSiteEvidence(
                place_id=place_id,
                place_name=place_name,
                page_type=page_type,
                official_host=_canonical_host(official_host),
                source_url=source_url,
                fetched_at=datetime.now(timezone.utc),
                verified=False,
                reason="no_readable_static_content",
                title=parsed.title,
                text=None,
                truncated=truncated,
            )

        return OfficialSiteEvidence(
            place_id=place_id,
            place_name=place_name,
            page_type=page_type,
            official_host=_canonical_host(official_host),
            source_url=source_url,
            fetched_at=datetime.now(timezone.utc),
            verified=True,
            reason=None,
            title=parsed.title,
            text=text,
            truncated=truncated,
        )
    finally:
        if owns_client:
            http_client.close()
