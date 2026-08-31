import io
import json
import random
import re
import time
from datetime import datetime, timezone
from urllib.parse import urlparse
import pandas as pd
import streamlit as st
from ddgs import DDGS
# ============================================================
# إعداد الصفحة
# ============================================================
st.set_page_config(
    page_title="Public Username Search",
    page_icon="🔎",
    layout="wide",
)
# ============================================================
# CSS
# ============================================================
st.markdown(
    """
    <style>
        .main-title {
            font-size: 38px;
            font-weight: 700;
            margin-bottom: 5px;
        }
        .subtitle {
            color: #777;
            margin-bottom: 25px;
        }
    </style>
    """,
    unsafe_allow_html=True,
)
# ============================================================
# الإعدادات
# ============================================================
DEFAULT_MAX_RESULTS = 10
BACKENDS = [
    "auto",
    "duckduckgo",
    "bing",
    "brave",
    "google",
    "mojeek",
    "yahoo",
]
# ============================================================
# تنظيف Username
# ============================================================
def normalize_username(value: str) -> str:
    """
    تنظيف Username وإزالة @ والمسافات.
    """
    value = value.strip()
    if value.startswith("@"):
        value = value[1:]
    value = re.sub(
        r"[^a-zA-Z0-9._]",
        "",
        value,
    )
    return value.lower()
# ============================================================
# التحقق من Username
# ============================================================
def valid_username(username: str) -> bool:
    """
    تحقق من صيغة Instagram Username.
    """
    if not username:
        return False
    if len(username) > 30:
        return False
    return bool(
        re.fullmatch(
            r"[a-zA-Z0-9._]+",
            username,
        )
    )
# ============================================================
# توليد الاستعلامات
# ============================================================
def generate_queries(username: str):
    """
    إنشاء مجموعة استعلامات بحث عامة.
    """
    queries = []
    def add(category, query):
        queries.append(
            {
                "category": category,
                "query": query,
            }
        )
    # --------------------------------------------------------
    # Instagram
    # --------------------------------------------------------
    instagram = [
        f'site:instagram.com "{username}"',
        f'site:instagram.com "@{username}"',
        f'site:instagram.com/p/ "{username}"',
        f'site:instagram.com/reel/ "{username}"',
        f'site:instagram.com/reels/ "{username}"',
        f'site:instagram.com/tv/ "{username}"',
        f'site:instagram.com "{username}" comment',
        f'site:instagram.com "{username}" comments',
        f'site:instagram.com "{username}" mention',
        f'site:instagram.com "{username}" mentioned',
        f'site:instagram.com "@{username}" comment',
        f'site:instagram.com "@{username}" mention',
        f'site:instagram.com "@{username}" tagged',
        f'site:instagram.com "{username}" reel',
        f'site:instagram.com "{username}" post',
    ]
    for query in instagram:
        add("Instagram", query)
    # --------------------------------------------------------
    # Threads
    # --------------------------------------------------------
    threads = [
        f'site:threads.net "{username}"',
        f'site:threads.net "@{username}"',
        f'site:threads.net "{username}" Instagram',
        f'site:threads.net "{username}" mention',
        f'site:threads.net "{username}" mentioned',
        f'site:threads.net "@{username}" comment',
        f'site:threads.net "@{username}" tagged',
    ]
    for query in threads:
        add("Threads", query)
    # --------------------------------------------------------
    # Reddit
    # --------------------------------------------------------
    reddit = [
        f'site:reddit.com "{username}" Instagram',
        f'site:reddit.com "@{username}"',
        f'site:reddit.com "{username}" comment',
        f'site:reddit.com "{username}" mention',
        f'site:reddit.com "{username}" reel',
        f'site:reddit.com "{username}" post',
    ]
    for query in reddit:
        add("Reddit", query)
    # --------------------------------------------------------
    # Facebook
    # --------------------------------------------------------
    facebook = [
        f'site:facebook.com "{username}" Instagram',
        f'site:facebook.com "@{username}"',
        f'site:facebook.com "{username}" comment',
        f'site:facebook.com "{username}" mention',
        f'site:facebook.com "{username}" tagged',
    ]
    for query in facebook:
        add("Facebook", query)
    # --------------------------------------------------------
    # YouTube
    # --------------------------------------------------------
    youtube = [
        f'site:youtube.com "{username}" Instagram',
        f'site:youtube.com "@{username}"',
        f'site:youtube.com "{username}" comment',
        f'site:youtube.com "{username}" mention',
        f'site:youtube.com "{username}" reel',
    ]
    for query in youtube:
        add("YouTube", query)
    # --------------------------------------------------------
    # TikTok
    # --------------------------------------------------------
    tiktok = [
        f'site:tiktok.com "{username}" Instagram',
        f'site:tiktok.com "@{username}"',
        f'site:tiktok.com "{username}" mention',
        f'site:tiktok.com "{username}" comment',
    ]
    for query in tiktok:
        add("TikTok", query)
    # --------------------------------------------------------
    # البحث العام
    # --------------------------------------------------------
    general = [
        f'"{username}" Instagram',
        f'"@{username}" Instagram',
        f'"{username}" Instagram reel',
        f'"{username}" Instagram post',
        f'"{username}" Instagram comment',
        f'"{username}" Instagram comments',
        f'"{username}" Instagram mention',
        f'"@{username}" comment',
        f'"@{username}" mention',
        f'"{username}" social media',
        f'"{username}" profile',
        f'"{username}" creator',
        f'"{username}" influencer',
    ]
    for query in general:
        add("General", query)
    # --------------------------------------------------------
    # الأرشيف والنسخ المؤرشفة
    # --------------------------------------------------------
    archive = [
        f'"{username}" Instagram archive',
        f'"{username}" Instagram archived',
        f'"{username}" Instagram mirror',
        f'"@{username}" archive',
        f'"@{username}" archived',
        f'"{username}" cached Instagram',
    ]
    for query in archive:
        add("Archive", query)
    # --------------------------------------------------------
    # إزالة الاستعلامات المكررة
    # --------------------------------------------------------
    unique = []
    seen = set()
    for item in queries:
        query = item["query"]
        if query not in seen:
            seen.add(query)
            unique.append(item)
    return unique
