import json

from typer.testing import CliRunner

from bucket import db
from bucket.main import app

runner = CliRunner()


def invoke(db_path, *args):
    return runner.invoke(app, ["--db", str(db_path), "--json", *args])


def test_json_crud_contract(tmp_path):
    db_path = tmp_path / "bucket.sqlite"

    result = invoke(db_path, "add", "Hike Grand Canyon", "--horizon", "soon", "--priority", "2")
    assert result.exit_code == 0, result.output
    created = json.loads(result.output)
    assert created["id"] == 1
    assert created["horizon"] == "soon"

    result = invoke(db_path, "list", "--all")
    assert result.exit_code == 0, result.output
    items = json.loads(result.output)
    assert [item["title"] for item in items] == ["Hike Grand Canyon"]

    result = invoke(db_path, "edit", "1", "--title", "Hike the Grand Canyon", "--horizon", "now")
    assert result.exit_code == 0, result.output
    edited = json.loads(result.output)
    assert edited["title"] == "Hike the Grand Canyon"
    assert edited["horizon"] == "now"

    result = invoke(db_path, "done", "1")
    assert result.exit_code == 0, result.output
    completed = json.loads(result.output)
    assert completed["status"] == "completed"
    assert completed["completed_at"] is not None

    result = invoke(db_path, "delete", "1", "--confirm")
    assert result.exit_code == 0, result.output
    deleted = json.loads(result.output)
    assert deleted["id"] == 1


def test_edit_can_clear_optional_fields(tmp_path):
    db_path = tmp_path / "bucket.sqlite"
    assert invoke(
        db_path,
        "add",
        "Clear me",
        "--desc",
        "old desc",
        "--priority",
        "3",
        "--date",
        "2030-01-01",
    ).exit_code == 0

    result = invoke(db_path, "edit", "1", "--clear-desc", "--clear-priority", "--clear-date")

    assert result.exit_code == 0, result.output
    item = json.loads(result.output)
    assert item["description"] is None
    assert item["priority"] is None
    assert item["target_date"] is None



def test_default_list_shows_only_actionable_now_items(tmp_path):
    db_path = tmp_path / "bucket.sqlite"
    assert invoke(db_path, "add", "Active now", "--horizon", "now").exit_code == 0
    assert invoke(db_path, "add", "Soon", "--horizon", "soon").exit_code == 0
    assert invoke(db_path, "add", "Done now", "--horizon", "now").exit_code == 0
    assert invoke(db_path, "done", "3").exit_code == 0

    result = invoke(db_path, "list")

    assert result.exit_code == 0, result.output
    items = json.loads(result.output)
    assert [item["title"] for item in items] == ["Active now"]



def test_start_marks_item_in_progress(tmp_path):
    db_path = tmp_path / "bucket.sqlite"
    assert invoke(db_path, "add", "Build a canoe").exit_code == 0

    result = invoke(db_path, "start", "1")

    assert result.exit_code == 0, result.output
    started = json.loads(result.output)
    assert started["status"] == "in_progress"
    assert started["completed_at"] is None


def test_not_found_exit_code(tmp_path):
    result = invoke(tmp_path / "bucket.sqlite", "show", "999")
    assert result.exit_code == 2


def test_edit_not_found_exit_code(tmp_path):
    result = invoke(tmp_path / "bucket.sqlite", "edit", "999", "--title", "Missing")
    assert result.exit_code == 2


def test_schema_json(tmp_path):
    result = invoke(tmp_path / "bucket.sqlite", "schema")
    assert result.exit_code == 0, result.output
    schema = json.loads(result.output)
    assert schema["tables"]["items"]["horizon"] == ["now", "soon", "later", "waiting"]
    assert "rank_quiz_count" in schema["tables"]["items"]


