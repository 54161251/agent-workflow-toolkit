"""Offline evaluation of recorded agent traces. Python 3.11+, standard library only."""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict, dataclass
import hashlib
import html
import json
import math
from pathlib import Path
import sys
from typing import Any

VERSION = "1.0.0"
MAX_FILE_BYTES = 2_000_000
MAX_EVENTS = 1000


class InputError(ValueError):
    """An input cannot be evaluated reliably."""


def _object(value: Any, keys: set[str], label: str) -> dict:
    if not isinstance(value, dict) or set(value) != keys:
        raise InputError(f"{label}: expected fields {', '.join(sorted(keys))}")
    return value


def _text(value: Any, label: str, *, empty: bool = False) -> str:
    if not isinstance(value, str) or (not empty and not value.strip()) or len(value) > 20000:
        raise InputError(f"{label}: expected a string of at most 20000 characters")
    return value


def _number(value: Any, label: str, *, integer: bool = False) -> float | int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InputError(f"{label}: expected a nonnegative number")
    if value < 0 or value > 1_000_000_000_000 or not math.isfinite(value) or (integer and not isinstance(value, int)):
        raise InputError(f"{label}: invalid nonnegative number")
    return value


def _strings(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or len(value) > 100:
        raise InputError(f"{label}: expected a list with at most 100 items")
    for item in value:
        _text(item, label)
    if len(set(value)) != len(value):
        raise InputError(f"{label}: duplicate items")
    return value


def _pairs(pairs: list[tuple[str, Any]]) -> dict:
    result: dict = {}
    for key, value in pairs:
        if key in result:
            raise InputError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def load_json(path: str | Path) -> Any:
    """Read bounded UTF-8 JSON; never run expressions, plugins, or embedded URLs."""
    try:
        with Path(path).open("rb") as stream:
            raw = stream.read(MAX_FILE_BYTES + 1)
        if len(raw) > MAX_FILE_BYTES:
            raise InputError("input file exceeds 2 MB")
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(InputError("nonfinite JSON number")))
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise InputError(f"cannot read valid UTF-8 JSON: {type(exc).__name__}") from exc


def fingerprint(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True, allow_nan=False).encode()).hexdigest()


def validate_policy(policy: Any) -> dict:
    _object(policy, {"allowed_tools", "required_tools", "allowed_repositories", "required_terms",
                     "forbidden_terms", "max_calls", "max_tokens", "max_latency_ms", "max_retries"}, "policy")
    for key in ("allowed_tools", "required_tools", "allowed_repositories", "required_terms", "forbidden_terms"):
        _strings(policy[key], key)
    if not set(policy["required_tools"]) <= set(policy["allowed_tools"]):
        raise InputError("required_tools must be a subset of allowed_tools")
    for key in ("max_calls", "max_tokens", "max_retries"):
        _number(policy[key], key, integer=True)
    _number(policy["max_latency_ms"], "max_latency_ms")
    return policy


def validate_trace(trace: Any) -> dict:
    _object(trace, {"scenario_id", "events"}, "trace")
    _text(trace["scenario_id"], "scenario_id")
    events = trace["events"]
    if not isinstance(events, list) or len(events) > MAX_EVENTS:
        raise InputError("events must be a list of at most 1000 entries")
    finished = False
    for event in events:
        if not isinstance(event, dict):
            raise InputError("event must be an object")
        if finished:
            raise InputError("events after the final answer are invalid")
        if event.get("type") == "tool_call":
            _object(event, {"type", "tool", "arguments", "status", "latency_ms", "tokens"}, "tool_call")
            _text(event["tool"], "tool")
            if not isinstance(event["arguments"], dict):
                raise InputError("arguments must be an object")
            # Canonicalize only JSON data; reject nonfinite nested argument values.
            try:
                encoded = json.dumps(event["arguments"], allow_nan=False)
            except (ValueError, TypeError, RecursionError) as exc:
                raise InputError("arguments must contain finite JSON data") from exc
            if len(encoded) > 20000:
                raise InputError("arguments exceed 20000 characters")
            if event["status"] not in ("ok", "error"):
                raise InputError("status must be ok or error")
            _number(event["latency_ms"], "latency_ms")
            _number(event["tokens"], "tokens", integer=True)
        elif event.get("type") == "final":
            _object(event, {"type", "text", "tokens", "latency_ms"}, "final")
            _text(event["text"], "text", empty=True)
            _number(event["tokens"], "tokens", integer=True)
            _number(event["latency_ms"], "latency_ms")
            finished = True
        else:
            raise InputError("unknown event type")
    return trace


@dataclass(frozen=True)
class Finding:
    code: str
    message: str
    event_index: int | None = None


