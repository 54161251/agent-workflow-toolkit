import json

from github_issue_mcp.github_client import GitHubClient


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.payload).encode()


def test_create_issue_uses_auth_and_returns_safe_fields() -> None:
    observed = {}

    def opener(request, timeout):
        observed["authorization"] = request.headers["Authorization"]
        observed["method"] = request.method
        return FakeResponse(
            {
                "number": 42,
                "title": "Broken build",
                "state": "open",
                "html_url": "https://github.com/acme/demo/issues/42",
                "ignored_internal_field": "not returned",
            }
        )

    client = GitHubClient("test-token", opener=opener)
    result = client.create_issue("acme", "demo", "Broken build", "Details")

    assert observed == {"authorization": "Bearer test-token", "method": "POST"}
    assert result == {
        "number": 42,
        "title": "Broken build",
        "state": "open",
        "url": "https://github.com/acme/demo/issues/42",
    }

