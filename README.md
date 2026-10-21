# Agent Workflow Toolkit

Three separate Python projects exploring issue drafting, draft review, and
evaluation of recorded agent behavior.
Maintained by Kaiwen Ji. Each folder is independently runnable; there is no
automatic integration or shared runtime between them.

| Project folder | What it does | Interface | External effects |
|---|---|---|---|
| [github-issue-mcp](github-issue-mcp/) | Searches GitHub issues, previews issue reports, and provides a triage prompt | MCP server | Can call GitHub and create issues when configured and explicitly authorized |
| [draft-approval-review-queue](draft-approval-review-queue/) | Binds draft approval to a revision and content hash, invalidates approval after edits, and records review events | Local CLI and SQLite | Local dry-runs only; sends nothing externally |
| [agent-evaluation-lab](agent-evaluation-lab/) | Replays recorded traces against explicit policies, compares variants, and produces HTML/JSON regression reports | Offline CLI | Reads local JSON and writes reports; no tool execution or model calls |

## Choose a project

**Working with GitHub issues?** Start with [GitHub Issue MCP](github-issue-mcp/README.md).
It demonstrates MCP tools/prompts, repository-scoped search, input validation,
and safe upstream error handling. It requires its own dependencies and a scoped
GitHub token for live use. Its caller-supplied confirmation flag does not
independently authenticate a human reviewer.

**Exploring approval workflows?** Start with [Draft Approval Review Queue](draft-approval-review-queue/README.md).
It demonstrates content-bound review decisions, stale-edit checks, transactional
state transitions, and idempotent local simulation. It uses Python's standard
library and needs no token or network. Its local approval command is not an
identity or access-control boundary.

**Testing agent behavior?** Start with [Agent Evaluation Lab](agent-evaluation-lab/README.md).
It checks recorded tool scope, retries, completion, output markers, and budgets,
then compares paired scenarios with CI gate modes. Its demo is explicitly
synthetic; it does not claim measured results from a live model.

These projects cover related steps in an agent workflow, but the review queue
does not currently authorize or execute the MCP server's GitHub operations.

## Run locally

Clone this repository, then enter the individual project folder. Relative paths
in each project's README refer to that folder, not the repository root.

GitHub Issue MCP (Python 3.11+):

```sh
cd github-issue-mcp
python -m pip install -r requirements.txt
python -m pytest -q
```

Draft Approval Review Queue (Python 3.11+):

```sh
cd draft-approval-review-queue
python demo.py
python -m unittest discover -s tests -v
```

Use separate virtual environments for the projects. For live MCP setup, follow
the project README and point the client configuration at `github-issue-mcp`.
Never commit your real `.env`, databases, or credentials.

Agent Evaluation Lab (Python 3.11+, standard library only):

```sh
cd agent-evaluation-lab
python -m unittest discover -s tests -v
python agent_eval.py compare examples/demo-suite.json
```

## Validation and provenance

- GitHub Issue MCP: earlier coursework prepared for a public portfolio; six
  offline tests passed during preparation. [Validation details](github-issue-mcp/VALIDATION.md).
- Draft Approval Review Queue: new portfolio prototype created in October 2026;
  twelve tests and the local demo passed during preparation. [Validation details](draft-approval-review-queue/VALIDATION.md).
- Agent Evaluation Lab: new October 2026 portfolio project; 27 unit tests passed
  locally. Includes seven synthetic paired scenarios, an HTML report, and a CI
  regression gate. [Validation details](agent-evaluation-lab/VALIDATION.md).
- All projects were prepared with OpenAI Codex assistance. None is presented
  as a production deployment. This combined repository adds organization and
  repository-root CI; it does not add a live integration between the projects.
- No open-source license has been selected. Public visibility alone does not
  grant an open-source license.

The older standalone repository called `agent-review-queue` contains the project
now organized here as `draft-approval-review-queue`; the descriptive folder name
distinguishes it from the GitHub-facing MCP server.
