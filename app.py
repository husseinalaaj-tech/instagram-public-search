import io
import json
import re
import time
import hashlib
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

import pandas as pd
import streamlit as st
from ddgs import DDGS


# ============================================================
# APP CONFIGURATION
# ============================================================

APP_TITLE = "Instagram Public Discovery"

DEFAULT_RESULTS_PER_QUERY = 8
DEFAULT_DELAY = 0.35
DEFAULT_MAX_QUERIES = 70
DEFAULT_RETRIES = 2

# Easy-to-edit scoring weights.
SCORE_WEIGHTS = {
    "exact_username": 10,
    "at_username": 12,
    "title_username": 6,
    "instagram_domain": 5,
    "instagram_post": 8,
    "instagram_reel": 10,
    "instagram_tv": 6,
    "comment_keyword": 4,
    "mention_keyword": 4,
    "tag_keyword": 3,
    "caption_keyword": 3,
    "profile_keyword": 2,
}

COMMENT_WORDS = (
    "comment",
    "comments",
    "commented",
    "reply",
    "replies",
)

MENTION_WORDS = (
    "mention",
    "mentioned",
    "mentions",
)

TAG_WORDS = (
    "tag",
    "tagged",
    "tags",
)

CAPTION_WORDS = (
    "caption",
    "description",
)

INSTAGRAM_DOMAIN = "instagram.com"


# ============================================================
# STREAMLIT CONFIG
# ============================================================

