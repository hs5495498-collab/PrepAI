import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi.testclient import TestClient

import auth
import db
from main import app


@pytest.fixture
def client():
    # A fresh TestClient per test means a fresh, empty cookie jar - no
    # session leaks between tests even though the isolated_database
    # fixture already gives each test its own database file too.
    return TestClient(app)


def register(client, email="alice@example.com", password="correct-horse-1"):
    return client.post("/api/auth/register", json={"email": email, "password": password})


def login(client, email="alice@example.com", password="correct-horse-1"):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def csrf_headers(client):
    token = client.cookies.get(auth.CSRF_COOKIE_NAME)
    return {"X-CSRF-Token": token} if token else {}


def create_interview(client, **headers):
    return client.post(
        "/api/interviews",
        json={"role": "Engineer", "category": "technical", "difficulty": "easy", "question_count": 2},
        headers=headers,
    )


# ---------- Registration ----------

def test_successful_registration(client):
    res = register(client)
    assert res.status_code == 201
    body = res.json()
    assert body["email"] == "alice@example.com"
    assert "id" in body and "created_at" in body
    assert "password" not in body and "password_hash" not in body
    # Registration auto-logs-in: the session cookie should already be set.
    assert client.cookies.get(auth.SESSION_COOKIE_NAME) is not None


def test_registration_normalizes_email_case_and_whitespace(client):
    register(client, email="  Alice@Example.COM  ")
    conn = db.connect()
    try:
        row = conn.execute("SELECT email FROM users").fetchone()
        assert row["email"] == "alice@example.com"
    finally:
        conn.close()


def test_duplicate_email_rejected(client):
    register(client)
    second_client = TestClient(app)
    res = register(second_client)
    assert res.status_code == 409


def test_duplicate_email_rejected_case_insensitive(client):
    register(client, email="bob@example.com")
    second_client = TestClient(app)
    res = register(second_client, email="BOB@EXAMPLE.COM")
    assert res.status_code == 409


def test_invalid_email_rejected(client):
    res = register(client, email="not-an-email")
    assert res.status_code == 422


def test_short_password_rejected(client):
    res = register(client, email="shortpw@example.com", password="short")
    assert res.status_code == 422


def test_password_hash_never_returned_or_stored_in_plain_text():
    client = TestClient(app)
    register(client, email="hashcheck@example.com", password="correct-horse-1")
    conn = db.connect()
    try:
        row = conn.execute("SELECT password_hash FROM users WHERE email = ?", ("hashcheck@example.com",)).fetchone()
        assert row["password_hash"] != "correct-horse-1"
        assert row["password_hash"].startswith("$argon2id$")
    finally:
        conn.close()


# ---------- Login / logout ----------

def test_successful_login(client):
    register(client)
    fresh = TestClient(app)
    res = login(fresh)
    assert res.status_code == 200
    assert res.json()["email"] == "alice@example.com"
    assert fresh.cookies.get(auth.SESSION_COOKIE_NAME) is not None


def test_incorrect_password_rejected(client):
    register(client)
    fresh = TestClient(app)
    res = login(fresh, password="wrong-password")
    assert res.status_code == 401
    assert fresh.cookies.get(auth.SESSION_COOKIE_NAME) is None


def test_login_with_unknown_account_rejected(client):
    res = login(client, email="nobody@example.com", password="whatever1")
    assert res.status_code == 401


def test_get_me_while_authenticated(client):
    register(client)
    res = client.get("/api/auth/me")
    assert res.status_code == 200
    assert res.json()["email"] == "alice@example.com"


def test_get_me_without_authentication_rejected(client):
    res = client.get("/api/auth/me")
    assert res.status_code == 401


def test_logout_invalidates_the_session(client):
    register(client)
    assert client.get("/api/auth/me").status_code == 200

    res = client.post("/api/auth/logout", headers=csrf_headers(client))
    assert res.status_code == 200

    # The exact same (now-deleted) session token must no longer work, even
    # if a client somehow still had it cached.
    res2 = client.get("/api/auth/me")
    assert res2.status_code == 401


def test_logout_without_csrf_header_rejected(client):
    register(client)
    res = client.post("/api/auth/logout")  # no X-CSRF-Token header
    assert res.status_code == 403
    # The session must still be valid - logout must not have happened.
    assert client.get("/api/auth/me").status_code == 200