# ============================================================
# تصنيف الرابط
# ============================================================
def classify_url(url: str) -> str:
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        path = parsed.path.lower()
        if "instagram.com" in domain:
            if "/reel/" in path:
                return "Instagram Reel"
            if "/reels/" in path:
                return "Instagram Reel"
            if "/p/" in path:
                return "Instagram Post"
            if "/tv/" in path:
                return "Instagram TV"
            if "/stories/" in path:
                return "Instagram Story"
            return "Instagram"
        if "threads.net" in domain:
            return "Threads"
        if "reddit.com" in domain:
            return "Reddit"
        if "facebook.com" in domain:
            return "Facebook"
        if "youtube.com" in domain:
            return "YouTube"
        if "youtu.be" in domain:
            return "YouTube"
        if "tiktok.com" in domain:
            return "TikTok"
        return "Other"
    except Exception:
        return "Unknown"
# ============================================================
# حساب أهمية النتيجة
# ============================================================
def calculate_score(row, username: str) -> int:
    score = 0
    text = " ".join(
        [
            str(row.get("title", "")),
            str(row.get("snippet", "")),
            str(row.get("url", "")),
        ]
    ).lower()
    username = username.lower()
    if f"@{username}" in text:
        score += 10
    if username in text:
        score += 5
    category = str(
        row.get("category", "")
    )
    if category == "Instagram Reel":
        score += 8
    elif category == "Instagram Post":
        score += 7
    elif category == "Instagram":
        score += 5
    elif category == "Threads":
        score += 5
    keywords = [
        "comment",
        "comments",
        "mention",
        "mentioned",
        "tag",
        "tagged",
        "instagram",
        "reel",
        "post",
    ]
    for keyword in keywords:
        if keyword in text:
            score += 1
    return score
