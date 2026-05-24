from bucket import db, queries


def memory_conn():
    return db.connect(":memory:")


def test_create_get_update_delete_item():
    conn = memory_conn()
    item = queries.create_item(conn, title="Hike Grand Canyon", horizon="soon", priority=2)

    assert item.id == 1
    assert item.title == "Hike Grand Canyon"
    assert item.horizon == "soon"

    updated = queries.update_item(conn, item.id, title="Hike the Grand Canyon", horizon="now")
    assert updated is not None
    assert updated.title == "Hike the Grand Canyon"
    assert updated.horizon == "now"

    completed = queries.set_status(conn, item.id, "completed")
    assert completed is not None
    assert completed.status == "completed"
    assert completed.completed_at is not None

    deleted = queries.delete_item(conn, item.id)
    assert deleted is not None
    assert queries.get_item(conn, item.id) is None


def test_list_defaults_to_now():
    conn = memory_conn()
    queries.create_item(conn, title="Now", horizon="now")
    queries.create_item(conn, title="Soon", horizon="soon")

    assert [item.title for item in queries.list_items(conn)] == ["Now"]
    assert {item.title for item in queries.list_items(conn, all_items=True)} == {"Now", "Soon"}


def test_ranking_candidate_prefers_unranked_eligible_items():
    conn = memory_conn()
    ranked = queries.create_item(conn, title="Ranked", horizon="now")
    unranked = queries.create_item(conn, title="Unranked", horizon="now")
    blocked = queries.create_item(conn, title="Blocked", horizon="blocked")
    queries.insert_item_at_rank(conn, ranked.id, 1)

    candidate, is_rerank = queries.choose_ranking_candidate(conn)

    assert candidate == unranked
    assert is_rerank is False
    assert blocked.rank is None


def test_ranking_candidate_falls_back_to_least_quizzed_ranked_item():
    conn = memory_conn()
    first = queries.create_item(conn, title="First", horizon="now")
    second = queries.create_item(conn, title="Second", horizon="now")
    queries.insert_item_at_rank(conn, first.id, 1)
    queries.insert_item_at_rank(conn, second.id, 2)
    queries.increment_rank_quiz_counts(conn, [second.id])

    candidate, is_rerank = queries.choose_ranking_candidate(conn)

    assert candidate is not None
    assert candidate.id == first.id
    assert is_rerank is True


def test_insert_item_at_rank_shifts_existing_ranks():
    conn = memory_conn()
    first = queries.create_item(conn, title="First", horizon="now")
    second = queries.create_item(conn, title="Second", horizon="now")
    third = queries.create_item(conn, title="Third", horizon="now")
    queries.insert_item_at_rank(conn, first.id, 1)
    queries.insert_item_at_rank(conn, second.id, 2)

    inserted = queries.insert_item_at_rank(conn, third.id, 2)

    assert inserted is not None
    assert [(item.title, item.rank) for item in queries.list_items(conn, all_items=True, ranked=True)] == [
        ("First", 1),
        ("Third", 2),
        ("Second", 3),
    ]


def test_remove_item_from_ranking_closes_gap():
    conn = memory_conn()
    first = queries.create_item(conn, title="First", horizon="now")
    second = queries.create_item(conn, title="Second", horizon="now")
    queries.insert_item_at_rank(conn, first.id, 1)
    queries.insert_item_at_rank(conn, second.id, 2)

    queries.remove_item_from_ranking(conn, first.id)

    assert [(item.title, item.rank) for item in queries.list_items(conn, all_items=True, ranked=True)] == [
        ("Second", 1),
        ("First", None),
    ]
