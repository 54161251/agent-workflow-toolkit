# Validation

Verified locally on Windows with Python 3.12.14 during portfolio preparation on
2026-10-21. No LLM or network calls were made.

- `python -m unittest discover -s tests -v`: **12 passed**.
- `python demo.py`: unapproved draft blocked; edit invalidated approval;
  approved local dry-run completed with `sent=false`; replay returned stored result.
- Two concurrent clients returned the same stored result and created exactly one
  `dry_run_completed` event.
- Input-shape, stale-review, stale-edit, rejected-state, parameterized-SQL and
  mismatched-payload checks are covered by tests.

The Windows sandbox's default temporary directory could not be opened by SQLite
in this session. Tests were run with TMP/TEMP pointing to a writable workspace
temporary folder. Application code explicitly closes database connections.

Not verified: hosted deployment, identity separation, malicious database owners,
production load, or any external action adapter. The project contains no such adapter.