# ============================================================
# البحث باستخدام DDGS
# ============================================================
def perform_search(
    query: str,
    backend: str,
    max_results: int,
):
    """
    تنفيذ بحث واحد.
    لا يوجد هنا أي تجاوز لـ CAPTCHA
    أو أنظمة الحماية.
    """
    ddgs = DDGS(
        timeout=15
    )
    results = ddgs.text(
        query=query,
        region="wt-wt",
        safesearch="moderate",
        timelimit=None,
        max_results=max_results,
        backend=backend,
    )
    return results
# ============================================================
# تنفيذ البحث الكامل
# ============================================================
def run_search(
    username: str,
    backend: str,
    max_results: int,
    min_delay: float,
    max_delay: float,
):
    queries = generate_queries(
        username
    )
    collected = []
    progress = st.progress(
        0,
        text="بدء البحث...",
    )
    status = st.empty()
    errors = []
    total = len(queries)
    for index, item in enumerate(
        queries,
        start=1,
    ):
        query = item["query"]
        category = item["category"]
        status.info(
            f"🔎 {index}/{total} — {query}"
        )
        try:
            raw_results = perform_search(
                query=query,
                backend=backend,
                max_results=max_results,
            )
            for result in raw_results:
                url = str(
                    result.get(
                        "href",
                        "",
                    )
                ).strip()
                if not url:
                    continue
                title = str(
                    result.get(
                        "title",
                        "",
                    )
                ).strip()
                snippet = str(
                    result.get(
                        "body",
                        "",
                    )
                ).strip()
                parsed = urlparse(
                    url
                )
                domain = parsed.netloc.lower()
                detected_category = classify_url(
                    url
                )
                collected.append(
                    {
                        "username": username,
                        "category": (
                            detected_category
                            if detected_category != "Other"
                            else category
                        ),
                        "title": title,
                        "url": url,
                        "snippet": snippet,
                        "domain": domain,
                        "query": query,
                        "backend": backend,
                        "discovered_at": datetime.now(
                            timezone.utc
                        ).isoformat(),
                    }
                )
        except Exception as exc:
            errors.append(
                {
                    "query": query,
                    "error": str(exc),
                }
            )
        progress.progress(
            index / total,
            text=f"تم تنفيذ {index} من {total}",
        )
        # ----------------------------------------------------
        # تأخير محترم بين الطلبات
        # ----------------------------------------------------
        if index < total:
            delay = random.uniform(
                min_delay,
                max_delay,
            )
            time.sleep(
                delay
            )
    status.success(
        "✅ انتهى البحث."
    )
    progress.empty()
    # --------------------------------------------------------
    # إزالة التكرار
    # --------------------------------------------------------
    unique = []
    seen_urls: Set[str] = set()
    for row in collected:
        clean_url = row["url"].split(
            "#",
            1
        )[0]
        if clean_url in seen_urls:
            continue
        seen_urls.add(
            clean_url
        )
        unique.append(
            row
        )
    # --------------------------------------------------------
    # DataFrame
    # --------------------------------------------------------
    df = pd.DataFrame(
        unique
    )
    if not df.empty:
        df["score"] = df.apply(
            lambda row: calculate_score(
                row,
                username,
            ),
            axis=1,
        )
        df = df.sort_values(
            by="score",
            ascending=False,
        )
        df = df.reset_index(
            drop=True
        )
    return df, errors
# ============================================================
# تحويل DataFrame إلى Excel
# ============================================================
def dataframe_to_excel(df: pd.DataFrame):
    output = io.BytesIO()
    with pd.ExcelWriter(
        output,
        engine="openpyxl",
    ) as writer:
        df.to_excel(
            writer,
            index=False,
            sheet_name="Results",
        )
        if not df.empty:
            statistics = (
                df["category"]
                .value_counts()
                .reset_index()
            )
            statistics.columns = [
                "category",
                "count",
            ]
            statistics.to_excel(
                writer,
                index=False,
                sheet_name="Statistics",
            )
    output.seek(0)
    return output.getvalue()
