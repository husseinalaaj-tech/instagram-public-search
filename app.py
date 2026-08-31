def perform_search(
    username: str,
    settings: dict,
):
    queries = generate_all_queries(
        username=username,
        max_queries=settings["max_queries"],
    )

    clear_results()

    st.session_state.searched_username = username
    st.session_state.total_queries = len(queries)

    if not queries:
        st.error("No queries were generated.")
        return

    provider = DDGSSearchProvider()

    all_results = []
    seen_urls = set()

    progress = st.progress(
        0,
        text="Starting search..."
    )

    status_placeholder = st.empty()
    live_stats_placeholder = st.empty()
    results_placeholder = st.empty()

    for number, query in enumerate(
        queries,
        start=1,
    ):
        status_placeholder.info(
            f"🔎 Query {number} / {len(queries)}\n\n"
            f"**Category:** {query.category}\n\n"
            f"`{query.text}`"
        )

        progress.progress(
            int(
                ((number - 1) / len(queries)) * 100
            ),
            text=f"Searching {number} / {len(queries)}"
        )

        results, error = execute_query(
            provider=provider,
            query=query,
            username=username,
            settings=settings,
        )

        if error:
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

            # Add only new URLs immediately.
            new_results = []

            for result in results:
                key = url_key(result.url)

                if not key:
                    continue

                if key in seen_urls:
                    continue

                seen_urls.add(key)
                new_results.append(result)

            all_results.extend(new_results)

        # ----------------------------------------------------
        # LIVE DEDUPLICATION + SORTING
        # ----------------------------------------------------

        live_results = deduplicate_results(
            results=all_results,
            username=username,
        )

        # Save immediately to session state.
        st.session_state.results = live_results

        # ----------------------------------------------------
        # LIVE STATISTICS
        # ----------------------------------------------------

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

            Queries completed: **{number}/{len(queries)}**  
            Unique results: **{len(live_results)}**  
            Comment matches: **{comment_count}**  
            Mention matches: **{mention_count}**  
            Reels: **{reel_count}**  
            Posts: **{post_count}**
            """
        )

        # ----------------------------------------------------
        # SHOW RESULTS IMMEDIATELY
        # ----------------------------------------------------

        if live_results:

            live_df = results_dataframe(
                live_results
            )

            results_placeholder.dataframe(
                live_df,
                use_container_width=True,
                hide_index=True,
                height=500,
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

        # ----------------------------------------------------
        # SMALL DELAY BETWEEN REQUESTS
        # ----------------------------------------------------

        if number < len(queries):
            randomized_delay(
                settings["delay_min"],
                settings["delay_max"],
            )

    # --------------------------------------------------------
    # FINISHED
    # --------------------------------------------------------

    final_results = deduplicate_results(
        results=all_results,
        username=username,
    )

    st.session_state.results = final_results
    st.session_state.search_completed = True

    progress.progress(
        100,
        text=(
            f"Completed {len(queries)} / "
            f"{len(queries)} queries"
        ),
    )

    status_placeholder.success(
        f"✅ Search completed — "
        f"{len(final_results)} unique results found."
    )

    live_stats_placeholder.markdown(
        f"""
        ### Final Results

        Queries completed: **{len(queries)} / {len(queries)}**

        Successful: **{st.session_state.successful_queries}**

        Failed: **{st.session_state.failed_queries}**

        Unique results: **{len(final_results)}**
        """
    )