def test_backup_restore_round_trip(tmp_path):
    source_db = tmp_path / "source.sqlite"
    restored_db = tmp_path / "restored.sqlite"
    backup_file = tmp_path / "backup.json"

    assert invoke(source_db, "add", "Visit Japan", "--horizon", "soon", "--priority", "2").exit_code == 0
    assert invoke(source_db, "add", "Hike Grand Canyon", "--horizon", "now").exit_code == 0
    assert invoke(source_db, "start", "2").exit_code == 0
    assert runner.invoke(app, ["--db", str(source_db), "review", "--ranking", "--limit", "1"]).exit_code == 0

    result = invoke(source_db, "backup", "--dest", str(backup_file))
    assert result.exit_code == 0, result.output
    backup_result = json.loads(result.output)
    assert backup_result["path"] == str(backup_file)
    assert backup_file.exists()

    result = invoke(restored_db, "restore", str(backup_file))
    assert result.exit_code == 0, result.output
    restore_result = json.loads(result.output)
    assert restore_result["items"] == 2

    source_items = json.loads(invoke(source_db, "list", "--all", "--ranked").output)
    restored_items = json.loads(invoke(restored_db, "list", "--all", "--ranked").output)
    assert restored_items == source_items


def test_restore_existing_database_requires_confirmation(tmp_path):
    source_db = tmp_path / "source.sqlite"
    target_db = tmp_path / "target.sqlite"
    backup_file = tmp_path / "backup.json"
    assert invoke(source_db, "add", "Backup item").exit_code == 0
    assert invoke(source_db, "backup", "--dest", str(backup_file)).exit_code == 0
    assert invoke(target_db, "add", "Existing item").exit_code == 0

    result = invoke(target_db, "restore", str(backup_file))

    assert result.exit_code == 1
    items = json.loads(invoke(target_db, "list", "--all").output)
    assert [item["title"] for item in items] == ["Existing item"]

    result = invoke(target_db, "restore", str(backup_file), "--confirm")

    assert result.exit_code == 0, result.output
    items = json.loads(invoke(target_db, "list", "--all").output)
    assert [item["title"] for item in items] == ["Backup item"]


def test_restore_rejects_future_schema_version(tmp_path):
    db_path = tmp_path / "bucket.sqlite"
    backup_file = tmp_path / "future.json"
    backup_file.write_text('{"schema_version": 999, "items": [], "tags": [], "item_tags": [], "notes": []}')

    result = invoke(db_path, "restore", str(backup_file))

    assert result.exit_code == 1
    assert "newer schema version" in result.output


def test_review_ranking_inserts_unranked_item(tmp_path):
    db_path = tmp_path / "bucket.sqlite"
    assert invoke(db_path, "add", "First").exit_code == 0
    assert runner.invoke(app, ["--db", str(db_path), "review", "--ranking", "--limit", "1"]).exit_code == 0
    assert invoke(db_path, "add", "Second").exit_code == 0

    result = runner.invoke(app, ["--db", str(db_path), "review", "--ranking", "--no-randomize"], input="1\n")

    assert result.exit_code == 0, result.output
    result = invoke(db_path, "list", "--all", "--ranked")
    items = json.loads(result.output)
    assert [(item["title"], item["rank"]) for item in items] == [("Second", 1), ("First", 2)]
    assert all(item["rank_quiz_count"] == 1 for item in items)


def test_review_ranking_json_rejects_when_items_remain(tmp_path):
    db_path = tmp_path / "bucket.sqlite"
    assert invoke(db_path, "add", "First").exit_code == 0
    assert runner.invoke(app, ["--db", str(db_path), "review", "--ranking", "--limit", "1"]).exit_code == 0
    assert invoke(db_path, "add", "Second").exit_code == 0

    result = invoke(db_path, "review", "--ranking")

    assert result.exit_code == 3
    assert "rank-next/rank-answer" in result.output


def test_review_ranking_json_rejects_before_any_mutation(tmp_path):
    db_path = tmp_path / "bucket.sqlite"
    assert invoke(db_path, "add", "First").exit_code == 0
    assert invoke(db_path, "add", "Second").exit_code == 0

    result = invoke(db_path, "review", "--ranking")
    assert result.exit_code == 3
    assert "rank-next/rank-answer" in result.output

    result = invoke(db_path, "list", "--all", "--ranked")
    items = json.loads(result.output)
    assert all(item["rank"] is None for item in items)