def test_logout_without_any_session_is_a_safe_no_op():
    client = TestClient(app)
    res = client.post("/api/auth/logout")
    assert res.status_code == 200


def test_expired_session_is_rejected(client, monkeypatch):
    register(client)
    monkeypatch.setattr(auth, "DEFAULT_SESSION_LIFETIME_DAYS", -1)
    # Force a brand-new, already-expired session rather than relying on the
    # one register() already set up.
    user = auth.authenticate("alice@example.com", "correct-horse-1")
    expired_session = auth.create_session_for_user(user["id"])
    client.cookies.set(auth.SESSION_COOKIE_NAME, expired_session["token"])
    res = client.get("/api/auth/me")
    assert res.status_code == 401


# ---------- Ownership isolation ----------

def test_owned_interview_is_readable_by_its_owner(client):
    register(client)
    created = create_interview(client, **csrf_headers(client)).json()
    res = client.get(f"/api/interviews/{created['session_id']}")
    assert res.status_code == 200


def test_user_a_cannot_read_user_bs_interview():
    client_a = TestClient(app)
    register(client_a, email="usera@example.com")
    created = create_interview(client_a, **csrf_headers(client_a)).json()
    session_id = created["session_id"]

    client_b = TestClient(app)
    register(client_b, email="userb@example.com")
    res = client_b.get(f"/api/interviews/{session_id}")
    assert res.status_code == 404


def test_user_a_cannot_answer_user_bs_interview():
    client_a = TestClient(app)
    register(client_a, email="usera2@example.com")
    created = create_interview(client_a, **csrf_headers(client_a)).json()
    session_id, question_id = created["session_id"], created["questions"][0]["id"]

    client_b = TestClient(app)
    register(client_b, email="userb2@example.com")
    res = client_b.post(
        f"/api/interviews/{session_id}/answers",
        json={"question_id": question_id, "answer": "intrusion attempt"},
        headers=csrf_headers(client_b),
    )
    assert res.status_code == 404

    # And the real owner's data must be completely untouched.
    reloaded = client_a.get(f"/api/interviews/{session_id}").json()
    assert reloaded["questions"][0]["answer"] is None


def test_user_a_cannot_complete_user_bs_interview():
    client_a = TestClient(app)
    register(client_a, email="usera3@example.com")
    created = create_interview(client_a, **csrf_headers(client_a)).json()
    session_id = created["session_id"]

    client_b = TestClient(app)
    register(client_b, email="userb3@example.com")
    res = client_b.post(f"/api/interviews/{session_id}/complete", headers=csrf_headers(client_b))
    assert res.status_code == 404

    reloaded = client_a.get(f"/api/interviews/{session_id}").json()
    assert reloaded["status"] == "in_progress"


def test_anonymous_request_cannot_read_someone_elses_owned_interview():
    owner = TestClient(app)
    register(owner, email="owner@example.com")
    created = create_interview(owner, **csrf_headers(owner)).json()

    anonymous = TestClient(app)
    res = anonymous.get(f"/api/interviews/{created['session_id']}")
    assert res.status_code == 404


def test_existing_unowned_interview_stays_open_like_before():
    # No authentication at all - exactly the Phase 4-6 anonymous/offline flow.
    anon = TestClient(app)
    created = create_interview(anon).json()
    assert created["session_id"]

    conn = db.connect()
    try:
        row = conn.execute("SELECT user_id FROM interviews WHERE id = ?", (created["session_id"],)).fetchone()
        assert row["user_id"] is None
    finally:
        conn.close()

    # Anyone (including a different logged-in user) can still read/use it,
    # unchanged from Phase 6 behavior.
    someone = TestClient(app)
    register(someone, email="someone@example.com")
    res = someone.get(f"/api/interviews/{created['session_id']}")
    assert res.status_code == 200


def test_create_interview_without_csrf_header_rejected_when_authenticated(client):
    register(client)
    res = client.post(
        "/api/interviews",
        json={"role": "Engineer", "category": "technical", "difficulty": "easy", "question_count": 2},
    )
    assert res.status_code == 403


def test_create_interview_anonymous_does_not_require_csrf():
    anon = TestClient(app)
    res = create_interview(anon)
    assert res.status_code == 201
