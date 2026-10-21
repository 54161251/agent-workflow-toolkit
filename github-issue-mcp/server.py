"""Executable entry point for the GitHub Issue MCP server."""

from github_issue_mcp.server import mcp


if __name__ == "__main__":
    # MCP SDK run pattern adapted from the official documentation:
    # https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/run/index.md
    mcp.run(transport="stdio")