def test_rank_next_and_rank_answer_json_flow(tmp_path):
    db_path = tmp_path / "bucket.sqlite"
    assert invoke(db_path, "add", "First", "--tag", "base").exit_code == 0
    assert invoke(db_path, "rank-next").exit_code == 0
    assert invoke(db_path, "add", "Second", "--tag", "new").exit_code == 0

    result = invoke(db_path, "rank-next", "--no-randomize")
    assert result.exit_code == 0, result.output
    step = json.loads(result.output)
    assert step["status"] == "comparison"
    assert step["candidate"]["title"] == "Second"
    assert step["candidate"]["tags"] == ["new"]
    assert step["pivot"]["title"] == "First"
    assert step["pivot"]["tags"] == ["base"]

    result = invoke(
        db_path,
        "rank-answer",
        "--candidate",
        str(step["candidate"]["id"]),
        "--pivot",
        str(step["pivot"]["id"]),
        "--winner",
        "candidate",
    )
    assert result.exit_code == 0, result.output
    answer = json.loads(result.output)
    assert answer["status"] == "ranked"
    assert answer["item"]["title"] == "Second"
    assert answer["item"]["rank"] == 1



def test_rank_next_rejects_pending_session_with_different_filters(tmp_path):
    db_path = tmp_path / "bucket.sqlite"
    assert invoke(db_path, "add", "First", "--horizon", "soon").exit_code == 0
    assert invoke(db_path, "rank-next", "--horizon", "soon").exit_code == 0
    assert invoke(db_path, "add", "Second", "--horizon", "soon").exit_code == 0
    assert invoke(db_path, "rank-next", "--horizon", "soon", "--no-randomize").exit_code == 0

    result = invoke(db_path, "rank-next", "--horizon", "now")

    assert result.exit_code == 1
    assert "different filters" in result.output



def test_rank_answer_rejects_stale_candidate_waiting(tmp_path):
    db_path = tmp_path / "bucket.sqlite"
    assert invoke(db_path, "add", "First").exit_code == 0
    assert invoke(db_path, "rank-next").exit_code == 0
    assert invoke(db_path, "add", "Second").exit_code == 0
    step = json.loads(invoke(db_path, "rank-next", "--no-randomize").output)

    # Make candidate ineligible by changing horizon to waiting
    assert invoke(db_path, "edit", str(step["candidate"]["id"]), "--horizon", "waiting").exit_code == 0

    result = invoke(
        db_path,
        "rank-answer",
        "--candidate",
        str(step["candidate"]["id"]),
        "--pivot",
        str(step["pivot"]["id"]),
        "--winner",
        "candidate",
    )

    assert result.exit_code == 3
    assert "no longer eligible" in result.output.lower()
    assert "run rank-next again" in result.output.lower()

    # Session should be deleted so rank-next can proceed cleanly
    result = invoke(db_path, "rank-next", "--no-randomize")
    assert result.exit_code == 0, result.output
    step2 = json.loads(result.output)
    assert step2["status"] in ("comparison", "empty")
    if step2["status"] == "comparison":
        assert step2["candidate"]["id"] != step["candidate"]["id"]


def test_rank_answer_skip_with_stale_candidate_returns_skipped(tmp_path):
    db_path = tmp_path / "bucket.sqlite"
    assert invoke(db_path, "add", "First").exit_code == 0
    assert invoke(db_path, "rank-next").exit_code == 0
    assert invoke(db_path, "add", "Second").exit_code == 0
    step = json.loads(invoke(db_path, "rank-next", "--no-randomize").output)

    # Make candidate ineligible by changing horizon to waiting
    assert invoke(db_path, "edit", str(step["candidate"]["id"]), "--horizon", "waiting").exit_code == 0

    result = invoke(
        db_path,
        "rank-answer",
        "--candidate",
        str(step["candidate"]["id"]),
        "--pivot",
        str(step["pivot"]["id"]),
        "--winner",
        "skip",
    )

    assert result.exit_code == 0, result.output
    answer = json.loads(result.output)
    assert answer["status"] == "skipped"
    assert answer["candidate"]["id"] == step["candidate"]["id"]
    assert answer["pivot"]["id"] == step["pivot"]["id"]

    # Session should be deleted
    result = invoke(db_path, "rank-next", "--no-randomize")
    assert result.exit_code == 0, result.output
    step2 = json.loads(result.output)
    assert step2["status"] in ("comparison", "empty")


