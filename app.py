from __future__ import annotations

import io
import json
import random
import re
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import pandas as pd
import streamlit as st

try:
    from ddgs import DDGS
    from ddgs.exceptions import DDGSException, RatelimitException, TimeoutException
except ImportError:
    st.error("The 'ddgs' package is required. Install it with: pip install -U ddgs")
    st.stop()


APP_TITLE = "Instagram Public Comments Discovery"
APP_VERSION = "1.1.0"

DEFAULT_BACKEND = "auto"
DEFAULT_REGION = "us-en"
DEFAULT_SAFESEARCH = "moderate"

DEFAULT_RESULTS_PER_QUERY = 8
DEFAULT_MAX_QUERIES = 80

DEFAULT_DELAY_MIN = 0.25
DEFAULT_DELAY_MAX = 0.60

DEFAULT_TIMEOUT = 8
DEFAULT_RETRIES = 1


SUPPORTED_BACKENDS = [
    "auto",
    "bing",
    "brave",
    "duckduckgo",
    "google",
    "mojeek",
    "yahoo",
    "yandex",
]


SCORE_WEIGHTS = {
    "username_title": 10,
    "at_username_title": 14,
    "username_snippet": 8,
    "at_username_snippet": 14,
    "username_url": 5,
    "instagram_domain": 5,
    "instagram_post": 8,
    "instagram_reel": 10,
    "instagram_profile": 7,
    "comment": 6,
    "comments": 6,
    "commented": 5,
    "mention": 5,
    "mentions": 5,
    "mentioned": 5,
    "tag": 3,
    "tags": 3,
    "tagged": 4,
    "query_relevance": 3,
    "multiple_discoveries": 2,
}


