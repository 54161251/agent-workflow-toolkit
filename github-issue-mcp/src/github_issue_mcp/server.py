"""MCP primitives for the GitHub issue workflow."""

from typing import Any

from mcp.server import MCPServer

from .config import Settings
from .github_client import GitHubClient, GitHubServiceError
from .security import (
    InputValidationError,
    validate_issue_text,
    validate_limit,
    validate_repository_part,
    validate_search_query,
)


# Decorator-based primitives follow the official MCP Python SDK tutorial:
# https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/get-started/first-steps.md
mcp = MCPServer("GitHub Issue Assistant", log_level="INFO")
client = GitHubClient(Settings.from_env_file().github_token)


def _error(code: str, message: str) -> dict[str, Any]:
    return {"ok": False, "error": {"code": code, "message": message}}


@mcp.tool()
def search_github_issues(
    owner: str, repository: str, query: str, limit: int = 5
) -> dict[str, Any]:
    """Search issues in one GitHub repository; returns at most 20 safe summaries."""
    try:
        safe_owner = validate_repository_part(owner, "owner")
        safe_repository = validate_repository_part(repository, "repository")
        safe_query = validate_search_query(query)
        safe_limit = validate_limit(limit)
        issues = client.search_issues(
            safe_owner, safe_repository, safe_query, safe_limit
        )
        return {"ok": True, "count": len(issues), "issues": issues}
    except InputValidationError as exc:
        return _error("invalid_input", str(exc))
    except GitHubServiceError as exc:
        return _error(exc.code, exc.safe_message)
    except Exception:
        return _error("internal_error", "The server could not complete the request.")


@mcp.tool()
def create_github_issue(
    owner: str,
    repository: str,
    title: str,
    body: str,
    confirm: bool = False,
) -> dict[str, Any]:
    """Preview or create a GitHub issue. Set confirm=true only after user approval."""
    try:
        safe_owner = validate_repository_part(owner, "owner")
        safe_repository = validate_repository_part(repository, "repository")
        safe_title = validate_issue_text(title, "title", 200)
        safe_body = validate_issue_text(body, "body", 10_000)
        if not confirm:
            return {
                "ok": True,
                "created": False,
                "preview": {
                    "repository": f"{safe_owner}/{safe_repository}",
                    "title": safe_title,
                    "body": safe_body,
                },
                "message": "Preview only. Ask the user to approve, then call with confirm=true.",
            }
        issue = client.create_issue(
            safe_owner, safe_repository, safe_title, safe_body
        )
        return {"ok": True, "created": True, "issue": issue}
    except InputValidationError as exc:
        return _error("invalid_input", str(exc))
    except GitHubServiceError as exc:
        return _error(exc.code, exc.safe_message)
    except Exception:
        return _error("internal_error", "The server could not complete the request.")


@mcp.prompt()
def triage_github_issue(issue_text: str) -> str:
    """Build a structured prompt for turning a report into an actionable issue."""
    safe_text = validate_issue_text(issue_text, "issue_text", 5_000)
    return (
        "Act as a software issue triage assistant. Analyze the report below. "
        "Return: (1) a concise title, (2) a Markdown body with Summary, "
        "Steps to Reproduce, Expected Behavior, Actual Behavior, and Acceptance "
        "Criteria, and (3) any missing information as questions. Do not invent facts. "
        "Do not create an issue until the user approves the preview.\n\n"
        f"REPORT:\n{safe_text}"
    )