def test_rank_answer_rejects_stale_candidate_completed(tmp_path):
    db_path = tmp_path / "bucket.sqlite"
    assert invoke(db_path, "add", "First").exit_code == 0
    assert invoke(db_path, "rank-next").exit_code == 0
    assert invoke(db_path, "add", "Second").exit_code == 0
    step = json.loads(invoke(db_path, "rank-next", "--no-randomize").output)

    assert invoke(db_path, "done", str(step["candidate"]["id"])).exit_code == 0

    result = invoke(
        db_path,
        "rank-answer",
        "--candidate",
        str(step["candidate"]["id"]),
        "--pivot",
        str(step["pivot"]["id"]),
        "--winner",
        "candidate",
    )

    assert result.exit_code == 3
    assert "no longer eligible" in result.output.lower()


def test_rank_answer_rejects_stale_candidate_blocked(tmp_path):
    db_path = tmp_path / "bucket.sqlite"
    assert invoke(db_path, "add", "Blocker").exit_code == 0
    assert invoke(db_path, "rank-next").exit_code == 0  # auto-ranks Blocker deterministically
    assert invoke(db_path, "add", "First").exit_code == 0
    assert invoke(db_path, "rank-next").exit_code == 0  # creates session with First as candidate
    assert invoke(db_path, "add", "Second").exit_code == 0
    step = json.loads(invoke(db_path, "rank-next", "--no-randomize").output)

    # Blocker was auto-ranked first, so its id is 1 and it is not the candidate
    assert step["candidate"]["id"] != 1
    assert invoke(db_path, "block", str(step["candidate"]["id"]), "--by", "1").exit_code == 0

    result = invoke(
        db_path,
        "rank-answer",
        "--candidate",
        str(step["candidate"]["id"]),
        "--pivot",
        str(step["pivot"]["id"]),
        "--winner",
        "candidate",
    )

    assert result.exit_code == 3
    assert "no longer eligible" in result.output.lower()


def test_rank_answer_allows_stale_when_all_flag_used(tmp_path):
    db_path = tmp_path / "bucket.sqlite"
    assert invoke(db_path, "add", "First").exit_code == 0
    assert invoke(db_path, "rank-next", "--all").exit_code == 0
    assert invoke(db_path, "add", "Second").exit_code == 0
    step = json.loads(invoke(db_path, "rank-next", "--all", "--no-randomize").output)

    # Make candidate ineligible under normal filters
    assert invoke(db_path, "done", str(step["candidate"]["id"])).exit_code == 0

    result = invoke(
        db_path,
        "rank-answer",
        "--candidate",
        str(step["candidate"]["id"]),
        "--pivot",
        str(step["pivot"]["id"]),
        "--winner",
        "candidate",
    )

    assert result.exit_code == 0, result.output
    answer = json.loads(result.output)
    assert answer["status"] == "ranked"


def test_rank_next_cleans_up_stale_session(tmp_path):
    db_path = tmp_path / "bucket.sqlite"
    assert invoke(db_path, "add", "First").exit_code == 0
    assert invoke(db_path, "rank-next").exit_code == 0
    assert invoke(db_path, "add", "Second").exit_code == 0
    step = json.loads(invoke(db_path, "rank-next", "--no-randomize").output)

    # Make candidate ineligible
    assert invoke(db_path, "edit", str(step["candidate"]["id"]), "--horizon", "waiting").exit_code == 0

    # rank-next should detect the stale session, delete it, and proceed cleanly
    result = invoke(db_path, "rank-next", "--no-randomize")
    assert result.exit_code == 0, result.output
    step2 = json.loads(result.output)
    assert step2["status"] in ("comparison", "empty")
    if step2["status"] == "comparison":
        assert step2["candidate"]["id"] != step["candidate"]["id"]