@dataclass(frozen=True)
class Result:
    scenario_id: str
    passed: bool
    calls: int
    tokens: int
    recorded_latency_ms: float
    failed_calls: int
    findings: list[Finding]
    trace_sha256: str
    policy_sha256: str


def evaluate(trace: Any, policy: Any) -> Result:
    """Judge recorded behavior. No tool execution, API calls, or model inference."""
    validate_trace(trace)
    validate_policy(policy)
    findings: list[Finding] = []
    calls = 0
    tokens = 0
    latency = 0.0
    failed = 0
    used: set[str] = set()
    attempts: Counter[str] = Counter()
    final: str | None = None
    for index, event in enumerate(trace["events"]):
        tokens += event["tokens"]
        latency += event["latency_ms"]
        if not math.isfinite(latency):
            raise InputError("aggregate latency exceeds numeric range")
        if event["type"] == "final":
            final = event["text"]
            continue
        calls += 1
        failed += event["status"] == "error"
        tool = event["tool"]
        if event["status"] == "ok":
            used.add(tool)
        if tool not in policy["allowed_tools"]:
            findings.append(Finding("tool_not_allowed", f"Tool is not allowed: {tool}", index))
        # Any tool argument named repository is subject to the declared scope.
        repo = event["arguments"].get("repository")
        if "repository" in event["arguments"] and (not isinstance(repo, str) or repo not in policy["allowed_repositories"]):
            findings.append(Finding("repository_out_of_scope", "Repository is outside the declared scope", index))
        key = fingerprint({"tool": tool, "arguments": event["arguments"]})
        attempts[key] += 1
        # Retry means any repeated exact tool/argument pair, including after success.
        if attempts[key] > policy["max_retries"] + 1:
            findings.append(Finding("retry_limit", "Repeated identical call exceeds retry limit", index))
    missing = sorted(set(policy["required_tools"]) - used)
    for tool in missing:
        findings.append(Finding("required_tool_missing", f"Required tool was not called: {tool}"))
    if final is None:
        findings.append(Finding("final_missing", "Trace has no final answer"))
    else:
        for term in policy["required_terms"]:
            if term.casefold() not in final.casefold():
                findings.append(Finding("required_term_missing", f"Final answer is missing: {term}"))
        for term in policy["forbidden_terms"]:
            if term.casefold() in final.casefold():
                findings.append(Finding("forbidden_term", f"Final answer contains forbidden marker: {term}"))
    for actual, maximum, code, label in [
        (calls, policy["max_calls"], "call_budget", "Tool calls"),
        (tokens, policy["max_tokens"], "token_budget", "Recorded tokens"),
        (latency, policy["max_latency_ms"], "latency_budget", "Recorded latency"),
    ]:
        if actual > maximum:
            findings.append(Finding(code, f"{label}: {actual} exceeds {maximum}"))
    return Result(trace["scenario_id"], not findings, calls, tokens, latency,
                  failed, findings, fingerprint(trace), fingerprint(policy))


def load_suite(path: str | Path) -> dict:
    suite = load_json(path)
    _object(suite, {"schema_version", "name", "cases"}, "suite")
    if type(suite["schema_version"]) is not int or suite["schema_version"] != 1:
        raise InputError("suite schema_version must be 1")
    _text(suite["name"], "name")
    if not isinstance(suite["cases"], list) or not 1 <= len(suite["cases"]) <= 100:
        raise InputError("suite requires 1 to 100 cases")
    seen = set()
    for case in suite["cases"]:
        _object(case, {"scenario_id", "policy", "baseline", "candidate"}, "case")
        _text(case["scenario_id"], "scenario_id")
        if case["scenario_id"] in seen:
            raise InputError("duplicate scenario_id")
        seen.add(case["scenario_id"])
        validate_policy(case["policy"])
        for variant in ("baseline", "candidate"):
            validate_trace(case[variant])
            if case[variant]["scenario_id"] != case["scenario_id"]:
                raise InputError("trace scenario_id does not match case")
    return suite


def compare(suite: dict) -> dict:
    rows = []
    for case in suite["cases"]:
        baseline = evaluate(case["baseline"], case["policy"])
        candidate = evaluate(case["candidate"], case["policy"])
        transition = ("regression" if baseline.passed and not candidate.passed else
                      "improvement" if not baseline.passed and candidate.passed else "unchanged")
        rows.append({"scenario_id": case["scenario_id"], "transition": transition,
                     "baseline": asdict(baseline), "candidate": asdict(candidate)})
    return {"schema_version": 1, "evaluator_version": VERSION, "suite_name": suite["name"],
            "suite_sha256": fingerprint(suite), "cases": rows,
            "summary": {"total": len(rows),
                        "baseline_passed": sum(r["baseline"]["passed"] for r in rows),
                        "candidate_passed": sum(r["candidate"]["passed"] for r in rows),
                        "regressions": sum(r["transition"] == "regression" for r in rows),
                        "improvements": sum(r["transition"] == "improvement" for r in rows)}}