TRACKING_PARAMETERS = {
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
    st.session_state.searched_username = ""
    st.session_state.search_completed = False
    st.session_state.search_running = False
    st.session_state.stop_requested = False
    st.session_state.successful_queries = 0
    st.session_state.failed_queries = 0
    st.session_state.total_queries = 0
    st.session_state.completed_queries = 0


def request_stop() -> None:
    st.session_state.stop_requested = True


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

    if not re.fullmatch(r"[A-Za-z0-9._]+", username):
        return (
            False,
            "Username can contain only letters, numbers, dots and underscores.",
        )

    return True, ""


def add_query(
    queries: list[SearchQuery],
    seen: set[str],
    text: str,
    category: str,
    intent: str,
) -> None:
    text = re.sub(r"\s+", " ", text.strip())

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


def generate_comment_queries(username: str) -> list[SearchQuery]:
    queries: list[SearchQuery] = []
    seen: set[str] = set()

    comment_words = [
        "comment",
        "comments",
        "commented",
        "commenting",
    ]

    mention_words = [
        "mention",
        "mentions",
        "mentioned",
    ]

    tag_words = [
        "tag",
        "tags",
        "tagged",
    ]

    # Direct comment discovery.
    for word in comment_words:
        add_query(
            queries,
            seen,
            f'site:instagram.com "{username}" {word}',
            "Comments",
            f"Username + {word}",
        )

        add_query(
            queries,
            seen,
            f'site:instagram.com "@{username}" {word}',
            "Comments",
            f"@username + {word}",
        )

        add_query(
            queries,
            seen,
            f'site:instagram.com "{username}" Instagram {word}',
            "Comments",
            f"Username + Instagram + {word}",
        )

        add_query(
            queries,
            seen,
            f'site:instagram.com "@{username}" Instagram {word}',
            "Comments",
            f"@username + Instagram + {word}",
        )

    # Instagram posts + comments.
    for word in comment_words:
        add_query(
            queries,
            seen,
            f'site:instagram.com/p/ "{username}" {word}',
            "Post Comments",
            f"Post + {word}",
        )

        add_query(
            queries,
            seen,
            f'site:instagram.com/p/ "@{username}" {word}',
            "Post Comments",
            f"Post + @{username} + {word}",
        )

    # Instagram reels + comments.
    for word in comment_words:
        add_query(
            queries,
            seen,
            f'site:instagram.com/reel/ "{username}" {word}',
            "Reel Comments",
            f"Reel + {word}",
        )

        add_query(
            queries,
            seen,
            f'site:instagram.com/reel/ "@{username}" {word}',
            "Reel Comments",
            f"Reel + @{username} + {word}",
        )

        add_query(
            queries,
            seen,
            f'site:instagram.com/reels/ "{username}" {word}',
            "Reel Comments",
            f"Reels + {word}",
        )

    # Mentions.
    for word in mention_words:
        add_query(
            queries,
            seen,
            f'site:instagram.com "{username}" {word}',
            "Mentions",
            f"Username + {word}",
        )

        add_query(
            queries,
            seen,
            f'site:instagram.com "@{username}" {word}',
            "Mentions",
            f"@username + {word}",
        )

        add_query(
            queries,
            seen,
            f'site:instagram.com/p/ "@{username}" {word}',
            "Post Mentions",
            f"Post + @{username} + {word}",
        )

        add_query(
            queries,
            seen,
            f'site:instagram.com/reel/ "@{username}" {word}',
            "Reel Mentions",
            f"Reel + @{username} + {word}",
        )

    # Tags.
    for word in tag_words:
        add_query(
            queries,
            seen,
            f'site:instagram.com "{username}" {word}',
            "Tags",
            f"Username + {word}",
        )

        add_query(
            queries,
            seen,
            f'site:instagram.com "@{username}" {word}',
            "Tags",
            f"@username + {word}",
        )

        add_query(
            queries,
            seen,
            f'site:instagram.com/p/ "@{username}" {word}',
            "Post Tags",
            f"Post + {word}",
        )

        add_query(
            queries,
            seen,
            f'site:instagram.com/reel/ "@{username}" {word}',
            "Reel Tags",
            f"Reel + {word}",
        )

    # Post discovery.
    post_queries = [
        f'site:instagram.com/p/ "{username}"',
        f'site:instagram.com/p/ "@{username}"',
        f'site:instagram.com/p/ "{username}" Instagram',
        f'site:instagram.com/p/ "@{username}" Instagram',
        f'site:instagram.com/p/ "{username}" caption',
        f'site:instagram.com/p/ "@{username}" caption',
        f'site:instagram.com/p/ "{username}" text',
        f'site:instagram.com/p/ "@{username}" text',
    ]

    for query in post_queries:
        add_query(
            queries,
            seen,
            query,
            "Instagram Posts",
            "Public indexed post discovery",
        )

    # Reel discovery.
    reel_queries = [
        f'site:instagram.com/reel/ "{username}"',
        f'site:instagram.com/reel/ "@{username}"',
        f'site:instagram.com/reel/ "{username}" Instagram',
        f'site:instagram.com/reel/ "@{username}" Instagram',
        f'site:instagram.com/reel/ "{username}" caption',
        f'site:instagram.com/reel/ "@{username}" caption',
        f'site:instagram.com/reel/ "{username}" comment',
        f'site:instagram.com/reel/ "@{username}" comment',
        f'site:instagram.com/reels/ "{username}"',
        f'site:instagram.com/reels/ "@{username}"',
    ]

    for query in reel_queries:
        add_query(
            queries,
            seen,
            query,
            "Instagram Reels",
            "Public indexed reel discovery",
        )

    # Exact username discovery.
    exact_queries = [
        f'site:instagram.com "{username}"',
        f'site:instagram.com "@{username}"',
        f'site:instagram.com "{username}" Instagram',
        f'site:instagram.com "@{username}" Instagram',
        f'site:instagram.com "{username}" profile',
        f'site:instagram.com "@{username}" profile',
    ]

    for query in exact_queries:
        add_query(
            queries,
            seen,
            query,
            "Indexed Instagram",
            "Exact username discovery",
        )

    # High-value combinations.
    combined_queries = [
        f'site:instagram.com "{username}" comment mention',
        f'site:instagram.com "@{username}" comment mention',
        f'site:instagram.com "{username}" comments mentions',
        f'site:instagram.com "@{username}" comments mentions',
        f'site:instagram.com "{username}" comment tagged',
        f'site:instagram.com "@{username}" comment tagged',
        f'site:instagram.com "{username}" mentioned tagged',
        f'site:instagram.com "@{username}" mentioned tagged',
        f'site:instagram.com/p/ "{username}" comment mention',
        f'site:instagram.com/p/ "@{username}" comment mention',
        f'site:instagram.com/reel/ "{username}" comment mention',
        f'site:instagram.com/reel/ "@{username}" comment mention',
    ]

    for query in combined_queries:
        add_query(
            queries,
            seen,
            query,
            "High Relevance",
            "Combined comment / mention / tag",
        )

    return queries


def generate_all_queries(
    username: str,
    max_queries: int,
) -> list[SearchQuery]:
    queries = generate_comment_queries(username)
    return queries[:max_queries]


def normalize_url(url: str) -> str:
    if not url:
        return ""

    try:
        parsed = urlsplit(url.strip())

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

        parameters = []

        for key, value in parse_qsl(
            parsed.query,
            keep_blank_values=True,
        ):
            if key.lower() in TRACKING_PARAMETERS:
                continue

            parameters.append((key, value))

        parameters.sort()

        query = urlencode(
            parameters,
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
        return url.split("#", 1)[0]


def url_key(url: str) -> str:
    return normalize_url(url).casefold()


def get_domain(url: str) -> str:
    try:
        domain = urlsplit(url).netloc.lower()

        if domain.startswith("www."):
            domain = domain[4:]

        return domain
    except Exception:
        return ""


def username_pattern(username: str) -> re.Pattern:
    return re.compile(
        rf"(?<![A-Za-z0-9._])@?{re.escape(username)}(?![A-Za-z0-9._])",
        re.IGNORECASE,
    )


def mention_pattern(username: str) -> re.Pattern:
    return re.compile(
        rf"(?<![A-Za-z0-9._])@{re.escape(username)}(?![A-Za-z0-9._])",
        re.IGNORECASE,
    )


def keyword_exists(
    text: str,
    words: list[str],
) -> bool:
    if not text:
        return False

    for word in words:
        if re.search(
            rf"\b{re.escape(word)}\b",
            text,
            re.IGNORECASE,
        ):
            return True

    return False


def classify_result(
    url: str,
    title: str,
    snippet: str,
) -> str:
    url_lower = url.lower()

    if re.search(
        r"instagram\.com/(?:reel|reels)/",
        url_lower,
    ):
        return "Instagram Reel"

    if re.search(
        r"instagram\.com/p/",
        url_lower,
    ):
        return "Instagram Post"

    if re.search(
        r"instagram\.com/(?:tv|videos?)/",
        url_lower,
    ):
        return "Instagram Video"

    if "instagram.com" in url_lower:
        path = urlsplit(url_lower).path.strip("/")

        if path and "/" not in path:
            return "Instagram Profile"

        return "Instagram Other"

    return "Other"


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

    user_re = username_pattern(username)
    mention_re = mention_pattern(username)

    username_in_title = bool(
        user_re.search(title)
    )

    mention_in_title = bool(
        mention_re.search(title)
    )

    username_in_snippet = bool(
        user_re.search(snippet)
    )

    mention_in_snippet = bool(
        mention_re.search(snippet)
    )

    username_in_url = bool(
        user_re.search(url)
    )

    combined = f"{title} {snippet} {url}"

    comment_match = keyword_exists(
        combined,
        [
            "comment",
            "comments",
            "commented",
            "commenting",
        ],
    )

    mention_match = keyword_exists(
        combined,
        [
            "mention",
            "mentions",
            "mentioned",
        ],
    )

    tag_match = keyword_exists(
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
        or keyword_exists(
            combined,
            ["reel", "reels"],
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

    if username_in_title:
        score += SCORE_WEIGHTS["username_title"]

    if mention_in_title:
        score += SCORE_WEIGHTS["at_username_title"]

    if username_in_snippet:
        score += SCORE_WEIGHTS["username_snippet"]

    if mention_in_snippet:
        score += SCORE_WEIGHTS["at_username_snippet"]

    if username_in_url:
        score += SCORE_WEIGHTS["username_url"]

    if "instagram.com" in url.lower():
        score += SCORE_WEIGHTS["instagram_domain"]

    if post_match:
        score += SCORE_WEIGHTS["instagram_post"]

    if reel_match:
        score += SCORE_WEIGHTS["instagram_reel"]

    if keyword_exists(combined, ["comment"]):
        score += SCORE_WEIGHTS["comment"]

    if keyword_exists(combined, ["comments"]):
        score += SCORE_WEIGHTS["comments"]

    if keyword_exists(combined, ["commented"]):
        score += SCORE_WEIGHTS["commented"]

    if keyword_exists(combined, ["mention"]):
        score += SCORE_WEIGHTS["mention"]

    if keyword_exists(combined, ["mentions"]):
        score += SCORE_WEIGHTS["mentions"]

    if keyword_exists(combined, ["mentioned"]):
        score += SCORE_WEIGHTS["mentioned"]

    if keyword_exists(combined, ["tag"]):
        score += SCORE_WEIGHTS["tag"]

    if keyword_exists(combined, ["tags"]):
        score += SCORE_WEIGHTS["tags"]

    if keyword_exists(combined, ["tagged"]):
        score += SCORE_WEIGHTS["tagged"]

    if query.category.lower() in {
        "comments",
        "post comments",
        "reel comments",
        "mentions",
        "post mentions",
        "reel mentions",
        "tags",
        "post tags",
        "reel tags",
        "high relevance",
    }:
        score += SCORE_WEIGHTS["query_relevance"]

    matches = {
        "username_match": (
            username_in_title
            or username_in_snippet
            or username_in_url
        ),
        "mention_match": (
            mention_in_title
            or mention_in_snippet
            or bool(mention_re.search(url))
        ),
        "comment_match": comment_match,
        "tag_match": tag_match,
        "reel_match": reel_match,
        "post_match": post_match,
    }

    return score, matches


class SearchProvider:
    name = "Base"

    def search(
        self,
        query: str,
        backend: str,
        region: str,
        safesearch: str,
        max_results: int,
        timeout: int,
    ) -> list[dict]:
        raise NotImplementedError


class DDGSSearchProvider(SearchProvider):
    name = "DDGS"

    def __init__(self, timeout: int):
        self.timeout = timeout
        self.client = DDGS(timeout=timeout)

    def search(
        self,
        query: str,
        backend: str,
        region: str,
        safesearch: str,
        max_results: int,
        timeout: int,
    ) -> list[dict]:

        results = self.client.text(
            query,
            backend=backend,
            region=region,
            safesearch=safesearch,
            max_results=max_results,
        )

        return list(results or [])


def convert_raw_result(
    raw: dict,
    search_query: SearchQuery,
    username: str,
    backend: str,
) -> SearchResult | None:
    if not isinstance(raw, dict):
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

    clean_url = normalize_url(url)

    if not clean_url:
        return None

    domain = get_domain(clean_url)

    # Instagram-only enforcement.
    if "instagram.com" not in domain:
        return None

    result_type = classify_result(
        clean_url,
        title,
        snippet,
    )

    score, matches = calculate_score(
        username=username,
        title=title,
        snippet=snippet,
        url=clean_url,
        query=search_query,
    )

    return SearchResult(
        score=score,
        result_type=result_type,
        title=title,
        url=clean_url,
        snippet=snippet,
        domain=domain,
        backend=backend,
        query=search_query.text,
        query_category=search_query.category,
        query_intent=search_query.intent,
        discovered_at=datetime.now(
            timezone.utc
        ).isoformat(),
        username_match=matches["username_match"],
        mention_match=matches["mention_match"],
        comment_match=matches["comment_match"],
        tag_match=matches["tag_match"],
        reel_match=matches["reel_match"],
        post_match=matches["post_match"],
    )


def randomized_delay(
    minimum: float,
    maximum: float,
) -> None:
    minimum = max(0.0, minimum)
    maximum = max(minimum, maximum)

    if maximum <= 0:
        return

    time.sleep(
        random.uniform(
            minimum,
            maximum,
        )
    )


def execute_query(
    provider: SearchProvider,
    query: SearchQuery,
    username: str,
    settings: dict,
) -> tuple[list[SearchResult], str | None]:

    retries = settings["retries"]
    last_error = None

    for attempt in range(retries + 1):

        if st.session_state.stop_requested:
            return [], "Search stopped by user."

        try:
            if attempt > 0:
                backoff = min(
                    8.0,
                    (2 ** attempt)
                    + random.uniform(0.2, 0.8),
                )

                time.sleep(backoff)

            raw_results = provider.search(
                query=query.text,
                backend=settings["backend"],
                region=settings["region"],
                safesearch=settings["safesearch"],
                max_results=settings["results_per_query"],
                timeout=settings["timeout"],
            )

            converted = []

            for raw in raw_results:
                result = convert_raw_result(
                    raw=raw,
                    search_query=query,
                    username=username,
                    backend=settings["backend"],
                )

                if result:
                    converted.append(result)

            return converted, None

        except RatelimitException as exc:
            last_error = f"Rate limit: {exc}"

        except TimeoutException as exc:
            last_error = f"Timeout: {exc}"

        except DDGSException as exc:
            last_error = f"DDGS error: {exc}"

        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"

        if attempt < retries:
            randomized_delay(
                settings["delay_min"],
                settings["delay_max"],
            )

    return [], last_error or "Unknown search error."


def deduplicate_results(
    results: list[SearchResult],
    username: str,
) -> list[SearchResult]:

    grouped: dict[str, list[SearchResult]] = {}

    for result in results:
        key = url_key(result.url)

        if not key:
            continue

        grouped.setdefault(key, []).append(result)

    final_results = []

    for items in grouped.values():

        primary = max(
            items,
            key=lambda item: (
                item.score,
                item.mention_match,
                item.comment_match,
                item.reel_match,
                item.post_match,
                len(item.snippet),
            ),
        )

        duplicate_count = len(items)

        if duplicate_count > 1:
            primary.score += min(
                (duplicate_count - 1)
                * SCORE_WEIGHTS["multiple_discoveries"],
                10,
            )

        primary.username_match = any(
            item.username_match for item in items
        )

        primary.mention_match = any(
            item.mention_match for item in items
        )

        primary.comment_match = any(
            item.comment_match for item in items
        )

        primary.tag_match = any(
            item.tag_match for item in items
        )

        primary.reel_match = any(
            item.reel_match for item in items
        )

        primary.post_match = any(
            item.post_match for item in items
        )

        best_query = max(
            items,
            key=lambda item: (
                item.score,
                item.mention_match,
                item.comment_match,
            ),
        )

        primary.query = best_query.query
        primary.query_category = best_query.query_category
        primary.query_intent = best_query.query_intent

        final_results.append(primary)

    final_results.sort(
        key=lambda item: (
            -item.score,
            not item.comment_match,
            not item.mention_match,
            not item.reel_match,
            not item.post_match,
            item.domain,
        )
    )

    return final_results


def results_dataframe(
    results: list[SearchResult],
) -> pd.DataFrame:

    columns = [
        "Score",
        "Type",
        "Title",
        "URL",
        "Snippet",
        "Domain",
        "Backend",
        "Query",
        "Query Category",
        "Query Intent",
        "Discovered At",
        "Username Match",
        "Mention Match",
        "Comment Match",
        "Tag Match",
        "Reel Match",
        "Post Match",
    ]

    rows = []

    for result in results:
        rows.append(
            {
                "Score": result.score,
                "Type": result.result_type,
                "Title": result.title,
                "URL": result.url,
                "Snippet": result.snippet,
                "Domain": result.domain,
                "Backend": result.backend,
                "Query": result.query,
                "Query Category": result.query_category,
                "Query Intent": result.query_intent,
                "Discovered At": result.discovered_at,
                "Username Match": result.username_match,
                "Mention Match": result.mention_match,
                "Comment Match": result.comment_match,
                "Tag Match": result.tag_match,
                "Reel Match": result.reel_match,
                "Post Match": result.post_match,
            }
        )

    return pd.DataFrame(rows, columns=columns)


def statistics_dataframe(
    results: list[SearchResult],
) -> pd.DataFrame:

    counter = Counter(
        result.result_type
        for result in results
    )

    rows = [
        {
            "Metric": "Total Unique Results",
            "Value": len(results),
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
            "Metric": "Tag Matches",
            "Value": sum(
                result.tag_match
                for result in results
            ),
        },
        {
            "Metric": "Reel Matches",
            "Value": sum(
                result.reel_match
                for result in results
            ),
        },
        {
            "Metric": "Post Matches",
            "Value": sum(
                result.post_match
                for result in results
            ),
        },
    ]

    for result_type, count in counter.items():
        rows.append(
            {
                "Metric": result_type,
                "Value": count,
            }
        )

    return pd.DataFrame(rows)


def csv_bytes(
    dataframe: pd.DataFrame,
) -> bytes:
    return dataframe.to_csv(
        index=False
    ).encode("utf-8-sig")


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
    ).encode("utf-8")


def excel_bytes(
    results_df: pd.DataFrame,
    statistics_df: pd.DataFrame,
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

        statistics_df.to_excel(
            writer,
            index=False,
            sheet_name="Statistics",
        )

        if not results_df.empty:

            for result_type in sorted(
                results_df["Type"]
                .dropna()
                .unique()
            ):
                subset = results_df[
                    results_df["Type"] == result_type
                ]

                sheet_name = re.sub(
                    r"[\[\]:*?/\\]",
                    "_",
                    str(result_type),
                )[:31]

                subset.to_excel(
                    writer,
                    index=False,
                    sheet_name=sheet_name,
                )

    return buffer.getvalue()


def render_sidebar() -> dict:

    with st.sidebar:

        st.header("Search Settings")

        backend = st.selectbox(
            "Search backend",
            SUPPORTED_BACKENDS,
            index=SUPPORTED_BACKENDS.index(
                DEFAULT_BACKEND
            ),
            help=(
                "Auto is recommended. "
                "Specific backends can be useful for testing."
            ),
        )

        results_per_query = st.slider(
            "Results per query",
            min_value=3,
            max_value=20,
            value=DEFAULT_RESULTS_PER_QUERY,
        )

        max_queries = st.slider(
            "Maximum queries",
            min_value=10,
            max_value=100,
            value=DEFAULT_MAX_QUERIES,
            step=5,
        )

        st.divider()

        st.subheader("Speed / Request Pacing")

        delay_min = st.slider(
            "Minimum delay",
            min_value=0.20,
            max_value=3.0,
            value=DEFAULT_DELAY_MIN,
            step=0.05,
        )

        delay_max = st.slider(
            "Maximum delay",
            min_value=0.20,
            max_value=5.0,
            value=DEFAULT_DELAY_MAX,
            step=0.05,
        )

        timeout = st.slider(
            "Timeout",
            min_value=5,
            max_value=30,
            value=DEFAULT_TIMEOUT,
        )

        retries = st.slider(
            "Retries",
            min_value=0,
            max_value=3,
            value=DEFAULT_RETRIES,
        )

        st.divider()

        region = st.selectbox(
            "Search region",
            [
                "us-en",
                "uk-en",
                "ca-en",
                "au-en",
                "in-en",
                "de-de",
                "fr-fr",
                "tr-tr",
                "xa-en",
            ],
            index=0,
        )

        safesearch = st.selectbox(
            "SafeSearch",
            [
                "moderate",
                "on",
                "off",
            ],
            index=0,
        )

        st.divider()

        st.caption(
            f"Instagram-only mode • v{APP_VERSION}"
        )

        st.caption(
            "No login, private-data access, CAPTCHA bypass, "
            "proxy rotation or authentication bypass."
        )

    return {
        "backend": backend,
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
            "No Instagram results discovered yet..."
        )
        return

    dataframe = results_dataframe(
        results
    )

    placeholder.dataframe(
        dataframe,
        use_container_width=True,
        hide_index=True,
        height=520,
        column_config={
            "Score": st.column_config.NumberColumn(
                "Score",
                format="%d",
            ),
            "URL": st.column_config.LinkColumn(
                "URL",
                display_text="Open",
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

    queries = generate_all_queries(
        username=username,
        max_queries=settings["max_queries"],
    )

    reset_search_state()

    st.session_state.searched_username = username
    st.session_state.total_queries = len(queries)
    st.session_state.search_running = True

    provider = DDGSSearchProvider(
        timeout=settings["timeout"]
    )

    all_results: list[SearchResult] = []
    seen_urls: set[str] = set()

    progress_placeholder = st.empty()
    status_placeholder = st.empty()
    live_stats_placeholder = st.empty()
    results_placeholder = st.empty()

    for number, query in enumerate(
        queries,
        start=1,
    ):

        if st.session_state.stop_requested:
            break

        st.session_state.completed_queries = number - 1

        progress_placeholder.progress(
            int(
                ((number - 1) / len(queries))
                * 100
            ),
            text=(
                f"Query {number} / {len(queries)}"
            ),
        )

        status_placeholder.info(
            f"🔎 **Query {number} / {len(queries)}**\n\n"
            f"**Category:** {query.category}\n\n"
            f"**Intent:** {query.intent}\n\n"
            f"`{query.text}`"
        )

        results, error = execute_query(
            provider=provider,
            query=query,
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
                    "intent": query.intent,
                    "error": error,
                }
            )

        else:

            st.session_state.successful_queries += 1

            for result in results:

                key = url_key(
                    result.url
                )

                if not key:
                    continue

                if key in seen_urls:
                    continue

                seen_urls.add(key)
                all_results.append(result)

        live_results = deduplicate_results(
            results=all_results,
            username=username,
        )

        st.session_state.results = live_results
        st.session_state.completed_queries = number

        comment_count = sum(
            result.comment_match
            for result in live_results
        )

        mention_count = sum(
            result.mention_match
            for result in live_results
        )

        reel_count = sum(
            result.reel_match
            for result in live_results
        )

        post_count = sum(
            result.post_match
            for result in live_results
        )

        live_stats_placeholder.markdown(
            f"""
**Live Results**

- Queries completed: **{number}/{len(queries)}**
- Unique Instagram results: **{len(live_results)}**
- Comment matches: **{comment_count}**
- Mention matches: **{mention_count}**
- Reels: **{reel_count}**
- Posts: **{post_count}**
"""
        )

        render_live_results(
            live_results,
            results_placeholder,
        )

        if number < len(queries):
            randomized_delay(
                settings["delay_min"],
                settings["delay_max"],
            )

    final_results = deduplicate_results(
        results=all_results,
        username=username,
    )

    st.session_state.results = final_results
    st.session_state.search_running = False
    st.session_state.search_completed = True

    if st.session_state.stop_requested:

        progress_placeholder.progress(
            int(
                (
                    st.session_state.completed_queries
                    / max(len(queries), 1)
                )
                * 100
            ),
            text="Search stopped.",
        )

        status_placeholder.warning(
            f"⏹️ Search stopped after "
            f"{st.session_state.completed_queries} / "
            f"{len(queries)} queries."
        )

    else:

        progress_placeholder.progress(
            100,
            text="Search completed.",
        )

        status_placeholder.success(
            f"✅ Search completed — "
            f"{len(final_results)} unique Instagram results."
        )


def render_statistics(
    results: list[SearchResult],
) -> None:

    counter = Counter(
        result.result_type
        for result in results
    )

    columns = st.columns(6)

    columns[0].metric(
        "Results",
        len(results),
    )

    columns[1].metric(
        "Comments",
        sum(
            result.comment_match
            for result in results
        ),
    )

    columns[2].metric(
        "Mentions",
        sum(
            result.mention_match
            for result in results
        ),
    )

    columns[3].metric(
        "Reels",
        counter.get(
            "Instagram Reel",
            0,
        ),
    )

    columns[4].metric(
        "Posts",
        counter.get(
            "Instagram Post",
            0,
        ),
    )

    columns[5].metric(
        "Profiles",
        counter.get(
            "Instagram Profile",
            0,
        ),
    )


def render_error_panel() -> None:

    errors = st.session_state.errors

    if not errors:
        return

    with st.expander(
        f"⚠️ Failed queries ({len(errors)})"
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
        st.warning(
            "No indexed Instagram results were found."
        )
        return dataframe

    st.subheader("Filters")

    columns = st.columns(5)

    with columns[0]:
        types = st.multiselect(
            "Type",
            sorted(
                dataframe["Type"].unique()
            ),
        )

    with columns[1]:
        domains = st.multiselect(
            "Domain",
            sorted(
                dataframe["Domain"].unique()
            ),
        )

    with columns[2]:

        max_score = max(
            int(
                dataframe["Score"].max()
            ),
            1,
        )

        minimum_score = st.slider(
            "Minimum score",
            min_value=0,
            max_value=max_score,
            value=0,
        )

    with columns[3]:

        query_categories = st.multiselect(
            "Query category",
            sorted(
                dataframe[
                    "Query Category"
                ].unique()
            ),
        )

    with columns[4]:

        search_text = st.text_input(
            "Search results",
            placeholder="username, comment, URL...",
        )

    filtered = dataframe.copy()

    if types:
        filtered = filtered[
            filtered["Type"].isin(types)
        ]

    if domains:
        filtered = filtered[
            filtered["Domain"].isin(domains)
        ]

    if query_categories:
        filtered = filtered[
            filtered["Query Category"].isin(
                query_categories
            )
        ]

    filtered = filtered[
        filtered["Score"] >= minimum_score
    ]

    if search_text.strip():

        needle = re.escape(
            search_text.strip()
        )

        mask = (
            filtered["Title"]
            .fillna("")
            .str.contains(
                needle,
                case=False,
                regex=True,
            )
            |
            filtered["URL"]
            .fillna("")
            .str.contains(
                needle,
                case=False,
                regex=True,
            )
            |
            filtered["Snippet"]
            .fillna("")
            .str.contains(
                needle,
                case=False,
                regex=True,
            )
            |
            filtered["Query"]
            .fillna("")
            .str.contains(
                needle,
                case=False,
                regex=True,
            )
        )

        filtered = filtered[mask]

    return filtered.sort_values(
        by=[
            "Score",
            "Comment Match",
            "Mention Match",
        ],
        ascending=[
            False,
            False,
            False,
        ],
    )


def render_exports(
    filtered: pd.DataFrame,
    all_results: list[SearchResult],
) -> None:

    st.subheader("Export")

    all_dataframe = results_dataframe(
        all_results
    )

    statistics = statistics_dataframe(
        all_results
    )

    columns = st.columns(3)

    with columns[0]:

        st.download_button(
            "⬇️ Download CSV",
            data=csv_bytes(
                filtered
            ),
            file_name=(
                "instagram_public_search.csv"
            ),
            mime="text/csv",
            use_container_width=True,
        )

    with columns[1]:

        st.download_button(
            "⬇️ Download Excel",
            data=excel_bytes(
                all_dataframe,
                statistics,
            ),
            file_name=(
                "instagram_public_search.xlsx"
            ),
            mime=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
            use_container_width=True,
        )

    with columns[2]:

        st.download_button(
            "⬇️ Download JSON",
            data=json_bytes(
                filtered
            ),
            file_name=(
                "instagram_public_search.json"
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
        "🔎 Instagram Public Comments Discovery"
    )

    st.caption(
        "Instagram-only public/indexed username discovery"
    )

    st.info(
        "Searches public search-engine-indexed Instagram results. "
        "It does not log into Instagram, access private comments, "
        "bypass CAPTCHA, bypass authentication, or access Instagram's "
        "internal/private database."
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

    normalized_username = normalize_username(
        username_input
    )

    if normalized_username:
        st.caption(
            f"Normalized username: @{normalized_username}"
        )

    controls = st.columns(2)

    with controls[0]:

        start_search = st.button(
            "🚀 START SEARCH",
            type="primary",
            use_container_width=True,
            disabled=st.session_state.search_running,
        )

    with controls[1]:

        stop_search = st.button(
            "⏹️ STOP SEARCH",
            use_container_width=True,
            disabled=not st.session_state.search_running,
        )

    if stop_search:
        request_stop()
        st.warning(
            "Stop requested. The current search request will finish, "
            "then the application will stop."
        )

    if start_search:

        username = normalize_username(
            username_input
        )

        valid, message = validate_username(
            username
        )

        if not valid:

            st.error(message)

        else:

            queries = generate_all_queries(
                username=username,
                max_queries=settings["max_queries"],
            )

            with st.expander(
                f"Generated Instagram queries ({len(queries)})",
                expanded=False,
            ):

                query_dataframe = pd.DataFrame(
                    [
                        {
                            "Category": query.category,
                            "Intent": query.intent,
                            "Query": query.text,
                        }
                        for query in queries
                    ]
                )

                st.dataframe(
                    query_dataframe,
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
            f"Results for @{st.session_state.searched_username}"
        )

        render_statistics(
            st.session_state.results
        )

        status_columns = st.columns(2)

        status_columns[0].success(
            f"Successful Queries: "
            f"{st.session_state.successful_queries}"
        )

        if st.session_state.failed_queries:

            status_columns[1].warning(
                f"Failed Queries: "
                f"{st.session_state.failed_queries}"
            )

        else:

            status_columns[1].success(
                "Failed Queries: 0"
            )

        render_error_panel()

        filtered = render_filters(
            st.session_state.results
        )

        if not filtered.empty:

            st.subheader(
                f"Results ({len(filtered)})"
            )

            st.dataframe(
                filtered,
                use_container_width=True,
                hide_index=True,
                height=650,
                column_config={
                    "Score": st.column_config.NumberColumn(
                        "Score",
                        format="%d",
                    ),
                    "URL": st.column_config.LinkColumn(
                        "URL",
                        display_text="Open",
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

            render_exports(
                filtered=filtered,
                all_results=st.session_state.results,
            )

        else:

            st.info(
                "No results match the current filters."
            )

    elif not st.session_state.search_running:

        st.divider()

        st.subheader(
            "What this tool searches"
        )

        st.write(
            "Instagram posts, Reels, indexed profile pages, "
            "mentions, tags and public search-engine snippets "
            "associated with the supplied username."
        )

        st.warning(
            "Important: search engines do not expose every Instagram "
            "comment. A comment that is not publicly indexed cannot be "
            "recovered by this application."
        )


if __name__ == "__main__":
    main()