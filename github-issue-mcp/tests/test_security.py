import pytest

from github_issue_mcp.security import (
    InputValidationError,
    validate_repository_part,
    validate_search_query,
)


def test_repository_path_injection_is_blocked() -> None:
    with pytest.raises(InputValidationError):
        validate_repository_part("demo/../../victim", "repository")


def test_search_scope_override_is_blocked() -> None:
    with pytest.raises(InputValidationError):
        validate_search_query("bug repo:other/private-repo")


def test_normal_inputs_are_accepted() -> None:
    assert validate_repository_part("python-sdk", "repository") == "python-sdk"
    assert validate_search_query("connection timeout") == "connection timeout"

