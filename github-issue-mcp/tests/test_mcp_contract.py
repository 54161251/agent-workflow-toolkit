import asyncio
from unittest.mock import patch

from mcp import Client

from github_issue_mcp.config import Settings

# Tests must never depend on a real account credential or a developer's .env.
with patch.object(Settings, 'from_env_file', return_value=Settings('offline-test-placeholder')):
    from github_issue_mcp.server import mcp


def test_server_exposes_and_executes_required_primitives() -> None:
    async def exercise_server() -> None:
        async with Client(mcp) as client:
            tools = await client.list_tools()
            prompts = await client.list_prompts()
            assert {tool.name for tool in tools.tools} == {
                "search_github_issues",
                "create_github_issue",
            }
            assert {prompt.name for prompt in prompts.prompts} == {
                "triage_github_issue"
            }

            preview = await client.call_tool(
                "create_github_issue",
                {
                    "owner": "acme",
                    "repository": "demo",
                    "title": "Build fails",
                    "body": "The build exits with status 1.",
                    "confirm": False,
                },
            )
            assert preview.structured_content["ok"] is True
            assert preview.structured_content["created"] is False

            prompt = await client.get_prompt(
                "triage_github_issue", {"issue_text": "The build fails."}
            )
            assert "Do not invent facts" in prompt.messages[0].content.text

    asyncio.run(exercise_server())

