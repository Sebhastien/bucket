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


def test_create_item_validates_input():
    conn = memory_conn()
    try:
        queries.create_item(conn, title="", horizon="now")
    except ValueError as exc:
        assert str(exc) == "title is required"
    else:
        raise AssertionError("empty title should fail")

    try:
        queries.create_item(conn, title="Bad horizon", horizon="later")
    except ValueError as exc:
        assert "horizon must be one of" in str(exc)
    else:
        raise AssertionError("bad horizon should fail")

    try:
        queries.create_item(conn, title="Bad priority", priority=9)
    except ValueError as exc:
        assert str(exc) == "priority must be between 1 and 5"
    else:
        raise AssertionError("bad priority should fail")


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


def test_ranking_candidate_can_disable_reranking():
    conn = memory_conn()
    first = queries.create_item(conn, title="First", horizon="now")
    queries.insert_item_at_rank(conn, first.id, 1)

    candidate, is_rerank = queries.choose_ranking_candidate(conn, allow_rerank=False)

    assert candidate is None
    assert is_rerank is False


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


def test_insert_item_at_rank_clamps_out_of_range_targets():
    conn = memory_conn()
    first = queries.create_item(conn, title="First", horizon="now")
    second = queries.create_item(conn, title="Second", horizon="now")

    queries.insert_item_at_rank(conn, first.id, 0)
    queries.insert_item_at_rank(conn, second.id, 99)

    assert [(item.title, item.rank) for item in queries.list_items(conn, all_items=True, ranked=True)] == [
        ("First", 1),
        ("Second", 2),
    ]


def test_add_tag_to_item():
    conn = memory_conn()
    item = queries.create_item(conn, title="Hike Grand Canyon", horizon="soon")
    updated = queries.add_tag_to_item(conn, item.id, "adventure")

    assert updated is not None
    assert updated.tags == ("adventure",)
    assert queries.get_item(conn, item.id).tags == ("adventure",)


def test_add_tag_normalizes_name():
    conn = memory_conn()
    item = queries.create_item(conn, title="Test")
    queries.add_tag_to_item(conn, item.id, "  Adventure  ")
    assert queries.get_item(conn, item.id).tags == ("adventure",)


def test_add_tag_idempotent():
    conn = memory_conn()
    item = queries.create_item(conn, title="Test")
    queries.add_tag_to_item(conn, item.id, "fun")
    queries.add_tag_to_item(conn, item.id, "fun")
    assert queries.get_item(conn, item.id).tags == ("fun",)


def test_remove_tag_from_item():
    conn = memory_conn()
    item = queries.create_item(conn, title="Test")
    queries.add_tag_to_item(conn, item.id, "fun")
    updated = queries.remove_tag_from_item(conn, item.id, "fun")

    assert updated is not None
    assert updated.tags == ()


def test_remove_tag_deletes_unused_tag():
    conn = memory_conn()
    item = queries.create_item(conn, title="Test")
    queries.add_tag_to_item(conn, item.id, "fun")
    queries.remove_tag_from_item(conn, item.id, "fun")

    assert queries.list_tags(conn) == []


def test_list_tags_with_counts():
    conn = memory_conn()
    a = queries.create_item(conn, title="A")
    b = queries.create_item(conn, title="B")
    queries.add_tag_to_item(conn, a.id, "adventure")
    queries.add_tag_to_item(conn, b.id, "adventure")
    queries.add_tag_to_item(conn, b.id, "travel")

    tags = queries.list_tags(conn)
    assert len(tags) == 2
    by_name = {t.name: t.item_count for t in tags}
    assert by_name == {"adventure": 2, "travel": 1}


def test_list_items_filtered_by_tag():
    conn = memory_conn()
    a = queries.create_item(conn, title="A", horizon="now")
    b = queries.create_item(conn, title="B", horizon="now")
    queries.add_tag_to_item(conn, a.id, "fun")

    items = queries.list_items(conn, tag="fun")
    assert [item.title for item in items] == ["A"]


def test_search_items():
    conn = memory_conn()
    queries.create_item(conn, title="Visit Japan", description="Tokyo and Kyoto")
    queries.create_item(conn, title="Hike Alps", description="Swiss mountains")
    queries.create_item(conn, title="Learn Python", description="Programming language")

    results = queries.search_items(conn, "japan")
    assert [item.title for item in results] == ["Visit Japan"]

    results = queries.search_items(conn, "mountain")
    assert [item.title for item in results] == ["Hike Alps"]

    results = queries.search_items(conn, "programming")
    assert [item.title for item in results] == ["Learn Python"]

    results = queries.search_items(conn, "xyz")
    assert results == []


