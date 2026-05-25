from __future__ import annotations

import sqlite3

import typer

from bucket import queries
from bucket.main import EXIT_CONFLICT, EXIT_NOT_FOUND, emit, fail, get_conn
from bucket.ranking import choose_pivot, next_bounds


class RankingPromptRequiredError(RuntimeError):
    pass


def register(app: typer.Typer) -> None:
    @app.command()
    def review(
        ctx: typer.Context,
        ranking: bool = typer.Option(False, "--ranking", help="Enter pairwise ranking mode."),
        horizon: str | None = typer.Option(None, "--horizon"),
        all_items: bool = typer.Option(False, "--all", help="Include waiting, completed, and no-longer-me items."),
        limit: int = typer.Option(1, "--limit", min=1, help="Number of candidates to rank."),
        until_all_ranked: bool = typer.Option(
            False,
            "--until-all-ranked",
            help="Keep ranking unranked eligible items, then stop before re-ranking existing items.",
        ),
        randomize: bool = typer.Option(True, "--randomize/--no-randomize", help="Randomize pivots near the midpoint."),
    ) -> None:
        """Review bucket list items."""
        if ranking:
            try:
                conn = get_conn(ctx)
                try:
                    results = run_ranking_session(
                        conn,
                        horizon=horizon,
                        include_all=all_items,
                        limit=limit,
                        randomize=randomize,
                        quiet=ctx.obj["json"],
                        until_all_ranked=until_all_ranked,
                    )
                finally:
                    conn.close()
            except RankingPromptRequiredError as exc:
                fail(str(exc), EXIT_CONFLICT)
            else:
                emit(
                    ctx,
                    [item.to_dict() for item in results],
                    lambda console: console.print(f"Ranked {len(results)} item(s)."),
                )
                return

        if ctx.obj["json"]:
            typer.echo("GTD review is interactive and does not support --json.", err=True)
            raise typer.Exit(1)

        # GTD review is interactive; each mutation is self-committing so
        # partial progress is preserved if the user quits mid-session.
        conn = get_conn(ctx)
        try:
            run_gtd_review(conn, horizon=horizon, include_all=all_items)
        finally:
            conn.close()

    @app.command("rank-next")
    def rank_next(
        ctx: typer.Context,
        horizon: str | None = typer.Option(None, "--horizon"),
        all_items: bool = typer.Option(False, "--all", help="Include waiting, completed, and no-longer-me items."),
        randomize: bool = typer.Option(True, "--randomize/--no-randomize", help="Randomize pivots near the midpoint."),
        allow_rerank: bool = typer.Option(False, "--allow-rerank", help="Allow re-ranking existing ranked items."),
    ) -> None:
        """Return the next agent-drivable ranking comparison or auto-rank if no comparison is needed."""
        try:
            conn = get_conn(ctx)
            try:
                payload = next_ranking_step(
                    conn,
                    horizon=horizon,
                    include_all=all_items,
                    randomize=randomize,
                    allow_rerank=allow_rerank,
                )
            finally:
                conn.close()
        except ValueError as exc:
            fail(str(exc))
        emit(ctx, payload, render_ranking_payload)

    @app.command("rank-answer")
    def rank_answer(
        ctx: typer.Context,
        candidate: int = typer.Option(..., "--candidate", help="Candidate item ID from rank-next."),
        pivot: int = typer.Option(..., "--pivot", help="Pivot item ID from rank-next."),
        winner: str = typer.Option(..., "--winner", help="candidate, pivot, or skip."),
    ) -> None:
        """Apply one agent-drivable ranking answer and return the next step."""
        try:
            conn = get_conn(ctx)
            try:
                payload = apply_ranking_answer(conn, candidate_id=candidate, pivot_id=pivot, winner=winner)
            finally:
                conn.close()
        except LookupError as exc:
            fail(str(exc), EXIT_NOT_FOUND)
        except ValueError as exc:
            fail(str(exc), EXIT_CONFLICT)
        emit(ctx, payload, render_ranking_payload)


