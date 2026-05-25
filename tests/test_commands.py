import json

from typer.testing import CliRunner

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
    assert schema["tables"]["items"]["horizon"] == ["now", "soon", "someday", "blocked"]
    assert "rank_quiz_count" in schema["tables"]["items"]


def test_backup_restore_round_trip(tmp_path):
    source_db = tmp_path / "source.sqlite"
    restored_db = tmp_path / "restored.sqlite"
    backup_file = tmp_path / "backup.json"

    assert invoke(source_db, "add", "Visit Japan", "--horizon", "soon", "--priority", "2").exit_code == 0
    assert invoke(source_db, "add", "Hike Grand Canyon", "--horizon", "now").exit_code == 0
    assert invoke(source_db, "start", "2").exit_code == 0
    assert invoke(source_db, "review", "--ranking").exit_code == 0

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
    backup_file.write_text('{"schema_version": 999, "items": [], "tags": [], "item_tags": []}')

    result = invoke(db_path, "restore", str(backup_file))

    assert result.exit_code == 1
    assert "newer schema version" in result.output


def test_review_ranking_inserts_unranked_item(tmp_path):
    db_path = tmp_path / "bucket.sqlite"
    assert invoke(db_path, "add", "First").exit_code == 0
    assert invoke(db_path, "review", "--ranking").exit_code == 0
    assert invoke(db_path, "add", "Second").exit_code == 0

    result = runner.invoke(app, ["--db", str(db_path), "review", "--ranking", "--no-randomize"], input="1\n")

    assert result.exit_code == 0, result.output
    result = invoke(db_path, "list", "--all", "--ranked")
    items = json.loads(result.output)
    assert [(item["title"], item["rank"]) for item in items] == [("Second", 1), ("First", 2)]
    assert all(item["rank_quiz_count"] == 1 for item in items)


def test_review_ranking_skip_does_not_increment_counts(tmp_path):
    db_path = tmp_path / "bucket.sqlite"
    assert invoke(db_path, "add", "First").exit_code == 0
    assert invoke(db_path, "review", "--ranking").exit_code == 0
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
    assert item["horizon"] == "blocked"

    result = invoke(db_path, "unblock", "2")
    assert result.exit_code == 0, result.output
    item = json.loads(result.output)
    assert item["blocked_by"] is None
    # unblock does not restore the original horizon; user edits manually
    assert item["horizon"] == "blocked"


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


def test_block_self(tmp_path):
    db_path = tmp_path / "bucket.sqlite"
    assert invoke(db_path, "add", "A").exit_code == 0

    result = invoke(db_path, "block", "1", "--by", "1")
    assert result.exit_code == 3
    assert "itself" in result.output.lower()


def test_done_blocked_requires_force(tmp_path):
    db_path = tmp_path / "bucket.sqlite"
    assert invoke(db_path, "add", "Get passport").exit_code == 0
    assert invoke(db_path, "add", "Travel to Japan").exit_code == 0
    assert invoke(db_path, "block", "2", "--by", "1").exit_code == 0

    result = invoke(db_path, "done", "2")
    assert result.exit_code == 1
    assert "blocked" in result.output.lower()

    result = invoke(db_path, "done", "2", "--force")
    assert result.exit_code == 0, result.output
    item = json.loads(result.output)
    assert item["status"] == "completed"