def test_rank_answer_handles_missing_session_pivot_cleanly(tmp_path):
    db_path = tmp_path / "bucket.sqlite"
    assert invoke(db_path, "add", "First").exit_code == 0
    assert invoke(db_path, "rank-next").exit_code == 0
    assert invoke(db_path, "add", "Second").exit_code == 0
    step = json.loads(invoke(db_path, "rank-next", "--no-randomize").output)

    conn = db.connect(db_path)
    try:
        with conn:
            conn.execute("UPDATE ranking_sessions SET pivot_id = NULL")
    finally:
        conn.close()

    result = invoke(
        db_path,
        "rank-answer",
        "--candidate",
        str(step["candidate"]["id"]),
        "--pivot",
        str(step["pivot"]["id"]),
        "--winner",
        "candidate",
    )

    assert result.exit_code == 3
    assert "pivot mismatch" in result.output



def test_review_ranking_skip_does_not_increment_counts(tmp_path):
    db_path = tmp_path / "bucket.sqlite"
    assert invoke(db_path, "add", "First").exit_code == 0
    assert runner.invoke(app, ["--db", str(db_path), "review", "--ranking", "--limit", "1"]).exit_code == 0
    assert invoke(db_path, "add", "Second").exit_code == 0

    result = runner.invoke(app, ["--db", str(db_path), "review", "--ranking", "--no-randomize"], input="skip\n")

    assert result.exit_code == 0, result.output
    result = invoke(db_path, "list", "--all", "--ranked")
    items = json.loads(result.output)
    assert [(item["title"], item["rank"], item["rank_quiz_count"]) for item in items] == [
        ("First", 1, 0),
        ("Second", None, 0),
    ]


def test_review_ranking_until_all_ranked_stops_before_reranking(tmp_path):
    db_path = tmp_path / "bucket.sqlite"
    assert invoke(db_path, "add", "First").exit_code == 0
    assert invoke(db_path, "add", "Second").exit_code == 0
    assert invoke(db_path, "add", "Third").exit_code == 0

    result = runner.invoke(
        app,
        ["--db", str(db_path), "review", "--ranking", "--until-all-ranked", "--no-randomize"],
        input="2\n2\n",
    )

    assert result.exit_code == 0, result.output
    result = invoke(db_path, "list", "--all", "--ranked")
    items = json.loads(result.output)
    assert all(item["rank"] is not None for item in items)
    assert sorted(item["rank"] for item in items) == [1, 2, 3]
    assert sum(item["rank_quiz_count"] for item in items) == 4


def test_add_item_with_tags(tmp_path):
    db_path = tmp_path / "bucket.sqlite"
    result = invoke(db_path, "add", "Visit Japan", "--tag", "travel", "--tag", "asia")
    assert result.exit_code == 0, result.output
    created = json.loads(result.output)
    assert created["tags"] == ["asia", "travel"]


def test_tag_add_and_remove(tmp_path):
    db_path = tmp_path / "bucket.sqlite"
    assert invoke(db_path, "add", "Test item").exit_code == 0

    result = invoke(db_path, "tag", "add", "1", "fun")
    assert result.exit_code == 0, result.output
    item = json.loads(result.output)
    assert item["tags"] == ["fun"]

    result = invoke(db_path, "tag", "remove", "1", "fun")
    assert result.exit_code == 0, result.output
    item = json.loads(result.output)
    assert item["tags"] == []


def test_tags_list(tmp_path):
    db_path = tmp_path / "bucket.sqlite"
    assert invoke(db_path, "add", "A", "--tag", "adventure").exit_code == 0
    assert invoke(db_path, "add", "B", "--tag", "adventure").exit_code == 0
    assert invoke(db_path, "add", "C", "--tag", "travel").exit_code == 0

    result = invoke(db_path, "tags")
    assert result.exit_code == 0, result.output
    tags = json.loads(result.output)
    by_name = {t["name"]: t["item_count"] for t in tags}
    assert by_name == {"adventure": 2, "travel": 1}


