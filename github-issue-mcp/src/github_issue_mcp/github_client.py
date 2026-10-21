"""Small GitHub REST API client with deliberately safe errors."""

import json
import logging
from dataclasses import dataclass
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class GitHubServiceError(RuntimeError):
    """An error whose code and message are safe to return to an MCP client."""

    code: str
    safe_message: str

    def __str__(self) -> str:
        return self.safe_message


class GitHubClient:
    BASE_URL = "https://api.github.com"

    def __init__(
        self,
        token: str,
        opener: Callable[..., Any] = urlopen,
    ) -> None:
        self._token = token
        self._opener = opener

    def search_issues(
        self, owner: str, repository: str, query: str, limit: int
    ) -> list[dict[str, Any]]:
        search = f"{query} repo:{owner}/{repository} is:issue"
        path = "/search/issues?" + urlencode(
            {"q": search, "per_page": limit, "sort": "updated"}
        )
        payload = self._request("GET", path)
        return [
            {
                "number": item["number"],
                "title": item["title"],
                "state": item["state"],
                "url": item["html_url"],
                "updated_at": item["updated_at"],
            }
            for item in payload.get("items", [])[:limit]
        ]

    def create_issue(
        self, owner: str, repository: str, title: str, body: str
    ) -> dict[str, Any]:
        path = f"/repos/{quote(owner, safe='')}/{quote(repository, safe='')}/issues"
        payload = self._request("POST", path, {"title": title, "body": body})
        return {
            "number": payload["number"],
            "title": payload["title"],
            "state": payload["state"],
            "url": payload["html_url"],
        }

    def _request(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = Request(
            self.BASE_URL + path,
            data=data,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
                "User-Agent": "github-issue-mcp/1.0",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with self._opener(request, timeout=15) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            LOGGER.warning("GitHub request failed with HTTP status %s", exc.code)
            mapping = {
                401: ("authentication_failed", "GitHub rejected the configured token."),
                403: ("access_denied", "GitHub denied the request or its rate limit was reached."),
                404: ("not_found", "The repository or issue endpoint was not found."),
                422: ("invalid_request", "GitHub rejected the supplied issue data."),
            }
            code, message = mapping.get(
                exc.code, ("github_error", "GitHub could not complete the request.")
            )
            raise GitHubServiceError(code, message) from None
        except (URLError, TimeoutError):
            LOGGER.warning("GitHub request failed because the service was unreachable")
            raise GitHubServiceError(
                "service_unavailable", "GitHub is temporarily unreachable. Try again later."
            ) from None
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError):
            LOGGER.warning("GitHub returned an unexpected response shape")
            raise GitHubServiceError(
                "invalid_response", "GitHub returned an unexpected response."
            ) from None