def render_html(report: dict) -> str:
    """Self-contained report with escaped user content, no scripts or remote assets."""
    esc = lambda value: html.escape(str(value), quote=True)
    summary = report["summary"]
    rows = []
    for row in report["cases"]:
        cells = [f'<th scope="row">{esc(row["scenario_id"])}</th>', f'<td>{esc(row["transition"])}</td>']
        for variant in ("baseline", "candidate"):
            result = row[variant]
            details = "".join(f'<li><code>{esc(f["code"])}</code>: {esc(f["message"])}</li>' for f in result["findings"])
            cells.append(f'<td><strong>{"PASS" if result["passed"] else "FAIL"}</strong>'
                         f'<p>{result["calls"]} calls · {result["tokens"]} recorded tokens · '
                         f'{result["recorded_latency_ms"]:g} ms</p><ul>{details}</ul></td>')
        rows.append('<tr>' + ''.join(cells) + '</tr>')
    return '''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Agent Evaluation Lab — comparison</title>
<style>
:root{color-scheme:light}body{font:16px/1.5 system-ui,sans-serif;background:#f3f6fa;color:#172c42;margin:0}
main{max-width:1200px;margin:auto;padding:36px 24px}header{border-top:5px solid #14675e;padding-top:18px}
h1{font-size:36px;margin:6px 0}.eyebrow{color:#14675e;font-weight:700;letter-spacing:.12em}
.cards{display:flex;gap:16px;flex-wrap:wrap;margin:26px 0}.card{background:white;padding:18px 26px;border:1px solid #d5dfe9;border-radius:10px;flex:1}
.card b{display:block;font-size:30px}table{border-collapse:collapse;width:100%;background:white}th,td{text-align:left;padding:16px;border:1px solid #d5dfe9;vertical-align:top}
thead{background:#17394c;color:white}td p{font-size:14px;color:#425970}code{font-size:13px}ul{padding-left:18px}small{overflow-wrap:anywhere}.table-wrap{overflow:auto}.note{background:#e4efec;padding:16px;border-radius:8px}
</style><main><header><div class="eyebrow">AGENT EVALUATION LAB</div>
<h1>Recorded behavior, inspectable results.</h1>
<p>''' + esc(report["suite_name"]) + '''</p></header><p class="note">Offline trace replay. Demo traces are synthetic fixtures, not measurements of a live model. Token and latency values are supplied by the trace author.</p>
<section class="cards" aria-label="Summary">''' + ''.join(
        f'<div class="card">{esc(label)}<b>{esc(value)}</b></div>' for label, value in [
            ("Baseline passing", f'{summary["baseline_passed"]}/{summary["total"]}'),
            ("Candidate passing", f'{summary["candidate_passed"]}/{summary["total"]}'),
            ("Improved cases", summary["improvements"]), ("Regressions", summary["regressions"])]) + '''</section>
<div class="table-wrap"><table><thead><tr><th>Scenario</th><th>Change</th><th>Baseline</th><th>Candidate</th></tr></thead><tbody>''' + ''.join(rows) + '''</tbody></table></div>
<p>PASS means only that the declared deterministic checks passed. It does not establish factual grounding, prompt-injection resistance, human authorization, or production safety.</p>
<small>Evaluator ''' + esc(report["evaluator_version"]) + ' · Suite SHA-256: ' + esc(report["suite_sha256"]) + '</small></main></html>'


def _write(path: str, content: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    # Deliberately refuse to overwrite existing files, including symlinks.
    with target.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(content)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    one = commands.add_parser("evaluate", help="evaluate one trace against one policy")
    one.add_argument("trace")
    one.add_argument("policy")
    paired = commands.add_parser("compare", help="compare paired traces in a suite")
    paired.add_argument("suite")
    paired.add_argument("--fail-on", choices=("candidate-failure", "regression"), default="candidate-failure")
    paired.add_argument("--html", help="write a new standalone HTML report")
    for command in (one, paired):
        command.add_argument("--json", help="write a new machine-readable JSON result")
    args = parser.parse_args(argv)
    try:
        if args.command == "evaluate":
            result = evaluate(load_json(args.trace), load_json(args.policy))
            report = asdict(result)
            code = 0 if result.passed else 1
        else:
            report = compare(load_suite(args.suite))
            s = report["summary"]
            code = int(s["candidate_passed"] != s["total"] if args.fail_on == "candidate-failure" else s["regressions"] > 0)
            if args.html:
                _write(args.html, render_html(report))
        serialized = json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
        if args.json:
            _write(args.json, serialized)
        print(serialized, end="")
        return code
    except (InputError, OSError, ValueError, RecursionError) as exc:
        print(f"Input/output error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
