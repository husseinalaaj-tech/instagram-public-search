from __future__ import annotations

import io
import json
import random
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import pandas as pd
import streamlit as st

try:
    from ddgs import DDGS
    from ddgs.exceptions import (
        DDGSException,
        RatelimitException,
        TimeoutException,
    )
except ImportError:
    st.error(
        "Missing dependency: ddgs\n\n"
        "Install it with: pip install -U ddgs"
    )
    st.stop()


APP_TITLE = "Instagram Google Public Discovery"
APP_VERSION = "2.0.0"

GOOGLE_BACKEND = "google"

DEFAULT_RESULTS_PER_QUERY = 10
DEFAULT_MAX_QUERIES = 70

DEFAULT_DELAY_MIN = 0.20
DEFAULT_DELAY_MAX = 0.45

DEFAULT_TIMEOUT = 10
DEFAULT_RETRIES = 2

DEFAULT_REGION = "us-en"
DEFAULT_SAFESEARCH = "off"


SCORE = {
    "exact_username_title": 15,
    "exact_mention_title": 20,
    "exact_username_snippet": 14,
    "exact_mention_snippet": 20,
    "exact_username_url": 7,
    "instagram_domain": 5,
    "post": 10,
    "reel": 13,
    "comment_keyword": 8,
    "mention_keyword": 7,
    "tag_keyword": 4,
    "query_match": 4,
    "repeat_discovery": 3,
    "distinct_snippet": 2,
}


TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_name",
    "gclid",
    "fbclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "ref_src",
    "ref_url",
}


@dataclass(frozen=True)
class SearchQuery:
    text: str
    category: str
    intent: str


@dataclass
class SearchResult:
    score: int
    result_type: str

    title: str
    url: str
    snippet: str
    domain: str

    backend: str

    query: str
    query_category: str
    query_intent: str

    discovered_at: str

    username_match: bool
    mention_match: bool
    comment_match: bool
    tag_match: bool
    reel_match: bool
    post_match: bool

    discovery_count: int = 1
    distinct_snippets: int = 1

    queries_seen: list[str] = field(default_factory=list)
    snippets_seen: list[str] = field(default_factory=list)


