import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def create_interview(role="Software Engineer", category="technical", difficulty="medium", question_count=3):
    return client.post(
        "/api/interviews",
        json={"role": role, "category": category, "difficulty": difficulty, "question_count": question_count},
    )


def test_health_endpoint():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_create_interview_success():
    res = create_interview()
    assert res.status_code == 201
    body = res.json()
    assert body["status"] == "in_progress"
    assert body["role"] == "Software Engineer"
    assert body["category"] == "technical"
    assert body["total_questions"] == 3
    assert len(body["questions"]) == 3
    assert body["answered_count"] == 0
    assert all(q["answer"] is None for q in body["questions"])


def test_create_interview_rejects_invalid_category():
    res = client.post(
        "/api/interviews",
        json={"role": "Engineer", "category": "not-a-real-category", "difficulty": "medium", "question_count": 3},
    )
    assert res.status_code == 422


def test_get_session_success():
    created = create_interview().json()
    res = client.get(f"/api/interviews/{created['session_id']}")
    assert res.status_code == 200
    assert res.json()["session_id"] == created["session_id"]


def test_get_session_invalid_id():
    res = client.get("/api/interviews/does-not-exist")
    assert res.status_code == 404


def test_submit_answer_success():
    created = create_interview().json()
    session_id = created["session_id"]
    question_id = created["questions"][0]["id"]
    res = client.post(f"/api/interviews/{session_id}/answers", json={"question_id": question_id, "answer": "My answer"})
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "answer_recorded"
    assert body["answered_count"] == 1
    assert body["total_questions"] == 3

    follow_up = client.get(f"/api/interviews/{session_id}")
    stored = next(q for q in follow_up.json()["questions"] if q["id"] == question_id)
    assert stored["answer"] == "My answer"


def test_submit_blank_answer_rejected():
    created = create_interview().json()
    session_id = created["session_id"]
    question_id = created["questions"][0]["id"]
    res = client.post(f"/api/interviews/{session_id}/answers", json={"question_id": question_id, "answer": "   "})
    assert res.status_code == 422


def test_submit_answer_invalid_session():
    res = client.post("/api/interviews/does-not-exist/answers", json={"question_id": "q1", "answer": "hi"})
    assert res.status_code == 404


def test_submit_answer_invalid_question_id():
    created = create_interview().json()
    session_id = created["session_id"]
    res = client.post(f"/api/interviews/{session_id}/answers", json={"question_id": "not-a-real-question", "answer": "hi"})
    assert res.status_code == 404


def test_submit_duplicate_answer_rejected():
    created = create_interview().json()
    session_id = created["session_id"]
    question_id = created["questions"][0]["id"]
    first = client.post(f"/api/interviews/{session_id}/answers", json={"question_id": question_id, "answer": "first"})
    assert first.status_code == 200
    second = client.post(f"/api/interviews/{session_id}/answers", json={"question_id": question_id, "answer": "second"})
    assert second.status_code == 409


def test_complete_interview_success():
    created = create_interview(question_count=2).json()
    session_id = created["session_id"]
    for q in created["questions"]:
        client.post(f"/api/interviews/{session_id}/answers", json={"question_id": q["id"], "answer": "an answer"})

    res = client.post(f"/api/interviews/{session_id}/complete")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "completed"
    assert body["answered_count"] == 2
    assert all(q["answer"] == "an answer" for q in body["questions"])


def test_submit_answer_after_completion_rejected():
    created = create_interview(question_count=1).json()
    session_id = created["session_id"]
    question_id = created["questions"][0]["id"]
    client.post(f"/api/interviews/{session_id}/complete")

    res = client.post(f"/api/interviews/{session_id}/answers", json={"question_id": question_id, "answer": "too late"})
    assert res.status_code == 409


def test_complete_twice_rejected():
    created = create_interview(question_count=1).json()
    session_id = created["session_id"]
    first = client.post(f"/api/interviews/{session_id}/complete")
    assert first.status_code == 200
    second = client.post(f"/api/interviews/{session_id}/complete")
    assert second.status_code == 409


def test_complete_invalid_session():
    res = client.post("/api/interviews/does-not-exist/complete")
    assert res.status_code == 404
