# GitHub Issue Assistant MCP Server

A local Python MCP server in the **Development Workflow** domain. It lets an MCP
client search issues in one GitHub repository, preview/create an issue, and use a
prompt template to turn an unstructured bug report into a well-scoped issue.

## What it exposes

| MCP primitive | Name | Purpose |
|---|---|---|
| Tool | `search_github_issues` | Search issues within exactly one repository |
| Tool | `create_github_issue` | Preview an issue, then create it only when `confirm=true` |
| Prompt | `triage_github_issue` | Structure a raw report without inventing facts |

## Prerequisites

- Python 3.11 or newer
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- A GitHub fine-grained personal access token scoped to the demo repository with
  **Issues: Read and write** permission
- Claude Desktop for the integration demo

## Setup with uv

Open this folder in VS Code, then use its integrated terminal:

```powershell
uv venv
.\.venv\Scripts\Activate.ps1
uv pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` and replace the placeholder with your GitHub token. The server reads
the secret directly from that file with `pathlib.Path` and `python-dotenv`; it is
not stored in source code, the Claude config, or a system environment variable.
The `.gitignore` prevents `.env` and the virtual environment from being committed.
Select the local `.venv` interpreter in your editor after setup.

## Run and inspect

```powershell
uv run mcp dev server.py
```

The MCP Inspector URL appears in the terminal. Test the prompt and tools there.
For `create_github_issue`, first leave `confirm` false to inspect the preview. Set
it to true only when you intend to create the real issue.

The server uses stdio. A blank terminal after running it directly is normal: it is
waiting for an MCP client, and stdout is reserved for protocol messages.

## Claude Desktop configuration

1. Open Claude Desktop's developer settings and locate its configuration file.
2. Merge the `mcpServers` object from `claude_desktop_config.example.json`
   into that file. Replace the example directory with your local project path.
   If `uv` is not on the client PATH, use its absolute executable path.
3. Confirm `.env` contains the token, then fully quit and restart Claude Desktop.
4. Ask Claude to list or use `search_github_issues`. The hammer/tool icon should
   show both tools, and the prompt should appear in the prompt picker.

If the project is moved, update the `--directory` path in the JSON. Do not add the
GitHub token to that JSON.

## Best practices and exploit demonstrations

### 1. Input sanitization

All owner, repository, query, title, body, and limit values are validated before
any URL or request is built. Repository identifiers allow only one safe path
segment, and user queries cannot inject `repo:`, `org:`, or `user:` qualifiers to
escape the requested repository.

Exploit: `safe-repo/../../victim?access_token=stolen` attempts path/query
injection. `validate_repository_part` rejects it before an HTTP request occurs.

### 2. Error disclosure

The GitHub client maps upstream HTTP/network/parsing failures to a small set of
safe error codes. It never returns GitHub response bodies, exception details,
request URLs, file paths, or tokens to the MCP client. Unexpected exceptions also
produce only `internal_error`.

Exploit: the demo simulates a malicious 401 response whose error message/body
contains a token and private database path. The MCP-visible error contains neither.

Run both exploit demos:

```powershell
uv run --project . python scripts/demo_exploits.py
```

Run the automated tests:

```powershell
uv run --project . pytest
```

## Demo checklist

1. Show `.venv` selected as the Python interpreter in VS Code.
2. Show `.env.example`, `.gitignore`, and explain that the real `.env` is local.
3. Run `uv run mcp dev server.py`; list the two tools and one prompt.
4. Search a repository's issues.
5. Preview an issue with `confirm=false`, approve it, then create it with
   `confirm=true` in a repository made for the demo.
6. Restart Claude Desktop and invoke the server there.
7. Run `scripts/demo_exploits.py`, then `pytest`.

## Design and safety notes

- The read and write operations are separate because they have different intent
  and risk. The write tool adds a confirmation gate so the model cannot create an
  issue during drafting.
- GitHub calls have a 15-second timeout and return a limited set of response fields.
- The token is sent only in the HTTPS `Authorization` header.
- This assignment implementation does not retry or cache requests. GitHub may rate
  limit it, in which case the client receives a safe `access_denied` error.

## Code citations

The MCP decorator and `run()` patterns are adapted from the official MCP Python
SDK tutorials and are cited beside the relevant code in `src/github_issue_mcp/server.py`
and `server.py`:

- https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/get-started/first-steps.md
- https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/run/index.md

This coursework implementation was prepared with AI coding assistance. The
portfolio package preserves the application source and removes machine-specific
configuration. It is a learning prototype, not a production deployment.


## Validation status and boundaries

The included tests use local/in-process or mocked interfaces. The portfolio
preparation does not create any live GitHub issues or verify a live token.
The `confirm` field is a caller-supplied drafting convention, not a separate
human-identity or authorization boundary: an MCP host must enforce its own
human approval before passing `confirm=true`. The server does not independently
authenticate a human reviewer. Do not grant it a broadly scoped token.

The original task-tracker project stores local tasks; this project instead
demonstrates external HTTP integration, constrained repository search, request
validation, issue previews, and safe upstream-error handling.
