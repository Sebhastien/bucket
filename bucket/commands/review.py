from __future__ import annotations

import sqlite3

import typer

from bucket import queries
from bucket.main import emit, get_conn
from bucket.ranking import choose_pivot, next_bounds


def register(app: typer.Typer) -> None:
    @app.command()
    def review(
        ctx: typer.Context,
        ranking: bool = typer.Option(False, "--ranking", help="Enter pairwise ranking mode."),
        horizon: str | None = typer.Option(None, "--horizon"),
        all_items: bool = typer.Option(False, "--all", help="Include blocked, completed, and abandoned items."),
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
            with get_conn(ctx) as conn:
                results = run_ranking_session(
                    conn,
                    horizon=horizon,
                    include_all=all_items,
                    limit=limit,
                    randomize=randomize,
                    quiet=ctx.obj["json"],
                    until_all_ranked=until_all_ranked,
                )
            emit(ctx, [item.to_dict() for item in results], lambda console: console.print(f"Ranked {len(results)} item(s)."))
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
        typer.echo(f"─" * 50)
        typer.echo(f"  {item.title}")
        typer.echo(f"  Horizon: {item.horizon} | Status: {item.status}")
        if item.description:
            typer.echo(f"  {item.description}")
        if item.tags:
            typer.echo(f"  Tags: {', '.join(item.tags)}")

        typer.echo()
        answer = typer.prompt(
            "[y] keep  [n] now  [s] soon  [d] done  [a] abandon  [skip]  [quit]"
        ).strip().lower()

        if answer in {"q", "quit"}:
            break
        if answer in {"skip", ""}:
            continue
        if answer in {"n", "now"}:
            queries.update_item(conn, item.id, horizon="now")
            conn.commit()
            reviewed += 1
        elif answer in {"s", "soon"}:
            queries.update_item(conn, item.id, horizon="soon")
            conn.commit()
            reviewed += 1
        elif answer in {"d", "done"}:
            queries.set_status(conn, item.id, "completed")
            conn.commit()
            reviewed += 1
        elif answer in {"a", "abandon"}:
            queries.set_status(conn, item.id, "abandoned")
            conn.commit()
            reviewed += 1
        elif answer in {"y", "yes", "keep"}:
            # explicitly keep — no-op, counts as reviewed
            reviewed += 1
        else:
            typer.echo("  Unrecognized choice, skipping.")

    typer.echo(f"\nReviewed {reviewed} item(s).")


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
            if not quiet:
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
            if not quiet:
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
        if not quiet:
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