st.set_page_config(
    page_title=APP_TITLE,
    page_icon="📸",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# SESSION STATE
# ============================================================

def initialize_state():
    defaults = {
        "results": [],
        "failed_queries": [],
        "successful_queries": 0,
        "search_finished": False,
        "search_running": False,
        "last_username": "",
        "query_log": [],
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


initialize_state()


# ============================================================
# GENERAL HELPERS
# ============================================================

def now_utc():
    return datetime.now(timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%S UTC"
    )


def normalize_username(value):
    value = (value or "").strip()

    if value.startswith("@"):
        value = value[1:]

    value = value.strip()

    # Remove accidental Instagram URL input.
    value = re.sub(
        r"^https?://(www\.)?instagram\.com/",
        "",
        value,
        flags=re.IGNORECASE,
    )

    value = value.split("/")[0]
    value = value.split("?")[0]
    value = value.strip()

    return value


def validate_username(username):
    if not username:
        return False, "Enter an Instagram username."

    if len(username) > 30:
        return False, "Instagram usernames cannot exceed 30 characters."

    if not re.fullmatch(r"[A-Za-z0-9._]+", username):
        return False, (
            "Username contains unsupported characters."
        )

    return True, ""


def username_regex(username):
    escaped = re.escape(username)

    return re.compile(
        rf"(?<![A-Za-z0-9._])@?{escaped}(?![A-Za-z0-9._])",
        re.IGNORECASE,
    )


def text_contains_username(text, username):
    if not text:
        return False

    return bool(
        username_regex(username).search(text)
    )


def clean_url(url):
    if not url:
        return ""

    try:
        parsed = urlsplit(url)

        removable = {
            "utm_source",
            "utm_medium",
            "utm_campaign",
            "utm_term",
            "utm_content",
            "fbclid",
            "gclid",
            "ref",
        }

        query_items = [
            (key, value)
            for key, value in parse_qsl(
                parsed.query,
                keep_blank_values=True,
            )
            if key.lower() not in removable
        ]

        query = urlencode(query_items)

        cleaned = urlunsplit(
            (
                parsed.scheme.lower(),
                parsed.netloc.lower(),
                parsed.path.rstrip("/"),
                query,
                "",
            )
        )

        return cleaned

    except Exception:
        return url


def get_domain(url):
    try:
        hostname = urlsplit(url).netloc.lower()

        if hostname.startswith("www."):
            hostname = hostname[4:]

        return hostname

    except Exception:
        return ""


def is_instagram_url(url):
    domain = get_domain(url)

    return (
        domain == INSTAGRAM_DOMAIN
        or domain.endswith(".instagram.com")
    )


def result_key(result):
    url = clean_url(result.get("url", ""))

    if url:
        return hashlib.sha256(
            url.encode("utf-8")
        ).hexdigest()

    raw = (
        result.get("title", "")
        + "|"
        + result.get("snippet", "")
    )

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()


# ============================================================
# QUERY GENERATOR
# ============================================================

def build_query_groups(username):
    u = username
    q = f'"{u}"'
    aq = f'"@{u}"'

    groups = {
        "Profile": [
            f'site:instagram.com "{u}"',
            f'site:instagram.com "{u}" profile',
            f'site:instagram.com "@{u}"',
            f'site:instagram.com/users "{u}"',
        ],

        "Posts": [
            f'site:instagram.com/p/ "{u}"',
            f'site:instagram.com/p/ "@{u}"',
            f'site:instagram.com/p/ "{u}" Instagram',
            f'site:instagram.com/p/ {q}',
            f'site:instagram.com/p/ {aq}',
        ],

        "Reels": [
            f'site:instagram.com/reel/ "{u}"',
            f'site:instagram.com/reel/ "@{u}"',
            f'site:instagram.com/reels/ "{u}"',
            f'site:instagram.com/reel/ "{u}" Instagram',
            f'site:instagram.com/reels/ "@{u}" Instagram',
        ],

        "Videos": [
            f'site:instagram.com/tv/ "{u}"',
            f'site:instagram.com/tv/ "@{u}"',
            f'site:instagram.com/videos/ "{u}"',
        ],

        "Comments": [
            f'site:instagram.com "{u}" comment',
            f'site:instagram.com "@{u}" comment',
            f'site:instagram.com "{u}" comments',
            f'site:instagram.com "@{u}" comments',
            f'site:instagram.com "{u}" commented',
            f'site:instagram.com "@{u}" reply',
            f'site:instagram.com "{u}" replies',
        ],

        "Mentions": [
            f'site:instagram.com "{u}" mention',
            f'site:instagram.com "@{u}" mention',
            f'site:instagram.com "{u}" mentioned',
            f'site:instagram.com "@{u}" mentioned',
            f'site:instagram.com "{u}" mentions',
        ],

        "Tags": [
            f'site:instagram.com "{u}" tag',
            f'site:instagram.com "@{u}" tag',
            f'site:instagram.com "{u}" tagged',
            f'site:instagram.com "@{u}" tagged',
            f'site:instagram.com "{u}" tags',
        ],

        "Captions": [
            f'site:instagram.com "{u}" caption',
            f'site:instagram.com "@{u}" caption',
            f'site:instagram.com/p/ "{u}" caption',
            f'site:instagram.com/reel/ "{u}" caption',
        ],

        "Indexed Content": [
            f'site:instagram.com "{u}" Instagram',
            f'site:instagram.com "@{u}" Instagram',
            f'site:instagram.com "{u}" public',
            f'site:instagram.com "@{u}" public',
            f'site:instagram.com "{u}" post',
            f'site:instagram.com "@{u}" post',
        ],
    }

    return groups


def generate_queries(username, enabled_groups, max_queries):
    groups = build_query_groups(username)

    queries = []

    for group_name, group_queries in groups.items():

        if group_name not in enabled_groups:
            continue

        for query in group_queries:

            query = query.strip()

            if query and query not in queries:
                queries.append(
                    {
                        "query": query,
                        "category": group_name,
                    }
                )

    return queries[:max_queries]


# ============================================================
# CLASSIFICATION
# ============================================================

def classify_result(url, title, snippet):
    combined = (
        f"{title} {snippet} {url}"
    ).lower()

    path = urlsplit(url).path.lower()

    if "/reel/" in path or "/reels/" in path:
        return "Reel"

    if "/p/" in path:
        return "Post"

    if "/tv/" in path:
        return "Video"

    if (
        any(word in combined for word in COMMENT_WORDS)
        and is_instagram_url(url)
    ):
        return "Comment-related"

    if (
        any(word in combined for word in MENTION_WORDS)
        and is_instagram_url(url)
    ):
        return "Mention"

    if (
        any(word in combined for word in TAG_WORDS)
        and is_instagram_url(url)
    ):
        return "Tag"

    if is_instagram_url(url):
        return "Instagram"

    return "Other"


# ============================================================
# SCORING
# ============================================================

def calculate_score(
    username,
    title,
    snippet,
    url,
    category,
):
    score = 0

    title = title or ""
    snippet = snippet or ""
    url = url or ""

    title_lower = title.lower()
    snippet_lower = snippet.lower()
    url_lower = url.lower()

    exact_pattern = username_regex(username)

    if exact_pattern.search(snippet):
        score += SCORE_WEIGHTS["exact_username"]

    if re.search(
        rf"@{re.escape(username)}",
        snippet,
        re.IGNORECASE,
    ):
        score += SCORE_WEIGHTS["at_username"]

    if exact_pattern.search(title):
        score += SCORE_WEIGHTS["title_username"]

    if is_instagram_url(url):
        score += SCORE_WEIGHTS["instagram_domain"]

    if "/reel/" in url_lower or "/reels/" in url_lower:
        score += SCORE_WEIGHTS["instagram_reel"]

    if "/p/" in url_lower:
        score += SCORE_WEIGHTS["instagram_post"]

    if "/tv/" in url_lower:
        score += SCORE_WEIGHTS["instagram_tv"]

    combined = (
        f"{title_lower} {snippet_lower}"
    )

    if any(word in combined for word in COMMENT_WORDS):
        score += SCORE_WEIGHTS["comment_keyword"]

    if any(word in combined for word in MENTION_WORDS):
        score += SCORE_WEIGHTS["mention_keyword"]

    if any(word in combined for word in TAG_WORDS):
        score += SCORE_WEIGHTS["tag_keyword"]

    if any(word in combined for word in CAPTION_WORDS):
        score += SCORE_WEIGHTS["caption_keyword"]

    if category == "Profile":
        score += SCORE_WEIGHTS["profile_keyword"]

    return score


# ============================================================
# SEARCH PROVIDER
# ============================================================

class SearchProvider:

    def __init__(
        self,
        max_results=DEFAULT_RESULTS_PER_QUERY,
        retries=DEFAULT_RETRIES,
    ):
        self.max_results = max_results
        self.retries = retries

    def search(self, query):
        last_error = None

        for attempt in range(
            self.retries + 1
        ):

            try:
                with DDGS() as ddgs:

                    rows = list(
                        ddgs.text(
                            query,
                            max_results=self.max_results,
                        )
                    )

                return rows

            except Exception as exc:

                last_error = exc

                if attempt < self.retries:
                    time.sleep(
                        min(
                            2 ** attempt,
                            5,
                        )
                    )

        raise RuntimeError(
            str(last_error)
            if last_error
            else "Unknown search error."
        )


# ============================================================
# RESULT NORMALIZATION
# ============================================================

def normalize_search_result(
    raw,
    query,
    query_category,
    username,
):
    title = str(
        raw.get("title", "")
        or ""
    ).strip()

    url = str(
        raw.get("href", "")
        or raw.get("url", "")
        or ""
    ).strip()

    snippet = str(
        raw.get("body", "")
        or raw.get("snippet", "")
        or ""
    ).strip()

    if not url:
        return None

    url = clean_url(url)

    category = classify_result(
        url,
        title,
        snippet,
    )

    score = calculate_score(
        username=username,
        title=title,
        snippet=snippet,
        url=url,
        category=category,
    )

    combined_text = (
        f"{title} {snippet}"
    )

    username_match = text_contains_username(
        combined_text,
        username,
    )

    mention_match = bool(
        re.search(
            rf"@{re.escape(username)}",
            combined_text,
            re.IGNORECASE,
        )
    )

    comment_match = any(
        word in combined_text.lower()
        for word in COMMENT_WORDS
    )

    reel_match = (
        "/reel/" in url.lower()
        or "/reels/" in url.lower()
    )

    post_match = (
        "/p/" in url.lower()
    )

    return {
        "score": int(score),
        "category": category,
        "title": title,
        "url": url,
        "snippet": snippet,
        "domain": get_domain(url),
        "query": query,
        "query_category": query_category,
        "search_backend": "DuckDuckGo",
        "discovered_at": now_utc(),
        "username_match": username_match,
        "mention_match": mention_match,
        "comment_keyword_match": comment_match,
        "reel_match": reel_match,
        "post_match": post_match,
    }


# ============================================================
# DEDUPLICATION
# ============================================================

def merge_result(existing, new):
    if new["score"] > existing["score"]:
        existing["score"] = new["score"]

    if (
        len(new.get("snippet", ""))
        > len(existing.get("snippet", ""))
    ):
        existing["snippet"] = new["snippet"]

    existing["username_match"] = (
        existing["username_match"]
        or new["username_match"]
    )

    existing["mention_match"] = (
        existing["mention_match"]
        or new["mention_match"]
    )

    existing["comment_keyword_match"] = (
        existing["comment_keyword_match"]
        or new["comment_keyword_match"]
    )

    existing["reel_match"] = (
        existing["reel_match"]
        or new["reel_match"]
    )

    existing["post_match"] = (
        existing["post_match"]
        or new["post_match"]
    )

    return existing


def deduplicate_results(results):
    indexed = {}

    for result in results:

        key = result_key(result)

        if key in indexed:
            indexed[key] = merge_result(
                indexed[key],
                result,
            )
        else:
            indexed[key] = result

    output = list(indexed.values())

    output.sort(
        key=lambda item: (
            item.get("score", 0),
            item.get("discovered_at", ""),
        ),
        reverse=True,
    )

    return output


# ============================================================
# DATAFRAME
# ============================================================

def results_dataframe(results):
    columns = [
        "score",
        "category",
        "title",
        "url",
        "snippet",
        "domain",
        "query_category",
        "search_backend",
        "query",
        "discovered_at",
        "username_match",
        "mention_match",
        "comment_keyword_match",
        "reel_match",
        "post_match",
    ]

    if not results:
        return pd.DataFrame(
            columns=columns
        )

    return pd.DataFrame(
        results,
        columns=columns,
    )


# ============================================================
# EXPORT
# ============================================================

def make_excel(results):
    output = io.BytesIO()

    df = results_dataframe(results)

    statistics = pd.DataFrame(
        [
            {
                "Metric": "Total Results",
                "Value": len(results),
            },
            {
                "Metric": "Instagram Results",
                "Value": sum(
                    r["category"] == "Instagram"
                    for r in results
                ),
            },
            {
                "Metric": "Posts",
                "Value": sum(
                    r["category"] == "Post"
                    for r in results
                ),
            },
            {
                "Metric": "Reels",
                "Value": sum(
                    r["category"] == "Reel"
                    for r in results
                ),
            },
            {
                "Metric": "Comment-related",
                "Value": sum(
                    r["category"] == "Comment-related"
                    for r in results
                ),
            },
            {
                "Metric": "Mentions",
                "Value": sum(
                    r["category"] == "Mention"
                    for r in results
                ),
            },
        ]
    )

    with pd.ExcelWriter(
        output,
        engine="openpyxl",
    ) as writer:

        df.to_excel(
            writer,
            sheet_name="Results",
            index=False,
        )

        statistics.to_excel(
            writer,
            sheet_name="Statistics",
            index=False,
        )

    output.seek(0)

    return output.getvalue()


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.header("⚙️ Search Settings")

    results_per_query = st.slider(
        "Results per query",
        min_value=3,
        max_value=30,
        value=DEFAULT_RESULTS_PER_QUERY,
    )

    delay = st.slider(
        "Delay between queries",
        min_value=0.1,
        max_value=3.0,
        value=DEFAULT_DELAY,
        step=0.05,
    )

    max_queries = st.slider(
        "Maximum queries",
        min_value=5,
        max_value=100,
        value=DEFAULT_MAX_QUERIES,
    )

    retries = st.slider(
        "Retries on failure",
        min_value=0,
        max_value=3,
        value=DEFAULT_RETRIES,
    )

    st.divider()

    st.subheader("Query Categories")

    enabled_groups = []

    for group in [
        "Profile",
        "Posts",
        "Reels",
        "Videos",
        "Comments",
        "Mentions",
        "Tags",
        "Captions",
        "Indexed Content",
    ]:

        enabled = st.checkbox(
            group,
            value=True,
            key=f"group_{group}",
        )

        if enabled:
            enabled_groups.append(group)

    st.divider()

    st.caption(
        "This application searches public, "
        "search-engine-indexed information only."
    )

    st.caption(
        "It does not log into Instagram, bypass "
        "CAPTCHA, access private content, or "
        "retrieve Instagram's internal database."
    )


# ============================================================
# HEADER
# ============================================================

st.title("📸 Instagram Public Discovery")

st.write(
    "Search public web-indexed pages related to an "
    "Instagram username."
)


# ============================================================
# INPUT
# ============================================================

username_input = st.text_input(
    "Instagram Username",
    placeholder="@example",
)

username = normalize_username(
    username_input
)

if username:
    st.caption(
        f"Normalized username: `@{username}`"
    )


# ============================================================
# SEARCH BUTTON
# ============================================================

start_search = st.button(
    "🚀 START SEARCH",
    type="primary",
    use_container_width=True,
)


# ============================================================
# SEARCH ENGINE
# ============================================================

if start_search:

    valid, error_message = validate_username(
        username
    )

    if not valid:

        st.error(error_message)

    elif not enabled_groups:

        st.error(
            "Enable at least one query category."
        )

    else:

        queries = generate_queries(
            username,
            enabled_groups,
            max_queries,
        )

        st.session_state.results = []
        st.session_state.failed_queries = []
        st.session_state.successful_queries = 0
        st.session_state.query_log = []
        st.session_state.search_finished = False
        st.session_state.search_running = True
        st.session_state.last_username = username

        provider = SearchProvider(
            max_results=results_per_query,
            retries=retries,
        )

        progress = st.progress(0)
        current_query_box = st.empty()
        result_count_box = st.empty()
        live_results_box = st.empty()
        status_box = st.empty()

        accumulated_results = []

        total_queries = len(queries)

        for index, query_info in enumerate(
            queries,
            start=1,
        ):

            query = query_info["query"]
            query_category = query_info["category"]

            current_query_box.markdown(
                f"**Query {index} / {total_queries}**  \n"
                f"`{query}`"
            )

            progress.progress(
                index / total_queries
            )

            try:

                raw_results = provider.search(
                    query
                )

                for raw in raw_results:

                    normalized = normalize_search_result(
                        raw=raw,
                        query=query,
                        query_category=query_category,
                        username=username,
                    )

                    if normalized:
                        accumulated_results.append(
                            normalized
                        )

                st.session_state.successful_queries += 1

                st.session_state.query_log.append(
                    {
                        "query": query,
                        "category": query_category,
                        "status": "success",
                        "time": now_utc(),
                    }
                )

                accumulated_results = (
                    deduplicate_results(
                        accumulated_results
                    )
                )

                # Live result update.
                result_count_box.metric(
                    "Results discovered",
                    len(accumulated_results),
                )

                # Show results immediately instead of waiting
                # for the complete search.
                if accumulated_results:

                    live_df = results_dataframe(
                        accumulated_results
                    )

                    live_results_box.dataframe(
                        live_df[
                            [
                                "score",
                                "category",
                                "title",
                                "url",
                                "snippet",
                                "domain",
                            ]
                        ],
                        use_container_width=True,
                        hide_index=True,
                        column_config={
                            "url": st.column_config.LinkColumn(
                                "URL",
                                display_text="Open",
                            )
                        },
                    )

            except Exception as exc:

                error = str(exc)

                st.session_state.failed_queries.append(
                    {
                        "query": query,
                        "category": query_category,
                        "error": error,
                        "time": now_utc(),
                    }
                )

                st.session_state.query_log.append(
                    {
                        "query": query,
                        "category": query_category,
                        "status": "failed",
                        "error": error,
                        "time": now_utc(),
                    }
                )

            if delay > 0:
                time.sleep(delay)

        st.session_state.results = (
            deduplicate_results(
                accumulated_results
            )
        )

        st.session_state.search_finished = True
        st.session_state.search_running = False

        status_box.success(
            "Search completed."
        )

        st.rerun()


# ============================================================
# RESULTS
# ============================================================

results = st.session_state.results

if results:

    st.divider()

    st.header("📊 Results")

    total_results = len(results)

    instagram_count = sum(
        is_instagram_url(
            r["url"]
        )
        for r in results
    )

    posts_count = sum(
        r["category"] == "Post"
        for r in results
    )

    reels_count = sum(
        r["category"] == "Reel"
        for r in results
    )

    comments_count = sum(
        r["category"] == "Comment-related"
        for r in results
    )

    mentions_count = sum(
        r["category"] == "Mention"
        for r in results
    )

    c1, c2, c3, c4, c5, c6 = st.columns(6)

    c1.metric(
        "Total",
        total_results,
    )

    c2.metric(
        "Instagram",
        instagram_count,
    )

    c3.metric(
        "Posts",
        posts_count,
    )

    c4.metric(
        "Reels",
        reels_count,
    )

    c5.metric(
        "Comments",
        comments_count,
    )

    c6.metric(
        "Mentions",
        mentions_count,
    )

    # --------------------------------------------------------
    # Filters
    # --------------------------------------------------------

    st.subheader("🔎 Filters")

    categories = sorted(
        set(
            r["category"]
            for r in results
        )
    )

    domains = sorted(
        set(
            r["domain"]
            for r in results
        )
    )

    backends = sorted(
        set(
            r["search_backend"]
            for r in results
        )
    )

    f1, f2, f3, f4 = st.columns(4)

    with f1:

        selected_categories = st.multiselect(
            "Category",
            categories,
            default=categories,
        )

    with f2:

        selected_domains = st.multiselect(
            "Domain",
            domains,
            default=domains,
        )

    with f3:

        selected_backends = st.multiselect(
            "Backend",
            backends,
            default=backends,
        )

    with f4:

        min_score = st.number_input(
            "Minimum score",
            min_value=0,
            max_value=100,
            value=0,
        )

    search_inside = st.text_input(
        "Search inside results",
        placeholder="keyword, title, snippet...",
    )

    filtered = []

    for result in results:

        if (
            result["category"]
            not in selected_categories
        ):
            continue

        if (
            result["domain"]
            not in selected_domains
        ):
            continue

        if (
            result["search_backend"]
            not in selected_backends
        ):
            continue

        if result["score"] < min_score:
            continue

        if search_inside:

            haystack = (
                result["title"]
                + " "
                + result["snippet"]
                + " "
                + result["url"]
            ).lower()

            if search_inside.lower() not in haystack:
                continue

        filtered.append(result)

    filtered.sort(
        key=lambda r: r["score"],
        reverse=True,
    )

    st.caption(
        f"Showing {len(filtered)} of {len(results)} results"
    )

    # --------------------------------------------------------
    # Results table
    # --------------------------------------------------------

    display_df = results_dataframe(
        filtered
    )

    if not display_df.empty:

        st.dataframe(
            display_df[
                [
                    "score",
                    "category",
                    "title",
                    "url",
                    "snippet",
                    "domain",
                    "query_category",
                    "search_backend",
                    "query",
                    "discovered_at",
                ]
            ],
            use_container_width=True,
            hide_index=True,
            column_config={
                "score": st.column_config.NumberColumn(
                    "Score",
                    format="%d",
                ),
                "url": st.column_config.LinkColumn(
                    "URL",
                    display_text="Open",
                ),
            },
        )

    # --------------------------------------------------------
    # Detailed cards
    # --------------------------------------------------------

    with st.expander(
        "📄 Detailed Results",
        expanded=False,
    ):

        for number, result in enumerate(
            filtered,
            start=1,
        ):

            st.markdown(
                f"### #{number} — "
                f"Score {result['score']} — "
                f"{result['category']}"
            )

            st.write(
                result["title"]
                or "Untitled"
            )

            st.link_button(
                "Open result",
                result["url"],
            )

            if result["snippet"]:
                st.caption(
                    result["snippet"]
                )

            st.caption(
                f"Domain: {result['domain']} | "
                f"Query: {result['query']}"
            )

            st.divider()

    # --------------------------------------------------------
    # Export
    # --------------------------------------------------------

    st.subheader("📦 Export")

    export_df = results_dataframe(
        filtered
    )

    csv_data = export_df.to_csv(
        index=False
    ).encode("utf-8")

    json_data = json.dumps(
        filtered,
        ensure_ascii=False,
        indent=2,
    ).encode("utf-8")

    excel_data = make_excel(
        filtered
    )

    e1, e2, e3 = st.columns(3)

    with e1:

        st.download_button(
            "⬇️ Download CSV",
            data=csv_data,
            file_name=(
                f"{username}_instagram_results.csv"
            ),
            mime="text/csv",
            use_container_width=True,
        )

    with e2:

        st.download_button(
            "⬇️ Download Excel",
            data=excel_data,
            file_name=(
                f"{username}_instagram_results.xlsx"
            ),
            mime=(
                "application/vnd.openxmlformats-"
                "officedocument.spreadsheetml.sheet"
            ),
            use_container_width=True,
        )

    with e3:

        st.download_button(
            "⬇️ Download JSON",
            data=json_data,
            file_name=(
                f"{username}_instagram_results.json"
            ),
            mime="application/json",
            use_container_width=True,
        )


# ============================================================
# SEARCH DIAGNOSTICS
# ============================================================

if st.session_state.search_finished:

    st.divider()

    st.header("🧪 Search Diagnostics")

    q1, q2, q3 = st.columns(3)

    q1.metric(
        "Successful Queries",
        st.session_state.successful_queries,
    )

    q2.metric(
        "Failed Queries",
        len(
            st.session_state.failed_queries
        ),
    )

    q3.metric(
        "Unique Results",
        len(
            st.session_state.results
        ),
    )

    if st.session_state.failed_queries:

        with st.expander(
            "⚠️ Failed Queries"
        ):

            st.dataframe(
                pd.DataFrame(
                    st.session_state.failed_queries
                ),
                use_container_width=True,
                hide_index=True,
            )


# ============================================================
# EMPTY STATE
# ============================================================

if not results and not st.session_state.search_running:

    st.info(
        "Enter an Instagram username and press "
        "START SEARCH."
    )

    st.markdown(
        """
The application searches public search-engine results for:

- Instagram profiles
- Public indexed posts
- Public indexed Reels
- Public indexed videos
- Mention-related pages
- Tag-related pages
- Comment-related snippets
- Caption-related snippets

Results appear progressively while the search is running.
        """
    )