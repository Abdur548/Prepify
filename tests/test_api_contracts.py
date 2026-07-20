from fastapi.testclient import TestClient

import prepify.api.main as api_main
from prepify.api.main import app
from prepify.phase1.schemas import Paper4GradeResponse
from prepify.schemas import PrepBotChatResponse


client = TestClient(app)


def test_health_route_does_not_require_models_or_database() -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["service"] == "prepify-9618"


def test_topics_are_topic_tags_not_paper_numbers() -> None:
    response = client.get("/v1/topics")
    assert response.status_code == 200
    tags = {item["topic_tag"] for item in response.json()}
    assert "Recursion" in tags
    assert "Protocols" in tags
    assert "Paper 3" not in tags


def test_check_answer_request_is_rejected_without_answer() -> None:
    response = client.post(
        "/v1/questions/not-used/explain",
        json={"mode": "check_answer"},
    )
    assert response.status_code == 422


def test_phase1_endpoint_labels_unvalidated_result_provisional(monkeypatch) -> None:
    class FakeGrader:
        def grade(self, question_id, request):
            return Paper4GradeResponse(
                attempt_id="attempt-1",
                question_id=question_id,
                status="completed",
                marks_awarded=1,
                marks_available=2,
                certified=False,
                validation_status="blocked",
                launch_gate="Provisional only: held-out validation is required.",
                test_results=[
                    {
                        "test_case_id": "case-1",
                        "name": "example",
                        "verdict": "passed",
                        "marks_awarded": 1,
                        "marks_available": 1,
                        "exit_code": 0,
                        "feedback": "Matched.",
                    }
                ],
            )

    monkeypatch.setattr(api_main, "build_paper4_grader", lambda session: FakeGrader())
    response = client.post(
        "/v1/phase1/questions/q1/grade-code",
        json={"language": "python", "source_code": "print(4)"},
    )

    assert response.status_code == 200
    assert response.json()["marks_awarded"] == 1
    assert response.json()["certified"] is False
    assert response.json()["validation_status"] == "blocked"


def test_prep_bot_endpoint_uses_server_side_service(monkeypatch) -> None:
    class FakePrepBot:
        def chat(self, request):
            assert request.message == "Explain recursion"
            return PrepBotChatResponse(
                answer="Start with the base case, then trace one recursive call.",
                model="gemini-test",
                stored=False,
            )

    monkeypatch.setattr(api_main, "build_prep_bot_service", lambda: FakePrepBot())
    response = client.post(
        "/v1/prep-bot/chat",
        json={"message": "Explain recursion", "history": []},
    )

    assert response.status_code == 200
    assert response.json()["stored"] is False
    assert response.json()["model"] == "gemini-test"
