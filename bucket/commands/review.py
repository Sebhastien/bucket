from __future__ import annotations

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
        randomize: bool = typer.Option(True, "--randomize/--no-randomize", help="Randomize pivots near the midpoint."),
    ) -> None:
        """Review bucket list items."""
        if not ranking:
            typer.echo("Use --ranking to enter pairwise ranking mode.")
            return
        with get_conn(ctx) as conn:
            results = run_ranking_session(
                conn,
                horizon=horizon,
                include_all=all_items,
                limit=limit,
                randomize=randomize,
                quiet=ctx.obj["json"],
            )
        emit(ctx, [item.to_dict() for item in results], lambda console: console.print(f"Ranked {len(results)} item(s)."))


def run_ranking_session(conn, *, horizon: str | None, include_all: bool, limit: int, randomize: bool, quiet: bool = False):
    ranked_results = []
    for _ in range(limit):
        candidate, is_rerank = queries.choose_ranking_candidate(conn, horizon=horizon, include_all=include_all)
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
            if not quiet:
                typer.echo(f"Ranked '{ranked.title}' at #{ranked.rank}.")
            continue

        insertion_index = ask_for_insertion_index(conn, candidate, ranked_items, randomize=randomize)
        if insertion_index is None:
            break
        target_rank = queries.target_rank_for_filtered_insert(conn, ranked_items, insertion_index)
        ranked = queries.insert_item_at_rank(conn, candidate.id, target_rank)
        assert ranked is not None
        ranked_results.append(ranked)
        if not quiet:
            typer.echo(f"Ranked '{ranked.title}' at #{ranked.rank}.")
    return ranked_results


def ask_for_insertion_index(conn, candidate, ranked_items, *, randomize: bool) -> int | None:
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
            continue
        if answer not in {"1", "2"}:
            typer.echo("Please choose 1, 2, skip, or quit.")
            continue
        queries.increment_rank_quiz_counts(conn, [candidate.id, pivot.id])
        low, high = next_bounds(low, high, pivot_index, candidate_wins=answer == "1")
    return low