def test_search_escapes_like_wildcards():
    conn = memory_conn()
    queries.create_item(conn, title="100% pure")
    queries.create_item(conn, title="test_item")
    queries.create_item(conn, title="Regular title")

    assert [item.title for item in queries.search_items(conn, "%")] == ["100% pure"]
    assert [item.title for item in queries.search_items(conn, "_")] == ["test_item"]
    assert [item.title for item in queries.search_items(conn, "pure")] == ["100% pure"]
    assert [item.title for item in queries.search_items(conn, "test")] == ["test_item"]


def test_block_item_sets_blocked_by_and_horizon():
    conn = memory_conn()
    blocker = queries.create_item(conn, title="Get passport")
    blocked = queries.create_item(conn, title="Travel to Japan")

    updated = queries.block_item(conn, blocked.id, blocker.id)

    assert updated is not None
    assert updated.blocked_by == blocker.id
    assert updated.horizon == "blocked"


def test_block_item_returns_none_for_missing_item():
    conn = memory_conn()
    blocker = queries.create_item(conn, title="Get passport")

    result = queries.block_item(conn, 999, blocker.id)
    assert result is None


def test_block_item_raises_for_missing_blocker():
    conn = memory_conn()
    blocked = queries.create_item(conn, title="Travel to Japan")

    try:
        queries.block_item(conn, blocked.id, 999)
    except ValueError as exc:
        assert "blocker not found" in str(exc)
    else:
        raise AssertionError("missing blocker should fail")


def test_circular_dependency_detected():
    conn = memory_conn()
    a = queries.create_item(conn, title="A")
    b = queries.create_item(conn, title="B")
    c = queries.create_item(conn, title="C")
    queries.block_item(conn, b.id, a.id)
    queries.block_item(conn, c.id, b.id)

    try:
        queries.block_item(conn, a.id, c.id)
    except ValueError as exc:
        assert "circular" in str(exc)
    else:
        raise AssertionError("circular dependency should fail")


def test_unblock_item_clears_blocked_by():
    conn = memory_conn()
    blocker = queries.create_item(conn, title="Get passport")
    blocked = queries.create_item(conn, title="Travel to Japan")
    queries.block_item(conn, blocked.id, blocker.id)

    updated = queries.unblock_item(conn, blocked.id)

    assert updated is not None
    assert updated.blocked_by is None
    # horizon is left as-is; user must edit if they want to change it
    assert updated.horizon == "blocked"


def test_unblock_item_returns_none_for_missing_item():
    conn = memory_conn()
    result = queries.unblock_item(conn, 999)
    assert result is None


def test_self_blocking_is_rejected():
    conn = memory_conn()
    item = queries.create_item(conn, title="A")

    try:
        queries.block_item(conn, item.id, item.id)
    except ValueError as exc:
        assert "cannot block itself" in str(exc)
    else:
        raise AssertionError("self-blocking should fail")


def test_delete_blocking_item_nullifies_dependents():
    conn = memory_conn()
    blocker = queries.create_item(conn, title="Get passport")
    blocked = queries.create_item(conn, title="Travel to Japan")
    queries.block_item(conn, blocked.id, blocker.id)

    queries.delete_item(conn, blocker.id)
    item = queries.get_item(conn, blocked.id)

    assert item is not None
    assert item.blocked_by is None


def test_add_note_to_item():
    conn = memory_conn()
    item = queries.create_item(conn, title="Test")
    note = queries.add_note(conn, item.id, "Remember to pack light")

    assert note is not None
    assert note.item_id == item.id
    assert note.body == "Remember to pack light"

    notes = queries.get_notes_for_item(conn, item.id)
    assert len(notes) == 1
    assert notes[0].body == "Remember to pack light"


def test_add_note_returns_none_for_missing_item():
    conn = memory_conn()
    result = queries.add_note(conn, 999, "Some text")
    assert result is None


def test_add_note_rejects_empty_body():
    conn = memory_conn()
    item = queries.create_item(conn, title="Test")
    try:
        queries.add_note(conn, item.id, "  ")
    except ValueError as exc:
        assert "required" in str(exc)
    else:
        raise AssertionError("empty note body should fail")