def test_list_filtered_by_tag(tmp_path):
    db_path = tmp_path / "bucket.sqlite"
    assert invoke(db_path, "add", "A", "--tag", "fun").exit_code == 0
    assert invoke(db_path, "add", "B").exit_code == 0

    result = invoke(db_path, "list", "--all", "--tag", "fun")
    assert result.exit_code == 0, result.output
    items = json.loads(result.output)
    assert [item["title"] for item in items] == ["A"]


def test_search_command(tmp_path):
    db_path = tmp_path / "bucket.sqlite"
    assert invoke(db_path, "add", "Visit Japan", "--desc", "Tokyo trip").exit_code == 0
    assert invoke(db_path, "add", "Hike Alps", "--desc", "Swiss mountains").exit_code == 0

    result = invoke(db_path, "search", "tokyo")
    assert result.exit_code == 0, result.output
    items = json.loads(result.output)
    assert [item["title"] for item in items] == ["Visit Japan"]

    result = invoke(db_path, "search", "swiss")
    assert result.exit_code == 0, result.output
    items = json.loads(result.output)
    assert [item["title"] for item in items] == ["Hike Alps"]

    result = invoke(db_path, "search", "xyz")
    assert result.exit_code == 0, result.output
    items = json.loads(result.output)
    assert items == []


def test_note_add_and_show(tmp_path):
    db_path = tmp_path / "bucket.sqlite"
    assert invoke(db_path, "add", "Visit Japan").exit_code == 0

    result = invoke(db_path, "note", "add", "1", "Check", "visa", "requirements")
    assert result.exit_code == 0, result.output
    note = json.loads(result.output)
    assert note["item_id"] == 1
    assert note["body"] == "Check visa requirements"

    result = invoke(db_path, "note", "add", "1", "Book", "flights")
    assert result.exit_code == 0

    result = invoke(db_path, "show", "1")
    assert result.exit_code == 0, result.output


def test_note_show_includes_notes_in_json(tmp_path):
    db_path = tmp_path / "bucket.sqlite"
    assert invoke(db_path, "add", "Visit Japan").exit_code == 0
    assert invoke(db_path, "note", "add", "1", "Check visa").exit_code == 0

    result = invoke(db_path, "show", "1")
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert len(payload["notes"]) == 1
    assert payload["notes"][0]["body"] == "Check visa"


def test_note_requires_item(tmp_path):
    result = invoke(tmp_path / "bucket.sqlite", "note", "add", "999", "Some text")
    assert result.exit_code == 2


def test_note_empty_body(tmp_path):
    db_path = tmp_path / "bucket.sqlite"
    assert invoke(db_path, "add", "Test").exit_code == 0

    result = invoke(db_path, "note", "add", "1", "")
    assert result.exit_code == 1


def test_note_delete(tmp_path):
    db_path = tmp_path / "bucket.sqlite"
    assert invoke(db_path, "add", "Test").exit_code == 0
    result = invoke(db_path, "note", "add", "1", "Delete me")
    assert result.exit_code == 0, result.output
    note = json.loads(result.output)

    result = invoke(db_path, "note", "delete", str(note["id"]))
    assert result.exit_code == 0, result.output
    deleted = json.loads(result.output)
    assert deleted["body"] == "Delete me"

    result = invoke(db_path, "show", "1")
    payload = json.loads(result.output)
    assert payload["notes"] == []


def test_note_delete_not_found(tmp_path):
    result = invoke(tmp_path / "bucket.sqlite", "note", "delete", "999")
    assert result.exit_code == 2


def test_note_backup_restore_round_trip(tmp_path):
    source_db = tmp_path / "source.sqlite"
    restored_db = tmp_path / "restored.sqlite"
    backup_file = tmp_path / "backup.json"

    assert invoke(source_db, "add", "Visit Japan").exit_code == 0
    assert invoke(source_db, "note", "add", "1", "Check visa").exit_code == 0
    assert invoke(source_db, "backup", "--dest", str(backup_file)).exit_code == 0

    result = invoke(restored_db, "restore", str(backup_file))
    assert result.exit_code == 0, result.output
    restore_result = json.loads(result.output)
    assert restore_result["notes"] == 1

    # verify the note was restored by checking human show output
    result = runner.invoke(app, ["--db", str(restored_db), "show", "1"])
    assert result.exit_code == 0, result.output
    assert "Check visa" in result.output


