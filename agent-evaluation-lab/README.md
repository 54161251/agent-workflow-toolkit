# Agent Evaluation Lab

An offline regression-testing tool for recorded agent behavior. Feed it JSON
traces and an explicit policy; get reproducible findings, paired comparisons,
CI exit codes, and a standalone HTML report. Python 3.11+, standard library only.

This is a new portfolio project created in October 2026 with OpenAI Codex
assistance. It evaluates recorded traces; it does not call an LLM, execute agent
tools, or connect to a service. The demo data is synthetic, not a benchmark of
real models or evidence of production adoption.

![Synthetic trace comparison report preview](reports/demo-preview.png)

## Why it exists

An agent can produce a plausible final answer after using a disallowed tool,
searching the wrong repository, or looping through identical calls. Looking only
at the answer misses those behaviors. This evaluator makes the declared checks
and recorded behavior visible together and lets a CI job reject regressions.

| Component | Responsibility |
|---|---|
| Trace validator | Rejects malformed records, duplicate JSON fields, invalid metrics, and events after completion |
| Policy evaluator | Checks tool scope, required successful tools, repository arguments, exact-call retries, answer markers, and budgets |
| Paired comparison | Reports improvements and regressions per scenario, so gains cannot hide a newly failing case |
| Report renderer | Escapes untrusted labels and findings; generates HTML without scripts or external assets |
| CLI | Produces machine-readable JSON and meaningful exit codes for automation |

## Try it

Run these commands **inside `agent-evaluation-lab`**:

```sh
python -m unittest discover -s tests -v
python agent_eval.py evaluate examples/passing-trace.json examples/policy.json
python agent_eval.py compare examples/demo-suite.json
python agent_eval.py compare examples/demo-suite.json --json reports/my-run.json --html reports/my-run.html
```

Open `reports/my-run.html` locally. Output files must be new: the CLI refuses to
overwrite existing files, including symlinks. Choose a different filename for
another run. A pre-generated [HTML demo](reports/demo.html) and
[JSON demo](reports/demo.json) are included; download the HTML to view it in a
browser. GitHub displays its source rather than hosting the page.

The included suite has seven paired scenarios: clean search, repository scope
escape, excessive identical retries, missing final answer, token budget overrun,
a forbidden output marker, and an unexpected write tool. Its handcrafted
baseline passes 1/7 and handcrafted candidate passes 7/7. These numbers are
fixture expectations used to demonstrate the evaluator, not measured gains from
an agent intervention. Rebuild the fixtures with `python examples/build_demo.py`.

## Evaluate your own agent

1. Capture calls and the final answer from your existing agent in the
   [trace format](TRACE_FORMAT.md). No particular model provider is required.
2. Set your policy before judging a run. Declare allowed and required tools,
   allowed repositories, output markers, and budgets.
3. Evaluate one run with `evaluate`, or put paired baseline/candidate traces in a
   suite. A suite requires both traces for every scenario and matching IDs.
4. Keep the same policy for both variants. Review individual findings alongside
   totals. The suite and individual inputs receive SHA-256 fingerprints.

Token and latency values are **reported inputs**. The evaluator sums them; it
does not independently measure provider usage or elapsed time. Include all model
usage in the events you record, without double-counting it. Recorded latency is
the sum of event durations, not parallel wall-clock time. No dollar-cost estimate
or model pricing is used.

## CI gate modes

```sh
# Default: every candidate scenario must pass.
python agent_eval.py compare examples/demo-suite.json --fail-on candidate-failure

# Alternative: fail only when a previously passing scenario becomes failing.
python agent_eval.py compare examples/demo-suite.json --fail-on regression
```

| Exit code | Meaning |
|---|---|
| `0` | Selected gate passed |
| `1` | A valid evaluation failed the selected gate |
| `2` | Input, argument, or output error; results are not a successful evaluation |

Regression mode can allow failures that already existed in the baseline.
The default candidate-failure mode is stricter. The root repository workflow
runs the unit tests and the synthetic comparison on Python 3.11, 3.12, and 3.13.

## Boundaries

- PASS means only that these deterministic checks passed. Substring answer
  matching does not establish correctness, citations, or factual grounding.
- Repository scope applies only to a top-level `repository` argument. This is
  not a general argument schema validator, URL inspector, or data-loss detector.
- The retry key is the exact tool name plus canonical JSON arguments. Calls with
  changed arguments are distinct. Identical calls after success also count as
  repeated calls; a retry budget of one permits two identical calls.
- Failed calls count toward budgets. A required tool must have at least one
  recorded successful call; a failed attempt followed by recovery can pass.
- Forbidden markers are checked only in the final answer. This does not detect
  paraphrased secrets, encoded output, intermediate leakage, or prompt injection.
- The trace author can fabricate records. Hashes identify inputs; they are not
  signatures, proof of execution, or evidence of human authorization.
- This tool never prevents a live action. Run it on recorded data, or use its
  result in your own system. It is not wired into the other toolkit projects.
- Reports include declared policy terms and findings. Use synthetic placeholders
  for secret markers and review real traces before sharing reports publicly.
- Inputs are bounded to 2 MB, 100 suite cases, and 1,000 events per trace. Numeric
  metrics and budgets must be finite, nonnegative, and at most 10^12. Token counts
  and call/retry budgets must be integers. No plugins or dynamic code are loaded.

See [VALIDATION.md](VALIDATION.md) for checks actually run and limitations.
No open-source license has been selected by the repository owner.