# ============================================================
# الواجهة الرئيسية
# ============================================================
st.markdown(
    '<div class="main-title">🔎 Public Username Searcher</div>',
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="subtitle">'
    "البحث عن الإشارات العامة المرتبطة باسم مستخدم عبر محركات البحث."
    "</div>",
    unsafe_allow_html=True,
)
# ============================================================
# Sidebar
# ============================================================
with st.sidebar:
    st.header("⚙️ الإعدادات")
    backend = st.selectbox(
        "محرك البحث",
        BACKENDS,
        index=0,
        help=(
            "auto يختار backend تلقائياً. "
            "يمكن تجربة backend آخر إذا فشل الأول."
        ),
    )
    max_results = st.slider(
        "نتائج كل استعلام",
        min_value=5,
        max_value=50,
        value=DEFAULT_MAX_RESULTS,
        step=5,
    )
    min_delay = st.slider(
        "أقل تأخير",
        min_value=1.0,
        max_value=10.0,
        value=2.5,
        step=0.5,
    )
    max_delay = st.slider(
        "أعلى تأخير",
        min_value=2.0,
        max_value=15.0,
        value=5.0,
        step=0.5,
    )
    if max_delay < min_delay:
        st.error(
            "أعلى تأخير يجب أن يكون أكبر من أو يساوي أقل تأخير."
        )
    st.divider()
    st.info(
        "هذه الأداة تبحث في المعلومات العامة المفهرسة "
        "ولا تسجل الدخول إلى الحسابات ولا تتجاوز CAPTCHA."
    )
# ============================================================
# إدخال Username
# ============================================================
username_input = st.text_input(
    "Instagram Username",
    placeholder="مثال: rrenguk",
    help="اكتب Username بدون الحاجة إلى @.",
)
# ============================================================
# زر البحث
# ============================================================
start = st.button(
    "🚀 بدء البحث",
    type="primary",
    use_container_width=True,
)
# ============================================================
# تشغيل البحث
# ============================================================
if start:
    username = normalize_username(
        username_input
    )
    if not valid_username(
        username
    ):
        st.error(
            "❌ Username غير صالح."
        )
        st.stop()
    if max_delay < min_delay:
        st.error(
            "❌ إعدادات التأخير غير صحيحة."
        )
        st.stop()
    st.write(
        f"### الهدف: `@{username}`"
    )
    st.caption(
        f"سيتم إنشاء {len(generate_queries(username))} استعلامات بحث."
    )
    with st.spinner(
        "جاري البحث..."
    ):
        df, errors = run_search(
            username=username,
            backend=backend,
            max_results=max_results,
            min_delay=min_delay,
            max_delay=max_delay,
        )
    st.session_state[
        "results"
    ] = df
    st.session_state[
        "errors"
    ] = errors
    st.session_state[
        "username"
    ] = username