def test_tag_add_not_found(tmp_path):
    result = invoke(tmp_path / "bucket.sqlite", "tag", "add", "999", "fun")
    assert result.exit_code == 2


def test_block_and_unblock(tmp_path):
    db_path = tmp_path / "bucket.sqlite"
    assert invoke(db_path, "add", "Get passport").exit_code == 0
    assert invoke(db_path, "add", "Travel to Japan").exit_code == 0

    result = invoke(db_path, "block", "2", "--by", "1")
    assert result.exit_code == 0, result.output
    item = json.loads(result.output)
    assert item["blocked_by"] == 1
    assert item["horizon"] == "waiting"

    result = invoke(db_path, "unblock", "2")
    assert result.exit_code == 0, result.output
    item = json.loads(result.output)
    assert item["blocked_by"] is None
    # unblock does not restore the original horizon; user edits manually
    assert item["horizon"] == "waiting"


def test_block_missing_item(tmp_path):
    result = invoke(tmp_path / "bucket.sqlite", "block", "999", "--by", "1")
    assert result.exit_code == 2


def test_block_missing_blocker(tmp_path):
    db_path = tmp_path / "bucket.sqlite"
    assert invoke(db_path, "add", "Travel to Japan").exit_code == 0

    result = invoke(db_path, "block", "1", "--by", "999")
    assert result.exit_code == 2
    assert "blocker" in result.output.lower()


def test_block_circular_dependency(tmp_path):
    db_path = tmp_path / "bucket.sqlite"
    assert invoke(db_path, "add", "A").exit_code == 0
    assert invoke(db_path, "add", "B").exit_code == 0
    assert invoke(db_path, "add", "C").exit_code == 0
    assert invoke(db_path, "block", "2", "--by", "1").exit_code == 0
    assert invoke(db_path, "block", "3", "--by", "2").exit_code == 0

    result = invoke(db_path, "block", "1", "--by", "3")
    assert result.exit_code == 3
    assert "circular" in result.output.lower()


def test_stats_json_contract(tmp_path):
    db_path = tmp_path / "bucket.sqlite"
    assert invoke(db_path, "add", "A", "--horizon", "now").exit_code == 0
    assert invoke(db_path, "add", "B", "--horizon", "soon").exit_code == 0
    assert invoke(db_path, "add", "C", "--horizon", "later").exit_code == 0
    assert invoke(db_path, "done", "1").exit_code == 0

    result = invoke(db_path, "stats")
    assert result.exit_code == 0, result.output
    stats = json.loads(result.output)
    assert stats["total"] == 3
    assert stats["by_status"]["completed"] == 1
    assert stats["by_status"]["active"] == 2
    assert stats["by_horizon"]["now"] == 1
    assert stats["by_horizon"]["soon"] == 1
    assert stats["by_horizon"]["later"] == 1
    assert abs(stats["completion_rate"] - 1 / 3) < 1e-4
    assert stats["ranked"] == 0
    assert stats["unranked"] == 3
    assert stats["blocked"] == 0
    assert stats["actionable_items"] == 2
    assert stats["ranked_actionable"] == 0
    assert stats["unranked_actionable"] == 2
    assert stats["waiting_items"] == 0
    assert stats["completed_items"] == 1
    assert stats["no_longer_me_items"] == 0
    assert stats["by_tag"] == []


def test_stats_with_tags_and_waiting(tmp_path):
    db_path = tmp_path / "bucket.sqlite"
    assert invoke(db_path, "add", "Get passport").exit_code == 0
    assert invoke(db_path, "add", "Travel to Japan", "--tag", "travel").exit_code == 0
    assert invoke(db_path, "block", "2", "--by", "1").exit_code == 0

    result = invoke(db_path, "stats")
    assert result.exit_code == 0, result.output
    stats = json.loads(result.output)
    assert stats["total"] == 2
    assert stats["blocked"] == 1
    assert stats["waiting_items"] == 1
    assert stats["actionable_items"] == 1
    assert stats["unranked_actionable"] == 1
    assert stats["by_horizon"]["waiting"] == 1
    by_tag = {t["name"]: t["count"] for t in stats["by_tag"]}
    assert by_tag == {"travel": 1}