def run_gtd_review(
    conn: sqlite3.Connection,
    *,
    horizon: str | None,
    include_all: bool,
) -> None:
    """Interactive GTD-style review of items."""
    items = queries.get_review_items(conn, horizon=horizon, include_all=include_all)
    if not items:
        typer.echo("No items to review.")
        return

    typer.echo(f"\nReviewing {len(items)} item(s).\n")

    reviewed = 0
    for item in items:
        typer.echo("─" * 50)
        typer.echo(f"  {item.title}")
        typer.echo(f"  Horizon: {item.horizon} | Status: {item.status}")
        if item.description:
            typer.echo(f"  {item.description}")
        if item.tags:
            typer.echo(f"  Tags: {', '.join(item.tags)}")

        typer.echo()
        answer = typer.prompt(
            "[y] keep  [n] now  [s] soon  [l] later  [w] waiting  [d] done  [x] no longer me  [skip]  [quit]"
        ).strip().lower()

        if answer in {"q", "quit"}:
            break
        if answer in {"skip", ""}:
            continue
        if answer in {"n", "now"}:
            queries.update_item(conn, item.id, horizon="now")
            reviewed += 1
        elif answer in {"s", "soon"}:
            queries.update_item(conn, item.id, horizon="soon")
            reviewed += 1
        elif answer in {"l", "later"}:
            queries.update_item(conn, item.id, horizon="later")
            reviewed += 1
        elif answer in {"w", "waiting"}:
            queries.update_item(conn, item.id, horizon="waiting")
            reviewed += 1
        elif answer in {"d", "done"}:
            queries.set_status(conn, item.id, "completed")
            reviewed += 1
        elif answer in {"x", "no longer me", "no_longer_me"}:
            queries.set_status(conn, item.id, "no_longer_me")
            reviewed += 1
        elif answer in {"y", "yes", "keep"}:
            # explicitly keep — no-op, counts as reviewed
            reviewed += 1
        else:
            typer.echo("  Unrecognized choice, skipping.")

    typer.echo(f"\nReviewed {reviewed} item(s).")


def _comparison_payload(candidate, pivot) -> dict:
    return {
        "status": "comparison",
        "candidate": candidate.to_dict(),
        "pivot": pivot.to_dict(),
        "choices": {"candidate": candidate.id, "pivot": pivot.id, "skip": None},
    }


def _ranked_payload(item) -> dict:
    return {"status": "ranked", "item": item.to_dict()}


def _session_matches_filters(session, *, horizon: str | None, include_all: bool) -> bool:
    return session["horizon"] == horizon and bool(session["include_all"]) == include_all


def render_ranking_payload(payload: dict, console) -> None:
    status = payload.get("status")
    if status == "comparison":
        console.print("Which would you rather do sooner?")
        console.print(f"candidate #{payload['candidate']['id']}: {payload['candidate']['title']}")
        console.print(f"pivot #{payload['pivot']['id']}: {payload['pivot']['title']}")
    elif status == "ranked":
        item = payload["item"]
        console.print(f"Ranked #{item['id']} at rank {item['rank']}.")
    elif status == "skipped":
        console.print(f"Skipped ranking #{payload['candidate']['id']}.")
    else:
        console.print(payload.get("message", "No ranking step available."))


def next_ranking_step(
    conn: sqlite3.Connection,
    *,
    horizon: str | None,
    include_all: bool,
    randomize: bool,
    allow_rerank: bool,
) -> dict:
    session = queries.get_any_ranking_session(conn)
    if session is not None:
        if not _session_matches_filters(session, horizon=horizon, include_all=include_all):
            raise ValueError("pending ranking session uses different filters; answer or skip it first")
        candidate = queries.get_item(conn, int(session["candidate_id"]))
        pivot = queries.get_item(conn, int(session["pivot_id"])) if session["pivot_id"] is not None else None
        if candidate is not None and pivot is not None:
            return _comparison_payload(candidate, pivot)
        if candidate is not None:
            queries.delete_ranking_session(conn, candidate.id)

    candidate, is_rerank = queries.choose_ranking_candidate(
        conn, horizon=horizon, include_all=include_all, allow_rerank=allow_rerank
    )
    if candidate is None:
        return {"status": "empty", "message": "No eligible items to rank."}
    if is_rerank:
        queries.remove_item_from_ranking(conn, candidate.id)
        candidate = queries.get_item(conn, candidate.id)
        assert candidate is not None

    ranked_items = queries.get_ranked_items(conn, horizon=horizon, include_all=include_all)
    if not ranked_items:
        ranked = queries.insert_item_at_rank(conn, candidate.id, queries.max_rank(conn) + 1)
        assert ranked is not None
        return _ranked_payload(ranked)

    low = 0
    high = len(ranked_items)
    pivot_index = choose_pivot(low, high, randomize=randomize)
    pivot = ranked_items[pivot_index]
    queries.save_ranking_session(
        conn,
        candidate_id=candidate.id,
        low=low,
        high=high,
        pivot_id=pivot.id,
        pivot_index=pivot_index,
        horizon=horizon,
        include_all=include_all,
        randomize=randomize,
    )
    return _comparison_payload(candidate, pivot)


