# Validation

Revalidated on 2026-10-21, Windows, Python 3.13.1, MCP 2.2.0,
python-dotenv 1.1.1, and pytest 8.4.2: **6 tests passed**.

The tests cover MCP tool/prompt discovery and preview execution, mocked GitHub
HTTP behavior, repository/query validation, and sanitized error disclosure.
The contract test injects a synthetic Settings object; no `.env` or real token is
required for tests. No live GitHub issue was created during validation.

The sandboxed in-process MCP test transport stalled in this session; rerunning
the same test suite outside the sandbox passed. A second run after removing the
temporary dummy `.env` also passed. Live GitHub authentication, network API calls,
and an end-user Claude Desktop session were not verified in this preparation.

The application source is preserved from the earlier coursework project. The
portfolio preparation updates documentation, uses a portable client-config
example, removes personal machine configuration, and isolates test credentials.