def test_stats_empty_database(tmp_path):
    db_path = tmp_path / "bucket.sqlite"
    result = invoke(db_path, "stats")
    assert result.exit_code == 0, result.output
    stats = json.loads(result.output)
    assert stats["total"] == 0
    assert stats["total_items"] == 0
    assert stats["actionable_items"] == 0
    assert stats["unranked_actionable"] == 0
    assert stats["completion_rate"] == 0.0


def test_block_self(tmp_path):
    db_path = tmp_path / "bucket.sqlite"
    assert invoke(db_path, "add", "A").exit_code == 0

    result = invoke(db_path, "block", "1", "--by", "1")
    assert result.exit_code == 3
    assert "itself" in result.output.lower()


def test_done_waiting_requires_force(tmp_path):
    db_path = tmp_path / "bucket.sqlite"
    assert invoke(db_path, "add", "Get passport").exit_code == 0
    assert invoke(db_path, "add", "Travel to Japan").exit_code == 0
    assert invoke(db_path, "block", "2", "--by", "1").exit_code == 0

    result = invoke(db_path, "done", "2")
    assert result.exit_code == 1
    assert "waiting" in result.output.lower()

    result = invoke(db_path, "done", "2", "--force")
    assert result.exit_code == 0, result.output
    item = json.loads(result.output)
    assert item["status"] == "completed"


def test_review_without_ranking_rejects_json(tmp_path):
    db_path = tmp_path / "bucket.sqlite"
    assert invoke(db_path, "add", "A", "--horizon", "later").exit_code == 0

    result = runner.invoke(app, ["--db", str(db_path), "--json", "review"])
    assert result.exit_code == 1
    assert "does not support --json" in result.output.lower()


def test_review_gtd_mutations_persist(tmp_path):
    db_path = tmp_path / "bucket.sqlite"
    assert invoke(db_path, "add", "A", "--horizon", "later").exit_code == 0
    assert invoke(db_path, "add", "B", "--horizon", "soon").exit_code == 0

    from unittest.mock import patch

    prompts = iter(["n", "x", "quit"])
    with patch("bucket.commands.review.typer.prompt", side_effect=lambda _: next(prompts)):
        result = runner.invoke(app, ["--db", str(db_path), "review"])

    assert result.exit_code == 0, result.output
    assert "Reviewed 2 item(s)" in result.output

    # Verify mutations persisted
    # Review order is soon (B) first, then later (A)
    a = json.loads(invoke(db_path, "show", "1").output)
    b = json.loads(invoke(db_path, "show", "2").output)
    assert b["horizon"] == "now"      # B got "n" -> now
    assert a["status"] == "no_longer_me"   # A got "a" -> no-longer-me


def test_completion_show_bash():
    result = runner.invoke(app, ["completion", "show", "--shell", "bash"])
    assert result.exit_code == 0, result.output
    assert "_bucket_completion()" in result.output


def test_completion_show_zsh_json():
    result = runner.invoke(app, ["--json", "completion", "show", "--shell", "zsh"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["shell"] == "zsh"
    assert "#compdef bucket" in data["script"]


def test_completion_show_fish():
    result = runner.invoke(app, ["completion", "show", "--shell", "fish"])
    assert result.exit_code == 0, result.output
    assert "complete --command bucket" in result.output


def test_completion_install_unknown_shell():
    result = runner.invoke(app, ["completion", "install", "--shell", "unknown"])
    assert result.exit_code == 1
    assert "unknown" in result.output.lower()
    assert "not supported" in result.output.lower()


def test_completion_show_unknown_shell():
    result = runner.invoke(app, ["completion", "show", "--shell", "unknown"])
    assert result.exit_code == 1
    assert "unknown" in result.output.lower()
    assert "not supported" in result.output.lower()
