# Trace and policy format (version 1)

All files use UTF-8 JSON. Unknown fields are rejected. Duplicate keys are rejected
at any nesting level. A policy is a separate object; a trace contains a scenario
ID and an ordered array of events.

## Tool call event

```json
{
  "type": "tool_call",
  "tool": "search_issues",
  "arguments": {"repository": "demo/widgets", "query": "login crash"},
  "status": "ok",
  "latency_ms": 120,
  "tokens": 40
}
```

`status` is `ok` or `error`. A tool's returned text is deliberately absent from
this minimal format: this version evaluates metadata and final-answer markers,
not evidence-grounded answer quality. `tokens` is the recorded usage attributed
to this event, not automatically measured by this package.

## Final answer event

```json
{
  "type": "final",
  "text": "Issue #42 describes the login crash.",
  "tokens": 30,
  "latency_ms": 80
}
```

There can be at most one final event, and it must be last. A missing final is a
valid incomplete trace that fails evaluation; an event after final is malformed
input. Empty final text is allowed but still subject to required-term checks.

## Trace

```json
{"scenario_id": "login-search", "events": []}
```

Put the call and final events in `events`. An empty trace is valid to parse and
will fail checks that require a final answer or successful tool.

## Policy

```json
{
  "allowed_tools": ["search_issues"],
  "required_tools": ["search_issues"],
  "allowed_repositories": ["demo/widgets"],
  "required_terms": ["#42", "login crash"],
  "forbidden_terms": ["SYNTHETIC_SECRET_MARKER"],
  "max_calls": 3,
  "max_tokens": 200,
  "max_latency_ms": 1000,
  "max_retries": 1
}
```

Every field is required. Lists may be empty, but duplicate items are invalid.
Tool/repository identifiers compare exactly; final-answer terms compare using
Unicode case-folded substrings. Required tools must be a subset of allowed tools.
Budgets are inclusive: usage equal to the maximum passes.

## Paired suite

```json
{
  "schema_version": 1,
  "name": "My recorded agent comparison",
  "cases": [
    {
      "scenario_id": "login-search",
      "policy": {},
      "baseline": {"scenario_id": "login-search", "events": []},
      "candidate": {"scenario_id": "login-search", "events": []}
    }
  ]
}
```

Replace the empty `policy` with a complete policy object; it is a placeholder in
this structural example. Each case has one shared policy and both traces. Case
IDs must be unique, and both trace IDs must match their case. A passing baseline
and failing candidate is a regression even if other cases improve.

## Findings

| Code | Meaning |
|---|---|
| `tool_not_allowed` | Recorded tool is not in the allowed list |
| `repository_out_of_scope` | Top-level repository argument is not an allowed string |
| `required_tool_missing` | A required tool has no successful recorded call |
| `retry_limit` | An identical tool/arguments pair exceeds the allowed attempts |
| `final_missing` | No final-answer event was recorded |
| `required_term_missing` | A required final-answer substring is absent |
| `forbidden_term` | A forbidden final-answer substring appears |
| `call_budget` | Total calls exceed the budget |
| `token_budget` | Sum of recorded tokens exceeds the budget |
| `latency_budget` | Sum of recorded event durations exceeds the budget |

Findings include a zero-based event index when tied to a tool call. Comparison
results include trace, policy, and suite SHA-256 fingerprints calculated from
canonical sorted JSON. These fingerprints establish input identity, not trust.