def initialize_session_state() -> None:
    defaults = {
        "results": [],
        "errors": [],
        "searched_username": "",
        "search_completed": False,
        "search_running": False,
        "stop_requested": False,
        "successful_queries": 0,
        "failed_queries": 0,
        "total_queries": 0,
        "completed_queries": 0,
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def reset_search_state() -> None:
    st.session_state.results = []
    st.session_state.errors = []

    st.session_state.search_completed = False
    st.session_state.search_running = False
    st.session_state.stop_requested = False

    st.session_state.successful_queries = 0
    st.session_state.failed_queries = 0
    st.session_state.total_queries = 0
    st.session_state.completed_queries = 0


def normalize_username(value: str) -> str:
    value = (value or "").strip()

    if not value:
        return ""

    url_match = re.search(
        r"(?:https?://)?(?:www\.)?instagram\.com/([^/?#]+)/?",
        value,
        re.IGNORECASE,
    )

    if url_match:
        value = url_match.group(1)

    value = value.strip()
    value = value.lstrip("@")
    value = value.strip("/")

    return value


def validate_username(username: str) -> tuple[bool, str]:
    if not username:
        return False, "Enter an Instagram username."

    if len(username) > 30:
        return False, "Instagram username is too long."

    if not re.fullmatch(
        r"[A-Za-z0-9._]+",
        username,
    ):
        return (
            False,
            "Only letters, numbers, dots and underscores are allowed.",
        )

    return True, ""


def add_query(
    queries: list[SearchQuery],
    seen: set[str],
    text: str,
    category: str,
    intent: str,
) -> None:
    text = re.sub(
        r"\s+",
        " ",
        text.strip(),
    )

    if not text:
        return

    key = text.casefold()

    if key in seen:
        return

    seen.add(key)

    queries.append(
        SearchQuery(
            text=text,
            category=category,
            intent=intent,
        )
    )


def generate_queries(
    username: str,
    max_queries: int,
) -> list[SearchQuery]:

    queries: list[SearchQuery] = []
    seen: set[str] = set()

    u = username
    au = f"@{username}"

    # ---------------------------------------------------------
    # 1. Exact Instagram username
    # ---------------------------------------------------------

    exact_queries = [
        (
            f'site:instagram.com "{u}"',
            "Exact Username",
            "Exact username",
        ),
        (
            f'site:instagram.com "{au}"',
            "Exact Mention",
            "Exact @username",
        ),
        (
            f'site:instagram.com "{u}" Instagram',
            "Exact Username",
            "Username + Instagram",
        ),
        (
            f'site:instagram.com "{au}" Instagram',
            "Exact Mention",
            "@username + Instagram",
        ),
    ]

    for text, category, intent in exact_queries:
        add_query(
            queries,
            seen,
            text,
            category,
            intent,
        )

    # ---------------------------------------------------------
    # 2. Posts
    # ---------------------------------------------------------

    post_terms = [
        "comment",
        "comments",
        "commented",
        "mention",
        "mentioned",
        "tag",
        "tagged",
        "caption",
    ]

    for term in post_terms:

        add_query(
            queries,
            seen,
            f'site:instagram.com/p/ "{u}" "{term}"',
            "Instagram Posts",
            f'Post + exact username + "{term}"',
        )

        add_query(
            queries,
            seen,
            f'site:instagram.com/p/ "{au}" "{term}"',
            "Instagram Posts",
            f'Post + exact @username + "{term}"',
        )

    add_query(
        queries,
        seen,
        f'site:instagram.com/p/ "{u}"',
        "Instagram Posts",
        "Exact username inside indexed post",
    )

    add_query(
        queries,
        seen,
        f'site:instagram.com/p/ "{au}"',
        "Instagram Posts",
        "Exact @username inside indexed post",
    )

    # ---------------------------------------------------------
    # 3. Reels
    # ---------------------------------------------------------

    for term in post_terms:

        add_query(
            queries,
            seen,
            f'site:instagram.com/reel/ "{u}" "{term}"',
            "Instagram Reels",
            f'Reel + exact username + "{term}"',
        )

        add_query(
            queries,
            seen,
            f'site:instagram.com/reel/ "{au}" "{term}"',
            "Instagram Reels",
            f'Reel + exact @username + "{term}"',
        )

    add_query(
        queries,
        seen,
        f'site:instagram.com/reel/ "{u}"',
        "Instagram Reels",
        "Exact username inside indexed Reel",
    )

    add_query(
        queries,
        seen,
        f'site:instagram.com/reel/ "{au}"',
        "Instagram Reels",
        "Exact @username inside indexed Reel",
    )

    add_query(
        queries,
        seen,
        f'site:instagram.com/reels/ "{u}"',
        "Instagram Reels",
        "Alternative Reels URL pattern",
    )

    add_query(
        queries,
        seen,
        f'site:instagram.com/reels/ "{au}"',
        "Instagram Reels",
        "Alternative Reels URL pattern",
    )

    # ---------------------------------------------------------
    # 4. Comments
    # ---------------------------------------------------------

    comment_queries = [
        f'site:instagram.com "{u}" comment',
        f'site:instagram.com "{au}" comment',
        f'site:instagram.com "{u}" comments',
        f'site:instagram.com "{au}" comments',
        f'site:instagram.com "{u}" commented',
        f'site:instagram.com "{au}" commented',
        f'site:instagram.com "{u}" commenting',
        f'site:instagram.com "{au}" commenting',
        f'site:instagram.com/p/ "{u}" comment',
        f'site:instagram.com/p/ "{au}" comment',
        f'site:instagram.com/p/ "{u}" comments',
        f'site:instagram.com/p/ "{au}" comments',
        f'site:instagram.com/reel/ "{u}" comment',
        f'site:instagram.com/reel/ "{au}" comment',
        f'site:instagram.com/reel/ "{u}" comments',
        f'site:instagram.com/reel/ "{au}" comments',
    ]

    for text in comment_queries:
        add_query(
            queries,
            seen,
            text,
            "Comments",
            "Exact username comment discovery",
        )

    # ---------------------------------------------------------
    # 5. Mentions
    # ---------------------------------------------------------

    mention_queries = [
        f'site:instagram.com "{au}" mention',
        f'site:instagram.com "{au}" mentions',
        f'site:instagram.com "{au}" mentioned',
        f'site:instagram.com/p/ "{au}" mention',
        f'site:instagram.com/p/ "{au}" mentions',
        f'site:instagram.com/p/ "{au}" mentioned',
        f'site:instagram.com/reel/ "{au}" mention',
        f'site:instagram.com/reel/ "{au}" mentions',
        f'site:instagram.com/reel/ "{au}" mentioned',
    ]

    for text in mention_queries:
        add_query(
            queries,
            seen,
            text,
            "Mentions",
            "Exact @username mention discovery",
        )

    # ---------------------------------------------------------
    # 6. Tags
    # ---------------------------------------------------------

    tag_queries = [
        f'site:instagram.com "{au}" tag',
        f'site:instagram.com "{au}" tagged',
        f'site:instagram.com "{au}" tags',
        f'site:instagram.com/p/ "{au}" tagged',
        f'site:instagram.com/p/ "{au}" tag',
        f'site:instagram.com/reel/ "{au}" tagged',
        f'site:instagram.com/reel/ "{au}" tag',
    ]

    for text in tag_queries:
        add_query(
            queries,
            seen,
            text,
            "Tags",
            "Exact @username tag discovery",
        )

    # ---------------------------------------------------------
    # 7. Highly specific combinations
    # ---------------------------------------------------------

    combinations = [
        (
            f'site:instagram.com/p/ "{au}" "comment" "mention"',
            "Post Intelligence",
        ),
        (
            f'site:instagram.com/p/ "{au}" "comment" "tagged"',
            "Post Intelligence",
        ),
        (
            f'site:instagram.com/reel/ "{au}" "comment" "mention"',
            "Reel Intelligence",
        ),
        (
            f'site:instagram.com/reel/ "{au}" "comment" "tagged"',
            "Reel Intelligence",
        ),
        (
            f'site:instagram.com "{au}" "comment" "mentioned"',
            "Comment Intelligence",
        ),
        (
            f'site:instagram.com "{au}" "comment" "tagged"',
            "Comment Intelligence",
        ),
    ]

    for text, category in combinations:
        add_query(
            queries,
            seen,
            text,
            category,
            "Exact username + multiple indicators",
        )

    return queries[:max_queries]


def normalize_url(url: str) -> str:
    if not url:
        return ""

    try:
        parsed = urlsplit(
            url.strip()
        )

        scheme = parsed.scheme.lower()

        netloc = parsed.netloc.lower()

        if netloc.startswith("www."):
            netloc = netloc[4:]

        path = re.sub(
            r"/{2,}",
            "/",
            parsed.path or "/",
        )

        if path != "/" and path.endswith("/"):
            path = path[:-1]

        params = []

        for key, value in parse_qsl(
            parsed.query,
            keep_blank_values=True,
        ):
            if key.lower() in TRACKING_PARAMS:
                continue

            params.append(
                (key, value)
            )

        params.sort()

        query = urlencode(
            params,
            doseq=True,
        )

        return urlunsplit(
            (
                scheme,
                netloc,
                path,
                query,
                "",
            )
        )

    except Exception:
        return url.split(
            "#",
            1,
        )[0]


def url_key(url: str) -> str:
    return normalize_url(
        url
    ).casefold()


def get_domain(url: str) -> str:
    try:
        domain = urlsplit(
            url
        ).netloc.lower()

        if domain.startswith("www."):
            domain = domain[4:]

        return domain

    except Exception:
        return ""


def is_instagram_url(url: str) -> bool:
    domain = get_domain(
        url
    )

    return (
        domain == "instagram.com"
        or domain.endswith(".instagram.com")
    )


def username_regex(
    username: str,
) -> re.Pattern:

    return re.compile(
        rf"(?<![A-Za-z0-9._])"
        rf"@?{re.escape(username)}"
        rf"(?![A-Za-z0-9._])",
        re.IGNORECASE,
    )


def mention_regex(
    username: str,
) -> re.Pattern:

    return re.compile(
        rf"(?<![A-Za-z0-9._])"
        rf"@{re.escape(username)}"
        rf"(?![A-Za-z0-9._])",
        re.IGNORECASE,
    )


def contains_word(
    text: str,
    words: list[str],
) -> bool:

    if not text:
        return False

    for word in words:

        if re.search(
            rf"(?<![A-Za-z])"
            rf"{re.escape(word)}"
            rf"(?![A-Za-z])",
            text,
            re.IGNORECASE,
        ):
            return True

    return False


def classify_result(
    url: str,
) -> str:

    path = urlsplit(
        url.lower()
    ).path

    if re.search(
        r"/reel/",
        path,
    ):
        return "Instagram Reel"

    if re.search(
        r"/reels/",
        path,
    ):
        return "Instagram Reel"

    if re.search(
        r"/p/",
        path,
    ):
        return "Instagram Post"

    if re.search(
        r"/tv/",
        path,
    ):
        return "Instagram Video"

    clean_path = path.strip("/")

    if clean_path and "/" not in clean_path:
        return "Instagram Profile"

    return "Instagram Page"


def calculate_score(
    username: str,
    title: str,
    snippet: str,
    url: str,
    query: SearchQuery,
) -> tuple[int, dict[str, bool]]:

    title = title or ""
    snippet = snippet or ""
    url = url or ""

    u_re = username_regex(
        username
    )

    m_re = mention_regex(
        username
    )

    exact_username_title = bool(
        u_re.search(title)
    )

    exact_mention_title = bool(
        m_re.search(title)
    )

    exact_username_snippet = bool(
        u_re.search(snippet)
    )

    exact_mention_snippet = bool(
        m_re.search(snippet)
    )

    exact_username_url = bool(
        u_re.search(url)
    )

    combined = (
        f"{title} "
        f"{snippet} "
        f"{url}"
    )

    comment_match = contains_word(
        combined,
        [
            "comment",
            "comments",
            "commented",
            "commenting",
        ],
    )

    mention_match = contains_word(
        combined,
        [
            "mention",
            "mentions",
            "mentioned",
        ],
    )

    tag_match = contains_word(
        combined,
        [
            "tag",
            "tags",
            "tagged",
        ],
    )

    reel_match = bool(
        re.search(
            r"instagram\.com/(?:reel|reels)/",
            url,
            re.IGNORECASE,
        )
    )

    post_match = bool(
        re.search(
            r"instagram\.com/p/",
            url,
            re.IGNORECASE,
        )
    )

    score = 0

    if exact_username_title:
        score += SCORE[
            "exact_username_title"
        ]

    if exact_mention_title:
        score += SCORE[
            "exact_mention_title"
        ]

    if exact_username_snippet:
        score += SCORE[
            "exact_username_snippet"
        ]

    if exact_mention_snippet:
        score += SCORE[
            "exact_mention_snippet"
        ]

    if exact_username_url:
        score += SCORE[
            "exact_username_url"
        ]

    score += SCORE[
        "instagram_domain"
    ]

    if post_match:
        score += SCORE["post"]

    if reel_match:
        score += SCORE["reel"]

    if comment_match:
        score += SCORE[
            "comment_keyword"
        ]

    if mention_match:
        score += SCORE[
            "mention_keyword"
        ]

    if tag_match:
        score += SCORE[
            "tag_keyword"
        ]

    if (
        query.category
        in {
            "Comments",
            "Mentions",
            "Tags",
            "Post Intelligence",
            "Reel Intelligence",
            "Comment Intelligence",
        }
    ):
        score += SCORE[
            "query_match"
        ]

    return score, {
        "username_match": (
            exact_username_title
            or exact_username_snippet
            or exact_username_url
        ),
        "mention_match": (
            exact_mention_title
            or exact_mention_snippet
            or bool(
                m_re.search(url)
            )
        ),
        "comment_match": comment_match,
        "tag_match": tag_match,
        "reel_match": reel_match,
        "post_match": post_match,
    }


class GoogleSearchProvider:

    def __init__(
        self,
        timeout: int,
    ):
        self.client = DDGS(
            timeout=timeout
        )

    def search(
        self,
        query: str,
        region: str,
        safesearch: str,
        max_results: int,
    ) -> list[dict]:

        results = self.client.text(
            query=query,
            backend=GOOGLE_BACKEND,
            region=region,
            safesearch=safesearch,
            max_results=max_results,
            page=1,
        )

        return list(
            results or []
        )


def extract_result(
    raw: dict,
    search_query: SearchQuery,
    username: str,
) -> SearchResult | None:

    if not isinstance(
        raw,
        dict,
    ):
        return None

    title = str(
        raw.get("title")
        or raw.get("name")
        or ""
    ).strip()

    url = str(
        raw.get("href")
        or raw.get("url")
        or ""
    ).strip()

    snippet = str(
        raw.get("body")
        or raw.get("snippet")
        or raw.get("description")
        or ""
    ).strip()

    if not url:
        return None

    clean_url = normalize_url(
        url
    )

    if not is_instagram_url(
        clean_url
    ):
        return None

    score, matches = calculate_score(
        username=username,
        title=title,
        snippet=snippet,
        url=clean_url,
        query=search_query,
    )

    return SearchResult(
        score=score,
        result_type=classify_result(
            clean_url
        ),
        title=title,
        url=clean_url,
        snippet=snippet,
        domain=get_domain(
            clean_url
        ),
        backend=GOOGLE_BACKEND,
        query=search_query.text,
        query_category=search_query.category,
        query_intent=search_query.intent,
        discovered_at=datetime.now(
            timezone.utc
        ).isoformat(),
        username_match=matches[
            "username_match"
        ],
        mention_match=matches[
            "mention_match"
        ],
        comment_match=matches[
            "comment_match"
        ],
        tag_match=matches[
            "tag_match"
        ],
        reel_match=matches[
            "reel_match"
        ],
        post_match=matches[
            "post_match"
        ],
        discovery_count=1,
        distinct_snippets=1,
        queries_seen=[
            search_query.text
        ],
        snippets_seen=[
            snippet
        ]
        if snippet
        else [],
    )


def merge_result(
    store: dict[str, SearchResult],
    result: SearchResult,
) -> None:

    key = url_key(
        result.url
    )

    if not key:
        return

    if key not in store:

        store[key] = result
        return

    existing = store[key]

    existing.discovery_count += 1

    if result.query not in existing.queries_seen:

        existing.queries_seen.append(
            result.query
        )

    if (
        result.snippet
        and result.snippet
        not in existing.snippets_seen
    ):

        existing.snippets_seen.append(
            result.snippet
        )

        existing.distinct_snippets = len(
            existing.snippets_seen
        )

    existing.username_match = (
        existing.username_match
        or result.username_match
    )

    existing.mention_match = (
        existing.mention_match
        or result.mention_match
    )

    existing.comment_match = (
        existing.comment_match
        or result.comment_match
    )

    existing.tag_match = (
        existing.tag_match
        or result.tag_match
    )

    existing.reel_match = (
        existing.reel_match
        or result.reel_match
    )

    existing.post_match = (
        existing.post_match
        or result.post_match
    )

    if (
        result.score
        > existing.score
    ):

        best_snippet = result.snippet

        existing.score = result.score
        existing.title = result.title or existing.title
        existing.query = result.query
        existing.query_category = (
            result.query_category
        )
        existing.query_intent = (
            result.query_intent
        )

        if best_snippet:
            existing.snippet = best_snippet

    existing.score += SCORE[
        "repeat_discovery"
    ]

    if existing.distinct_snippets > 1:
        existing.score += SCORE[
            "distinct_snippet"
        ]


def sort_results(
    store: dict[str, SearchResult],
) -> list[SearchResult]:

    results = list(
        store.values()
    )

    results.sort(
        key=lambda result: (
            -result.score,
            -result.discovery_count,
            -result.distinct_snippets,
            not result.comment_match,
            not result.mention_match,
            not result.reel_match,
            not result.post_match,
            result.domain,
        )
    )

    return results


def randomized_delay(
    minimum: float,
    maximum: float,
) -> None:

    if maximum <= 0:
        return

    minimum = max(
        0.0,
        minimum,
    )

    maximum = max(
        minimum,
        maximum,
    )

    time.sleep(
        random.uniform(
            minimum,
            maximum,
        )
    )


def execute_google_query(
    provider: GoogleSearchProvider,
    search_query: SearchQuery,
    username: str,
    settings: dict,
) -> tuple[list[SearchResult], str | None]:

    last_error = None

    for attempt in range(
        settings["retries"] + 1
    ):

        if st.session_state.stop_requested:

            return (
                [],
                "Search stopped by user.",
            )

        try:

            if attempt > 0:

                backoff = min(
                    10.0,
                    (2 ** attempt)
                    + random.uniform(
                        0.2,
                        0.8,
                    ),
                )

                time.sleep(
                    backoff
                )

            raw_results = provider.search(
                query=search_query.text,
                region=settings["region"],
                safesearch=settings[
                    "safesearch"
                ],
                max_results=settings[
                    "results_per_query"
                ],
            )

            results = []

            for raw in raw_results:

                result = extract_result(
                    raw=raw,
                    search_query=search_query,
                    username=username,
                )

                if result:
                    results.append(
                        result
                    )

            return (
                results,
                None,
            )

        except RatelimitException as exc:

            last_error = (
                f"Google rate limit / provider "
                f"rate limit: {exc}"
            )

        except TimeoutException as exc:

            last_error = (
                f"Google timeout: {exc}"
            )

        except DDGSException as exc:

            last_error = (
                f"DDGS Google backend error: {exc}"
            )

        except Exception as exc:

            last_error = (
                f"{type(exc).__name__}: {exc}"
            )

        if attempt < settings[
            "retries"
        ]:

            randomized_delay(
                settings["delay_min"],
                settings["delay_max"],
            )

    return (
        [],
        last_error
        or "Unknown Google search error.",
    )


def results_dataframe(
    results: list[SearchResult],
) -> pd.DataFrame:

    rows = []

    for result in results:

        rows.append(
            {
                "Score": result.score,
                "Discovery Count": result.discovery_count,
                "Distinct Snippets": result.distinct_snippets,
                "Type": result.result_type,
                "Title": result.title,
                "Post / Reel URL": result.url,
                "Snippet": result.snippet,
                "Domain": result.domain,
                "Backend": result.backend,
                "Query": result.query,
                "Query Category": result.query_category,
                "Query Intent": result.query_intent,
                "Discovered At": result.discovered_at,
                "Username Match": result.username_match,
                "@Mention Match": result.mention_match,
                "Comment Match": result.comment_match,
                "Tag Match": result.tag_match,
                "Reel Match": result.reel_match,
                "Post Match": result.post_match,
                "Different Queries": len(
                    result.queries_seen
                ),
                "Different Snippets": len(
                    result.snippets_seen
                ),
            }
        )

    return pd.DataFrame(
        rows,
        columns=[
            "Score",
            "Discovery Count",
            "Distinct Snippets",
            "Type",
            "Title",
            "Post / Reel URL",
            "Snippet",
            "Domain",
            "Backend",
            "Query",
            "Query Category",
            "Query Intent",
            "Discovered At",
            "Username Match",
            "@Mention Match",
            "Comment Match",
            "Tag Match",
            "Reel Match",
            "Post Match",
            "Different Queries",
            "Different Snippets",
        ],
    )


def statistics_dataframe(
    results: list[SearchResult],
) -> pd.DataFrame:

    counter = Counter(
        result.result_type
        for result in results
    )

    rows = [
        {
            "Metric": "Unique Instagram URLs",
            "Value": len(results),
        },
        {
            "Metric": "Total Discovery Events",
            "Value": sum(
                result.discovery_count
                for result in results
            ),
        },
        {
            "Metric": "Distinct Snippets",
            "Value": sum(
                result.distinct_snippets
                for result in results
            ),
        },
        {
            "Metric": "Comment Matches",
            "Value": sum(
                result.comment_match
                for result in results
            ),
        },
        {
            "Metric": "Mention Matches",
            "Value": sum(
                result.mention_match
                for result in results
            ),
        },
        {
            "Metric": "Tagged Matches",
            "Value": sum(
                result.tag_match
                for result in results
            ),
        },
        {
            "Metric": "Instagram Posts",
            "Value": counter.get(
                "Instagram Post",
                0,
            ),
        },
        {
            "Metric": "Instagram Reels",
            "Value": counter.get(
                "Instagram Reel",
                0,
            ),
        },
    ]

    return pd.DataFrame(
        rows
    )


def csv_bytes(
    dataframe: pd.DataFrame,
) -> bytes:

    return dataframe.to_csv(
        index=False
    ).encode(
        "utf-8-sig"
    )


def json_bytes(
    dataframe: pd.DataFrame,
) -> bytes:

    return json.dumps(
        dataframe.to_dict(
            orient="records"
        ),
        ensure_ascii=False,
        indent=2,
        default=str,
    ).encode(
        "utf-8"
    )


def excel_bytes(
    results_df: pd.DataFrame,
    stats_df: pd.DataFrame,
) -> bytes:

    buffer = io.BytesIO()

    with pd.ExcelWriter(
        buffer,
        engine="openpyxl",
    ) as writer:

        results_df.to_excel(
            writer,
            index=False,
            sheet_name="Results",
        )

        stats_df.to_excel(
            writer,
            index=False,
            sheet_name="Statistics",
        )

    return buffer.getvalue()


def render_sidebar() -> dict:

    with st.sidebar:

        st.header(
            "Google Search Settings"
        )

        st.success(
            "Google backend: ACTIVE"
        )

        results_per_query = st.slider(
            "Results per query",
            3,
            20,
            DEFAULT_RESULTS_PER_QUERY,
        )

        max_queries = st.slider(
            "Maximum queries",
            10,
            100,
            DEFAULT_MAX_QUERIES,
            step=5,
        )

        st.divider()

        st.subheader(
            "Speed / Rate Control"
        )

        delay_min = st.slider(
            "Minimum delay",
            0.10,
            3.0,
            DEFAULT_DELAY_MIN,
            0.05,
        )

        delay_max = st.slider(
            "Maximum delay",
            0.10,
            5.0,
            DEFAULT_DELAY_MAX,
            0.05,
        )

        timeout = st.slider(
            "Timeout",
            5,
            30,
            DEFAULT_TIMEOUT,
        )

        retries = st.slider(
            "Retries",
            0,
            3,
            DEFAULT_RETRIES,
        )

        st.divider()

        region = st.selectbox(
            "Google region",
            [
                "us-en",
                "uk-en",
                "ca-en",
                "au-en",
                "in-en",
                "tr-tr",
                "ar-sa",
                "xa-en",
                "de-de",
                "fr-fr",
            ],
            index=0,
        )

        safesearch = st.selectbox(
            "SafeSearch",
            [
                "off",
                "moderate",
                "on",
            ],
            index=0,
        )

        st.divider()

        st.caption(
            f"Instagram-only • Google • v{APP_VERSION}"
        )

        st.caption(
            "Public/indexed information only."
        )

    return {
        "results_per_query": results_per_query,
        "max_queries": max_queries,
        "delay_min": min(
            delay_min,
            delay_max,
        ),
        "delay_max": max(
            delay_min,
            delay_max,
        ),
        "timeout": timeout,
        "retries": retries,
        "region": region,
        "safesearch": safesearch,
    }


def render_live_results(
    results: list[SearchResult],
    placeholder,
) -> None:

    if not results:

        placeholder.info(
            "Waiting for the first Google result..."
        )

        return

    dataframe = results_dataframe(
        results
    )

    placeholder.dataframe(
        dataframe,
        use_container_width=True,
        hide_index=True,
        height=600,
        column_config={
            "Score": st.column_config.NumberColumn(
                "Score",
                format="%d",
            ),
            "Discovery Count": st.column_config.NumberColumn(
                "Discovery Count",
                format="%d",
            ),
            "Distinct Snippets": st.column_config.NumberColumn(
                "Distinct Snippets",
                format="%d",
            ),
            "Post / Reel URL": st.column_config.LinkColumn(
                "Post / Reel URL",
                display_text="Open Instagram",
            ),
            "Title": st.column_config.TextColumn(
                "Title",
                width="large",
            ),
            "Snippet": st.column_config.TextColumn(
                "Snippet",
                width="large",
            ),
            "Query": st.column_config.TextColumn(
                "Query",
                width="large",
            ),
        },
    )


def perform_search(
    username: str,
    settings: dict,
) -> None:

    queries = generate_queries(
        username=username,
        max_queries=settings[
            "max_queries"
        ],
    )

    reset_search_state()

    st.session_state.searched_username = username
    st.session_state.total_queries = len(
        queries
    )
    st.session_state.search_running = True

    provider = GoogleSearchProvider(
        timeout=settings[
            "timeout"
        ]
    )

    result_store: dict[
        str,
        SearchResult,
    ] = {}

    progress = st.empty()
    status = st.empty()
    live_info = st.empty()
    live_results = st.empty()

    for number, query in enumerate(
        queries,
        start=1,
    ):

        if st.session_state.stop_requested:
            break

        progress.progress(
            int(
                (
                    (number - 1)
                    / max(
                        len(queries),
                        1,
                    )
                )
                * 100
            ),
            text=(
                f"Google Query "
                f"{number} / {len(queries)}"
            ),
        )

        status.info(
            f"🔎 **Google Query {number} / {len(queries)}**\n\n"
            f"**Category:** {query.category}\n\n"
            f"**Intent:** {query.intent}\n\n"
            f"`{query.text}`"
        )

        results, error = execute_google_query(
            provider=provider,
            search_query=query,
            username=username,
            settings=settings,
        )

        if error:

            if error == "Search stopped by user.":
                break

            st.session_state.failed_queries += 1

            st.session_state.errors.append(
                {
                    "number": number,
                    "query": query.text,
                    "category": query.category,
                    "error": error,
                }
            )

        else:

            st.session_state.successful_queries += 1

            for result in results:

                merge_result(
                    result_store,
                    result,
                )

        current_results = sort_results(
            result_store
        )

        st.session_state.results = (
            current_results
        )

        st.session_state.completed_queries = (
            number
        )

        comments = sum(
            result.comment_match
            for result in current_results
        )

        mentions = sum(
            result.mention_match
            for result in current_results
        )

        posts = sum(
            result.post_match
            for result in current_results
        )

        reels = sum(
            result.reel_match
            for result in current_results
        )

        total_discoveries = sum(
            result.discovery_count
            for result in current_results
        )

        live_info.markdown(
            f"""
### Live Google Results

**Unique URLs:** `{len(current_results)}`

**Discovery events:** `{total_discoveries}`

**Comments:** `{comments}`

**Mentions:** `{mentions}`

**Posts:** `{posts}`

**Reels:** `{reels}`

**Failed queries:** `{st.session_state.failed_queries}`
"""
        )

        render_live_results(
            current_results,
            live_results,
        )

        if (
            number < len(queries)
            and not st.session_state.stop_requested
        ):

            randomized_delay(
                settings["delay_min"],
                settings["delay_max"],
            )

    final_results = sort_results(
        result_store
    )

    st.session_state.results = (
        final_results
    )

    st.session_state.search_running = False
    st.session_state.search_completed = True

    if st.session_state.stop_requested:

        status.warning(
            f"⏹️ Search stopped after "
            f"{st.session_state.completed_queries} "
            f"/ {len(queries)} Google queries."
        )

    else:

        progress.progress(
            100,
            text="Google search completed.",
        )

        status.success(
            f"✅ Google search completed. "
            f"{len(final_results)} unique Instagram URLs found."
        )


def render_statistics(
    results: list[SearchResult],
) -> None:

    counter = Counter(
        result.result_type
        for result in results
    )

    cols = st.columns(7)

    cols[0].metric(
        "Unique URLs",
        len(results),
    )

    cols[1].metric(
        "Discovery Events",
        sum(
            r.discovery_count
            for r in results
        ),
    )

    cols[2].metric(
        "Comments",
        sum(
            r.comment_match
            for r in results
        ),
    )

    cols[3].metric(
        "Mentions",
        sum(
            r.mention_match
            for r in results
        ),
    )

    cols[4].metric(
        "Posts",
        counter.get(
            "Instagram Post",
            0,
        ),
    )

    cols[5].metric(
        "Reels",
        counter.get(
            "Instagram Reel",
            0,
        ),
    )

    cols[6].metric(
        "Distinct Snippets",
        sum(
            r.distinct_snippets
            for r in results
        ),
    )


def render_errors() -> None:

    errors = st.session_state.errors

    if not errors:
        return

    with st.expander(
        f"⚠️ Failed Google queries ({len(errors)})"
    ):

        for error in errors:

            st.error(
                f"Query {error['number']}\n\n"
                f"{error['query']}\n\n"
                f"{error['error']}"
            )


def render_filters(
    results: list[SearchResult],
) -> pd.DataFrame:

    dataframe = results_dataframe(
        results
    )

    if dataframe.empty:
        return dataframe

    st.subheader(
        "Result Filters"
    )

    cols = st.columns(5)

    with cols[0]:

        types = st.multiselect(
            "Type",
            sorted(
                dataframe[
                    "Type"
                ].unique()
            ),
        )

    with cols[1]:

        categories = st.multiselect(
            "Query Category",
            sorted(
                dataframe[
                    "Query Category"
                ].unique()
            ),
        )

    with cols[2]:

        max_score = max(
            int(
                dataframe[
                    "Score"
                ].max()
            ),
            1,
        )

        minimum_score = st.slider(
            "Minimum Score",
            0,
            max_score,
            0,
        )

    with cols[3]:

        min_discovery = st.number_input(
            "Minimum Discovery Count",
            min_value=1,
            max_value=max(
                int(
                    dataframe[
                        "Discovery Count"
                    ].max()
                ),
                1,
            ),
            value=1,
        )

    with cols[4]:

        search_text = st.text_input(
            "Search text",
            placeholder=(
                "Search title, snippet, username..."
            ),
        )

    filtered = dataframe.copy()

    if types:

        filtered = filtered[
            filtered["Type"].isin(
                types
            )
        ]

    if categories:

        filtered = filtered[
            filtered[
                "Query Category"
            ].isin(
                categories
            )
        ]

    filtered = filtered[
        filtered["Score"]
        >= minimum_score
    ]

    filtered = filtered[
        filtered[
            "Discovery Count"
        ]
        >= min_discovery
    ]

    if search_text.strip():

        needle = re.escape(
            search_text.strip()
        )

        mask = (
            filtered[
                "Title"
            ]
            .fillna("")
            .str.contains(
                needle,
                case=False,
                regex=True,
            )
            |
            filtered[
                "Snippet"
            ]
            .fillna("")
            .str.contains(
                needle,
                case=False,
                regex=True,
            )
            |
            filtered[
                "Post / Reel URL"
            ]
            .fillna("")
            .str.contains(
                needle,
                case=False,
                regex=True,
            )
            |
            filtered[
                "Query"
            ]
            .fillna("")
            .str.contains(
                needle,
                case=False,
                regex=True,
            )
        )

        filtered = filtered[
            mask
        ]

    return filtered.sort_values(
        by=[
            "Score",
            "Discovery Count",
            "Distinct Snippets",
        ],
        ascending=[
            False,
            False,
            False,
        ],
    )


def render_snippet_details(
    results: list[SearchResult],
) -> None:

    if not results:
        return

    st.subheader(
        "Different Indexed Snippets"
    )

    for index, result in enumerate(
        results[:50],
        start=1,
    ):

        if (
            len(
                result.snippets_seen
            )
            <= 1
        ):
            continue

        with st.expander(
            f"{index}. {result.title or result.url} "
            f"— {len(result.snippets_seen)} different snippets"
        ):

            st.markdown(
                f"**Instagram URL:** "
                f"{result.url}"
            )

            for snippet_number, snippet in enumerate(
                result.snippets_seen,
                start=1,
            ):

                st.markdown(
                    f"**Snippet {snippet_number}:** "
                    f"{snippet}"
                )

            if result.queries_seen:

                st.markdown(
                    "**Queries that discovered this URL:**"
                )

                for query in result.queries_seen:
                    st.code(
                        query,
                        language=None,
                    )


def render_exports(
    filtered: pd.DataFrame,
    all_results: list[SearchResult],
) -> None:

    st.subheader(
        "Export"
    )

    all_dataframe = results_dataframe(
        all_results
    )

    stats_dataframe = statistics_dataframe(
        all_results
    )

    cols = st.columns(3)

    with cols[0]:

        st.download_button(
            "⬇️ Download CSV",
            data=csv_bytes(
                filtered
            ),
            file_name=(
                "instagram_google_results.csv"
            ),
            mime="text/csv",
            use_container_width=True,
        )

    with cols[1]:

        st.download_button(
            "⬇️ Download Excel",
            data=excel_bytes(
                all_dataframe,
                stats_dataframe,
            ),
            file_name=(
                "instagram_google_results.xlsx"
            ),
            mime=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
            use_container_width=True,
        )

    with cols[2]:

        st.download_button(
            "⬇️ Download JSON",
            data=json_bytes(
                filtered
            ),
            file_name=(
                "instagram_google_results.json"
            ),
            mime="application/json",
            use_container_width=True,
        )


def main() -> None:

    st.set_page_config(
        page_title=APP_TITLE,
        page_icon="🔎",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    initialize_session_state()

    st.title(
        "🔎 Instagram Google Public Discovery"
    )

    st.caption(
        "Exact Instagram username / mention discovery "
        "using Google-indexed public results"
    )

    st.info(
        "Instagram only. The application searches public "
        "search-engine-indexed information. It does not log "
        "into Instagram or access private comments."
    )

    settings = render_sidebar()

    st.subheader(
        "Instagram Username"
    )

    username_input = st.text_input(
        "Username",
        placeholder="rrenguk or @rrenguk",
        disabled=st.session_state.search_running,
    )

    username = normalize_username(
        username_input
    )

    if username:

        st.caption(
            f"Exact search target: @{username}"
        )

    controls = st.columns(2)

    with controls[0]:

        start = st.button(
            "🚀 START GOOGLE SEARCH",
            type="primary",
            use_container_width=True,
            disabled=(
                st.session_state.search_running
            ),
        )

    with controls[1]:

        stop = st.button(
            "⏹️ STOP SEARCH",
            use_container_width=True,
            disabled=(
                not st.session_state.search_running
            ),
        )

    if stop:

        st.session_state.stop_requested = True

        st.warning(
            "Stop requested. The current Google request "
            "will finish before the loop stops."
        )

    if start:

        valid, error = validate_username(
            username
        )

        if not valid:

            st.error(
                error
            )

        else:

            query_preview = generate_queries(
                username=username,
                max_queries=settings[
                    "max_queries"
                ],
            )

            with st.expander(
                f"Google queries generated: "
                f"{len(query_preview)}",
                expanded=False,
            ):

                preview_df = pd.DataFrame(
                    [
                        {
                            "Category": q.category,
                            "Intent": q.intent,
                            "Google Query": q.text,
                        }
                        for q in query_preview
                    ]
                )

                st.dataframe(
                    preview_df,
                    use_container_width=True,
                    hide_index=True,
                )

            perform_search(
                username=username,
                settings=settings,
            )

    if st.session_state.search_completed:

        st.divider()

        st.header(
            f"Google Results for @{st.session_state.searched_username}"
        )

        render_statistics(
            st.session_state.results
        )

        cols = st.columns(2)

        cols[0].success(
            f"Successful Google Queries: "
            f"{st.session_state.successful_queries}"
        )

        if st.session_state.failed_queries:

            cols[1].warning(
                f"Failed Google Queries: "
                f"{st.session_state.failed_queries}"
            )

        else:

            cols[1].success(
                "Failed Google Queries: 0"
            )

        render_errors()

        filtered = render_filters(
            st.session_state.results
        )

        if not filtered.empty:

            st.subheader(
                f"Ranked Results ({len(filtered)})"
            )

            st.dataframe(
                filtered,
                use_container_width=True,
                hide_index=True,
                height=700,
                column_config={
                    "Score": st.column_config.NumberColumn(
                        "Score",
                        format="%d",
                    ),
                    "Discovery Count": st.column_config.NumberColumn(
                        "Discovery Count",
                        format="%d",
                    ),
                    "Distinct Snippets": st.column_config.NumberColumn(
                        "Distinct Snippets",
                        format="%d",
                    ),
                    "Post / Reel URL": st.column_config.LinkColumn(
                        "Post / Reel URL",
                        display_text="Open Instagram",
                    ),
                    "Title": st.column_config.TextColumn(
                        "Title",
                        width="large",
                    ),
                    "Snippet": st.column_config.TextColumn(
                        "Snippet",
                        width="large",
                    ),
                    "Query": st.column_config.TextColumn(
                        "Query",
                        width="large",
                    ),
                },
            )

            st.divider()

            render_snippet_details(
                st.session_state.results
            )

            st.divider()

            render_exports(
                filtered=filtered,
                all_results=st.session_state.results,
            )

        else:

            st.warning(
                "No results match the current filters."
            )

    elif not st.session_state.search_running:

        st.divider()

        st.subheader(
            "Search model"
        )

        st.write(
            "The tool uses exact quoted username and @username "
            "queries against Google, with Instagram restricted "
            "search operators. Results are then classified, "
            "scored, deduplicated and ranked."
        )

        st.warning(
            "Google indexing is the limiting factor: if an "
            "Instagram comment is not publicly indexed by Google, "
            "this application cannot retrieve that comment. "
            "Multiple different Google snippets for the same "
            "Post/Reel are retained and counted when available."
        )


if __name__ == "__main__":
    main()