# ============================================================
# عرض النتائج
# ============================================================
if "results" in st.session_state:
    df = st.session_state[
        "results"
    ]
    username = st.session_state[
        "username"
    ]
    errors = st.session_state[
        "errors"
    ]
    st.divider()
    st.header(
        f"📊 النتائج — @{username}"
    )
    # --------------------------------------------------------
    # الإحصائيات
    # --------------------------------------------------------
    total_results = len(df)
    instagram_results = 0
    threads_results = 0
    reel_results = 0
    if not df.empty:
        instagram_results = int(
            df["category"]
            .astype(str)
            .str.startswith("Instagram")
            .sum()
        )
        threads_results = int(
            (
                df["category"]
                == "Threads"
            ).sum()
        )
        reel_results = int(
            (
                df["category"]
                == "Instagram Reel"
            ).sum()
        )
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric(
            "إجمالي النتائج",
            total_results,
        )
    with col2:
        st.metric(
            "Instagram",
            instagram_results,
        )
    with col3:
        st.metric(
            "Reels",
            reel_results,
        )
    with col4:
        st.metric(
            "Threads",
            threads_results,
        )
    # --------------------------------------------------------
    # أخطاء البحث
    # --------------------------------------------------------
    if errors:
        with st.expander(
            f"⚠️ استعلامات لم تنجح ({len(errors)})"
        ):
            for error in errors:
                st.write(
                    f"**Query:** {error['query']}"
                )
                st.code(
                    error["error"]
                )
    # --------------------------------------------------------
    # لا توجد نتائج
    # --------------------------------------------------------
    if df.empty:
        st.warning(
            "لم يتم العثور على نتائج. "
            "جرّب backend آخر من القائمة الجانبية."
        )
        st.stop()
    # --------------------------------------------------------
    # الفلاتر
    # --------------------------------------------------------
    st.subheader(
        "🔎 فلترة النتائج"
    )
    filter_col1, filter_col2, filter_col3 = st.columns(3)
    with filter_col1:
        categories = [
            "All"
        ] + sorted(
            df["category"]
            .dropna()
            .unique()
            .tolist()
        )
        selected_category = st.selectbox(
            "الفئة",
            categories,
        )
    with filter_col2:
        minimum_score = st.slider(
            "Minimum Score",
            min_value=0,
            max_value=int(
                max(
                    10,
                    df["score"].max()
                )
            ),
            value=0,
        )
    with filter_col3:
        search_text = st.text_input(
            "بحث داخل النتائج",
            placeholder="كلمة أو جزء من URL...",
        )
    filtered = df.copy()
    if selected_category != "All":
        filtered = filtered[
            filtered["category"]
            == selected_category
        ]
    filtered = filtered[
        filtered["score"]
        >= minimum_score
    ]
    if search_text:
        pattern = re.escape(
            search_text
        )
        mask = (
            filtered["title"]
            .fillna("")
            .str.contains(
                pattern,
                case=False,
                regex=True,
            )
            |
            filtered["snippet"]
            .fillna("")
            .str.contains(
                pattern,
                case=False,
                regex=True,
            )
            |
            filtered["url"]
            .fillna("")
            .str.contains(
                pattern,
                case=False,
                regex=True,
            )
            |
            filtered["domain"]
            .fillna("")
            .str.contains(
                pattern,
                case=False,
                regex=True,
            )
        )
        filtered = filtered[
            mask
        ]
    st.caption(
        f"عرض {len(filtered)} من أصل {len(df)} نتيجة"
    )
    # --------------------------------------------------------
    # جدول النتائج
    # --------------------------------------------------------
    display_columns = [
        "score",
        "category",
        "title",
        "url",
        "snippet",
        "domain",
        "backend",
        "query",
    ]
    st.dataframe(
        filtered[display_columns],
        use_container_width=True,
        hide_index=True,
        column_config={
            "url": st.column_config.LinkColumn(
                "الرابط",
                display_text="فتح الرابط",
            ),
            "score": st.column_config.NumberColumn(
                "Score",
                format="%d",
            ),
        },
    )
    # --------------------------------------------------------
    # التحميل
    # --------------------------------------------------------
    st.divider()
    st.subheader(
        "📥 تصدير النتائج"
    )
    export_col1, export_col2, export_col3 = st.columns(3)
    # JSON
    json_data = json.dumps(
        filtered.to_dict(
            orient="records"
        ),
        ensure_ascii=False,
        indent=2,
    )
    with export_col1:
        st.download_button(
            "📄 تحميل JSON",
            data=json_data,
            file_name=f"{username}_results.json",
            mime="application/json",
            use_container_width=True,
        )
    # CSV
    csv_data = filtered.to_csv(
        index=False,
        encoding="utf-8-sig",
    )
    with export_col2:
        st.download_button(
            "📊 تحميل CSV",
            data=csv_data,
            file_name=f"{username}_results.csv",
            mime="text/csv",
            use_container_width=True,
        )
    # Excel
    excel_data = dataframe_to_excel(
        filtered
    )
    with export_col3:
        st.download_button(
            "📗 تحميل Excel",
            data=excel_data,
            file_name=f"{username}_results.xlsx",
            mime=(
                "application/vnd.openxmlformats-"
                "officedocument.spreadsheetml.sheet"
            ),
            use_container_width=True,
        )
# ============================================================
# Footer
# ============================================================
st.divider()
st.caption(
    "Public-source search only — لا يتم تسجيل الدخول إلى الحسابات "
    "ولا تجاوز CAPTCHA أو أنظمة الحماية."
)