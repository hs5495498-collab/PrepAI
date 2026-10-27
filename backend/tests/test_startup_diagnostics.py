"""Tests for the configuration-loading reliability fix and the new
startup diagnostic (main.py's env_file_path, _log_ai_feature_status,
lifespan). The actual AI-provider configuration logic itself
(AI_EVALUATION_ENABLED / OPENAI_API_KEY / OPENAI_MODEL loading,
is_configured()) is already covered by test_evaluation_provider.py's
test_not_configured_when_disabled/test_not_configured_when_key_missing
and ai_provider's equivalents - this file covers what's new: .env
loading no longer depends on the process's working directory, the
startup diagnostic reports the right thing for each configuration state
without ever printing the key, and the per-request error message is
actionable.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi.testclient import TestClient

import ai_provider
import evaluation_provider
import main
from main import app


@pytest.fixture
def client():
    return TestClient(app)


# ---------- .env loading is independent of the working directory ----------

def test_env_file_path_is_absolute_and_points_at_backend_env():
    path = main.env_file_path()
    assert path.is_absolute()
    assert path.name == ".env"
    assert path.parent == Path(main.__file__).resolve().parent


def test_env_file_path_is_unaffected_by_the_current_working_directory(monkeypatch, tmp_path):
    # The actual defect being fixed: load_dotenv() with no path argument
    # searches upward from the process's *current working directory* -
    # launching uvicorn from anywhere other than backend/ (e.g. the repo
    # root) would silently find no .env at all. env_file_path() must
    # resolve to the same absolute location regardless of cwd.
    before = main.env_file_path()
    monkeypatch.chdir(tmp_path)
    after = main.env_file_path()
    assert before == after
    assert after.is_absolute()


# ---------- Startup diagnostic: correct message, never leaks the key ----------

def test_diagnostic_reports_disabled_when_flag_is_false(monkeypatch, capsys):
    monkeypatch.setenv("AI_EVALUATION_ENABLED", "false")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    main._log_ai_feature_status("AI answer evaluation", "AI_EVALUATION_ENABLED", evaluation_provider)
    out = capsys.readouterr().out
    assert "AI answer evaluation" in out
    assert "disabled" in out
    assert "AI_EVALUATION_ENABLED" in out  # names the exact variable to set


def test_diagnostic_reports_flag_on_but_key_missing(monkeypatch, capsys):
    monkeypatch.setenv("AI_EVALUATION_ENABLED", "true")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    main._log_ai_feature_status("AI answer evaluation", "AI_EVALUATION_ENABLED", evaluation_provider)
    out = capsys.readouterr().out
    assert "OPENAI_API_KEY is missing" in out


def test_diagnostic_reports_enabled_with_model_when_fully_configured(monkeypatch, capsys):
    monkeypatch.setenv("AI_EVALUATION_ENABLED", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    main._log_ai_feature_status("AI answer evaluation", "AI_EVALUATION_ENABLED", evaluation_provider)
    out = capsys.readouterr().out
    assert "ENABLED" in out
    assert "model=" in out


def test_diagnostic_never_prints_the_api_key_value(monkeypatch, capsys):
    secret = "sk-this-exact-string-must-never-appear-in-output"
    monkeypatch.setenv("AI_EVALUATION_ENABLED", "true")
    monkeypatch.setenv("OPENAI_API_KEY", secret)
    main._log_ai_feature_status("AI answer evaluation", "AI_EVALUATION_ENABLED", evaluation_provider)
    main._log_ai_feature_status("AI question generation", "AI_QUESTIONS_ENABLED", ai_provider)
    out = capsys.readouterr().out
    assert secret not in out


def test_diagnostic_is_independent_per_feature(monkeypatch, capsys):
    # Enabling evaluation must never be reported as if it also enabled
    # question generation, or vice versa - the two flags stay independent.
    monkeypatch.setenv("AI_EVALUATION_ENABLED", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    monkeypatch.setenv("AI_QUESTIONS_ENABLED", "false")
    main._log_ai_feature_status("AI question generation", "AI_QUESTIONS_ENABLED", ai_provider)
    main._log_ai_feature_status("AI answer evaluation", "AI_EVALUATION_ENABLED", evaluation_provider)
    lines = capsys.readouterr().out.strip().splitlines()
    assert any("AI question generation" in l and "disabled" in l for l in lines)
    assert any("AI answer evaluation" in l and "ENABLED" in l for l in lines)


# ---------- The per-request error is actionable, not just "not configured" ----------

def test_evaluate_endpoint_error_is_actionable_when_not_configured(client):
    created = client.post(
        "/api/interviews",
        json={"role": "Tester", "category": "technical", "difficulty": "easy", "question_count": 1},
    ).json()
    session_id, question_id = created["session_id"], created["questions"][0]["id"]
    client.post(f"/api/interviews/{session_id}/answers", json={"question_id": question_id, "answer": "An answer."})

    res = client.post(f"/api/interviews/{session_id}/questions/{question_id}/evaluate")
    assert res.status_code == 503
    detail = res.json()["detail"]
    assert "not configured" in detail.lower()
    # Actionable: names the exact two settings and where they go, not just
    # that something is wrong.
    assert "AI_EVALUATION_ENABLED" in detail
    assert "OPENAI_API_KEY" in detail
    assert "backend/.env" in detail