def apply_ranking_answer(conn: sqlite3.Connection, *, candidate_id: int, pivot_id: int, winner: str) -> dict:
    winner = winner.strip().lower()
    if winner not in {"candidate", "pivot", "skip"}:
        raise ValueError("winner must be one of: candidate, pivot, skip")

    session = queries.get_ranking_session(conn, candidate_id)
    if session is None:
        raise ValueError("ranking session not found; run rank-next first")
    if session["pivot_id"] is None or int(session["pivot_id"]) != pivot_id:
        raise ValueError("ranking session pivot mismatch; run rank-next again")

    candidate = queries.get_item(conn, candidate_id)
    pivot = queries.get_item(conn, pivot_id)
    if candidate is None:
        raise LookupError(f"item not found: {candidate_id}")
    if pivot is None:
        raise LookupError(f"item not found: {pivot_id}")

    if winner == "skip":
        queries.delete_ranking_session(conn, candidate_id)
        return {"status": "skipped", "candidate": candidate.to_dict(), "pivot": pivot.to_dict()}

    horizon = session["horizon"]
    include_all = bool(session["include_all"])
    randomize = bool(session["randomize"])
    ranked_items = queries.get_ranked_items(conn, horizon=horizon, include_all=include_all)
    pivot_index = int(session["pivot_index"])
    if pivot_index >= len(ranked_items) or ranked_items[pivot_index].id != pivot_id:
        raise ValueError("ranking changed since rank-next; run rank-next again")

    low, high = next_bounds(
        int(session["low"]),
        int(session["high"]),
        pivot_index,
        candidate_wins=winner == "candidate",
    )
    queries.increment_rank_quiz_counts(conn, [candidate_id, pivot_id])
    if low >= high:
        target_rank = queries.target_rank_for_filtered_insert(conn, ranked_items, low)
        ranked = queries.insert_item_at_rank(conn, candidate_id, target_rank)
        assert ranked is not None
        queries.delete_ranking_session(conn, candidate_id)
        return _ranked_payload(ranked)

    next_pivot_index = choose_pivot(low, high, randomize=randomize)
    next_pivot = ranked_items[next_pivot_index]
    queries.save_ranking_session(
        conn,
        candidate_id=candidate_id,
        low=low,
        high=high,
        pivot_id=next_pivot.id,
        pivot_index=next_pivot_index,
        horizon=horizon,
        include_all=include_all,
        randomize=randomize,
    )
    candidate = queries.get_item(conn, candidate_id)
    assert candidate is not None
    return _comparison_payload(candidate, next_pivot)


def run_ranking_session(
    conn,
    *,
    horizon: str | None,
    include_all: bool,
    limit: int,
    randomize: bool,
    quiet: bool = False,
    until_all_ranked: bool = False,
):
    if quiet:
        raise RankingPromptRequiredError(
            "review --ranking needs an interactive comparison; use rank-next/rank-answer with --json"
        )

    ranked_results = []
    skipped_item_ids: set[int] = set()
    ranked_count = 0
    while until_all_ranked or ranked_count < limit:
        candidate, is_rerank = queries.choose_ranking_candidate(
            conn,
            horizon=horizon,
            include_all=include_all,
            allow_rerank=not until_all_ranked,
            exclude_item_ids=skipped_item_ids,
        )
        if candidate is None:
            typer.echo("No eligible items to rank.")
            break
        if is_rerank:
            queries.remove_item_from_ranking(conn, candidate.id)
            candidate = queries.get_item(conn, candidate.id)
            assert candidate is not None

        ranked_items = queries.get_ranked_items(conn, horizon=horizon, include_all=include_all)
        if not ranked_items:
            ranked = queries.insert_item_at_rank(conn, candidate.id, queries.max_rank(conn) + 1)
            assert ranked is not None
            ranked_results.append(ranked)
            ranked_count += 1
            typer.echo(f"Ranked '{ranked.title}' at #{ranked.rank}.")
            continue

        insertion_index = ask_for_insertion_index(conn, candidate, ranked_items, randomize=randomize)
        if insertion_index == "skip":
            skipped_item_ids.add(candidate.id)
            continue
        if insertion_index is None:
            break
        target_rank = queries.target_rank_for_filtered_insert(conn, ranked_items, insertion_index)
        ranked = queries.insert_item_at_rank(conn, candidate.id, target_rank)
        assert ranked is not None
        ranked_results.append(ranked)
        ranked_count += 1
        typer.echo(f"Ranked '{ranked.title}' at #{ranked.rank}.")
    return ranked_results


def ask_for_insertion_index(conn, candidate, ranked_items, *, randomize: bool) -> int | str | None:
    low = 0
    high = len(ranked_items)
    while low < high:
        pivot_index = choose_pivot(low, high, randomize=randomize)
        pivot = ranked_items[pivot_index]
        typer.echo("\nWhich would you rather do sooner?\n")
        typer.echo(f"1. {candidate.title}")
        typer.echo(f"2. {pivot.title}")
        answer = typer.prompt("Choose [1/2/skip/quit]").strip().lower()
        if answer in {"q", "quit"}:
            return None
        if answer in {"s", "skip"}:
            return "skip"
        if answer not in {"1", "2"}:
            typer.echo("Please choose 1, 2, skip, or quit.")
            continue
        queries.increment_rank_quiz_counts(conn, [candidate.id, pivot.id])
        low, high = next_bounds(low, high, pivot_index, candidate_wins=answer == "1")
    return low