def test_get_notes_orders_newest_first():
    conn = memory_conn()
    item = queries.create_item(conn, title="Test")
    queries.add_note(conn, item.id, "First note")
    queries.add_note(conn, item.id, "Second note")

    notes = queries.get_notes_for_item(conn, item.id)
    assert [n.body for n in notes] == ["Second note", "First note"]


def test_get_stats_empty_database():
    conn = memory_conn()
    stats = queries.get_stats(conn)
    assert stats == {
        "total": 0,
        "by_status": {"active": 0, "in_progress": 0, "completed": 0, "abandoned": 0},
        "by_horizon": {"now": 0, "soon": 0, "someday": 0, "blocked": 0},
        "completion_rate": 0.0,
        "ranked": 0,
        "unranked": 0,
        "blocked": 0,
        "by_tag": [],
    }


def test_get_stats_reflects_items_and_tags():
    conn = memory_conn()
    queries.create_item(conn, title="A", horizon="now")
    queries.create_item(conn, title="B", horizon="soon")
    queries.create_item(conn, title="C", horizon="someday")
    queries.set_status(conn, 1, "completed")
    queries.add_tag_to_item(conn, 1, "travel")
    queries.add_tag_to_item(conn, 2, "travel")
    queries.add_tag_to_item(conn, 2, "adventure")

    stats = queries.get_stats(conn)
    assert stats["total"] == 3
    assert stats["by_status"] == {"active": 2, "in_progress": 0, "completed": 1, "abandoned": 0}
    assert stats["by_horizon"] == {"now": 1, "soon": 1, "someday": 1, "blocked": 0}
    assert abs(stats["completion_rate"] - 1 / 3) < 1e-4
    assert stats["ranked"] == 0
    assert stats["unranked"] == 3
    assert stats["blocked"] == 0
    assert {t["name"]: t["count"] for t in stats["by_tag"]} == {"travel": 2, "adventure": 1}


def test_get_stats_with_ranked_and_blocked():
    conn = memory_conn()
    queries.create_item(conn, title="A", horizon="now")
    queries.create_item(conn, title="B", horizon="now")
    queries.insert_item_at_rank(conn, 1, 1)
    queries.block_item(conn, 2, 1)

    stats = queries.get_stats(conn)
    assert stats["total"] == 2
    assert stats["ranked"] == 1
    assert stats["unranked"] == 1
    assert stats["blocked"] == 1
    assert stats["by_horizon"]["blocked"] == 1


def test_add_tag_rejects_comma():
    conn = memory_conn()
    item = queries.create_item(conn, title="Test")
    try:
        queries.add_tag_to_item(conn, item.id, "road,trip")
    except ValueError as exc:
        assert "comma" in str(exc)
    else:
        raise AssertionError("comma in tag name should fail")


def test_get_review_items_defaults():
    conn = memory_conn()
    queries.create_item(conn, title="A", horizon="now")
    queries.create_item(conn, title="B", horizon="soon")
    queries.create_item(conn, title="C", horizon="someday")
    queries.create_item(conn, title="D", horizon="blocked")
    queries.create_item(conn, title="E", horizon="someday")
    queries.set_status(conn, 5, "completed")

    items = queries.get_review_items(conn)
    titles = [i.title for i in items]
    assert titles == ["B", "C"]


def test_get_review_items_by_horizon():
    conn = memory_conn()
    queries.create_item(conn, title="A", horizon="soon")
    queries.create_item(conn, title="B", horizon="someday")

    items = queries.get_review_items(conn, horizon="soon")
    assert [i.title for i in items] == ["A"]

    items = queries.get_review_items(conn, horizon="someday")
    assert [i.title for i in items] == ["B"]


def test_get_review_items_include_all():
    conn = memory_conn()
    queries.create_item(conn, title="A", horizon="soon")
    queries.set_status(conn, 1, "completed")

    items = queries.get_review_items(conn)
    assert len(items) == 0

    items = queries.get_review_items(conn, include_all=True)
    assert [i.title for i in items] == ["A"]


def test_get_review_items_empty():
    conn = memory_conn()
    assert queries.get_review_items(conn) == []
    assert queries.get_review_items(conn, horizon="now") == []
