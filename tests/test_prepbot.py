from types import SimpleNamespace

from prepify.config import Settings
from prepify.prepbot.service import GeminiPrepBotService
from prepify.schemas import PrepBotChatRequest


class FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "steps": [{
                "type": "model_output",
                "content": [{"type": "text", "text": "Trace the base case first."}],
            }]
        }


class FakeClient:
    def __init__(self):
        self.request = None

    def post(self, endpoint, *, headers, json):
        self.request = SimpleNamespace(endpoint=endpoint, headers=headers, json=json)
        return FakeResponse()


def test_prep_bot_uses_stateless_interactions_request() -> None:
    client = FakeClient()
    service = GeminiPrepBotService(
        Settings(gemini_api_key="server-secret", gemini_model_name="gemini-test"),
        client=client,
    )

    result = service.chat(PrepBotChatRequest(message="Help with recursion"))

    assert result.answer == "Trace the base case first."
    assert result.stored is False
    assert client.request.endpoint.endswith("/interactions")
    assert client.request.headers["x-goog-api-key"] == "server-secret"
    assert client.request.json["store"] is False
