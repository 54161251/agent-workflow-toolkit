from io import BytesIO
from urllib.error import HTTPError

import pytest

from github_issue_mcp.github_client import GitHubClient, GitHubServiceError


def leaking_opener(request, timeout):
    secret = "github_pat_SUPER_SECRET"
    body = BytesIO(f'{{"message":"debug token={secret}"}}'.encode())
    raise HTTPError(request.full_url, 401, f"token={secret}", {}, body)


def test_upstream_secret_is_not_disclosed() -> None:
    client = GitHubClient("github_pat_SUPER_SECRET", opener=leaking_opener)

    with pytest.raises(GitHubServiceError) as captured:
        client.search_issues("octocat", "Hello-World", "bug", 5)

    visible_error = str(captured.value)
    assert captured.value.code == "authentication_failed"
    assert "SUPER_SECRET" not in visible_error
    assert "debug" not in visible_error
    assert "api.github.com" not in visible_error

