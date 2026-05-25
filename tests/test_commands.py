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
