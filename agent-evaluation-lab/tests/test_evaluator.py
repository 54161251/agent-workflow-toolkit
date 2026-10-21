from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest

import agent_eval as lab
from examples.build_demo import POLICY, build_suite, call, final


class EvaluatorTests(unittest.TestCase):
    def setUp(self):
        self.policy = deepcopy(POLICY)
        self.trace = {"scenario_id": "sample", "events": [call(), final()]}

    def codes(self, trace=None, policy=None):
        return {f.code for f in lab.evaluate(trace or self.trace, policy or self.policy).findings}

    def test_valid_trace_and_exact_budget_boundary(self):
        self.policy.update(max_calls=1, max_tokens=70, max_latency_ms=200)
        self.assertTrue(lab.evaluate(self.trace, self.policy).passed)

    def test_required_tool_must_succeed(self):
        self.trace["events"][0]["status"] = "error"
        self.assertIn("required_tool_missing", self.codes())

    def test_recovered_failure_is_allowed(self):
        self.trace["events"].insert(0, call(status="error"))
        result = lab.evaluate(self.trace, self.policy)
        self.assertTrue(result.passed)
        self.assertEqual(result.failed_calls, 1)

    def test_unknown_tool_and_repository_are_reported(self):
        self.trace["events"][0].update(tool="delete_all", arguments={"repository": "other/private"})
        self.assertTrue({"tool_not_allowed", "repository_out_of_scope"} <= self.codes())

    def test_nonstring_repository_is_a_violation(self):
        self.trace["events"][0]["arguments"]["repository"] = ["demo/widgets"]
        self.assertIn("repository_out_of_scope", self.codes())

    def test_retry_limit_uses_canonical_arguments(self):
        first = call(arguments={"query": "login crash", "repository": "demo/widgets"})
        self.trace["events"] = [first, call(), call(), final()]
        self.assertIn("retry_limit", self.codes())

    def test_different_arguments_are_not_identical_retries(self):
        self.policy["max_retries"] = 0
        self.trace["events"].insert(0, call(arguments={"repository": "demo/widgets", "query": "another bug"}))
        self.assertNotIn("retry_limit", self.codes())

    def test_missing_and_empty_final(self):
        self.trace["events"] = [call()]
        self.assertIn("final_missing", self.codes())
        self.trace["events"].append(final(text=""))
        self.assertIn("required_term_missing", self.codes())

    def test_case_insensitive_answer_checks(self):
        self.trace["events"][-1]["text"] = "#42 LOGIN CRASH synthetic_secret_marker"
        self.assertEqual(self.codes(), {"forbidden_term"})

    def test_all_budgets_include_final_answer(self):
        self.policy.update(max_calls=0, max_tokens=40, max_latency_ms=150)
        self.assertTrue({"call_budget", "token_budget", "latency_budget"} <= self.codes())

    def test_boolean_negative_nonfinite_and_excessive_metrics_rejected(self):
        for value in (True, -1, float("nan"), float("inf"), 10**400):
            with self.subTest(value=str(value)):
                trace = deepcopy(self.trace)
                trace["events"][0]["tokens"] = value
                with self.assertRaises(lab.InputError):
                    lab.evaluate(trace, self.policy)

    def test_fractional_tokens_and_wrong_schema_rejected(self):
        self.trace["events"][0]["tokens"] = 1.5
        with self.assertRaises(lab.InputError):
            lab.evaluate(self.trace, self.policy)
        self.trace["events"][0]["tokens"] = 10
        self.trace["extra"] = "unrecognized"
        with self.assertRaises(lab.InputError):
            lab.evaluate(self.trace, self.policy)

    def test_nested_nonfinite_arguments_rejected(self):
        self.trace["events"][0]["arguments"] = {"nested": [float("nan")]}
        with self.assertRaises(lab.InputError):
            lab.evaluate(self.trace, self.policy)

    def test_events_after_final_rejected(self):
        for event in (call(), final()):
            trace = deepcopy(self.trace)
            trace["events"].append(event)
            with self.assertRaises(lab.InputError):
                lab.evaluate(trace, self.policy)

    def test_policy_cannot_require_disallowed_tool(self):
        self.policy["required_tools"] = ["unknown"]
        with self.assertRaises(lab.InputError):
            lab.evaluate(self.trace, self.policy)

    def test_fingerprints_are_reproducible_and_sensitive(self):
        before = lab.evaluate(self.trace, self.policy)
        self.assertEqual(before, lab.evaluate(deepcopy(self.trace), deepcopy(self.policy)))
        self.trace["events"][0]["tokens"] += 1
        after = lab.evaluate(self.trace, self.policy)
        self.assertNotEqual(before.trace_sha256, after.trace_sha256)
        self.assertEqual(before.policy_sha256, after.policy_sha256)

    def test_demo_comparison_is_explicitly_synthetic(self):
        report = lab.compare(build_suite())
        self.assertEqual(report["summary"], {"total": 7, "baseline_passed": 1,
                                           "candidate_passed": 7, "regressions": 0, "improvements": 6})
        self.assertIn("Synthetic", report["suite_name"])

    def test_regression_detected_even_if_other_case_improves(self):
        suite = build_suite()
        suite["cases"][0]["candidate"]["events"] = [call()]
        self.assertEqual(lab.compare(suite)["summary"]["regressions"], 1)

    def test_html_escapes_untrusted_labels_and_findings(self):
        suite = build_suite()
        suite["name"] = '<script>alert("x")</script>'
        suite["cases"][0]["candidate"]["scenario_id"] = '<img src=x onerror=alert(1)>'
        suite["cases"][0]["scenario_id"] = '<img src=x onerror=alert(1)>'
        suite["cases"][0]["policy"]["required_terms"] = ["<iframe>"]
        rendered = lab.render_html(lab.compare(suite))
        self.assertNotIn("<script>", rendered)
        self.assertNotIn("<img", rendered)
        self.assertNotIn("<iframe>", rendered)
        self.assertIn("&lt;script&gt;", rendered)


class FileAndCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write(self, name, value):
        path = self.root / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return str(path)

    def run_cli(self, args):
        with redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()) as err:
            code = lab.main(args)
        return code, out.getvalue(), err.getvalue()

    def test_duplicate_keys_invalid_json_and_invalid_encoding(self):
        path = self.root / "bad.json"
        for raw in (b'{"x":1,"x":2}', b'NaN', b'{', b'\xff'):
            path.write_bytes(raw)
            with self.subTest(raw=raw), self.assertRaises(lab.InputError):
                lab.load_json(path)

    def test_input_size_is_bounded(self):
        path = self.root / "large.json"
        path.write_bytes(b" " * (lab.MAX_FILE_BYTES + 1))
        with self.assertRaises(lab.InputError):
            lab.load_json(path)

    def test_trace_event_limit(self):
        with self.assertRaises(lab.InputError):
            lab.validate_trace({"scenario_id": "large", "events": [call()] * (lab.MAX_EVENTS + 1)})

    def test_suite_rejects_missing_pair_duplicate_ids_and_mismatches(self):
        for mutate in (lambda s: s["cases"][0].pop("candidate"),
                       lambda s: s["cases"].append(deepcopy(s["cases"][0])),
                       lambda s: s["cases"][0]["candidate"].update(scenario_id="wrong")):
            suite = build_suite()
            mutate(suite)
            path = self.write("suite.json", suite)
            with self.assertRaises(lab.InputError):
                lab.load_suite(path)

    def test_cli_writes_report_and_refuses_overwrite(self):
        suite = self.write("suite.json", build_suite())
        result = str(self.root / "nested" / "report.json")
        page = str(self.root / "report.html")
        code, out, _ = self.run_cli(["compare", suite, "--json", result, "--html", page])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), lab.load_json(result))
        self.assertIn("<!doctype html>", Path(page).read_text())
        old = Path(page).read_bytes()
        self.assertEqual(self.run_cli(["compare", suite, "--html", page])[0], 2)
        self.assertEqual(old, Path(page).read_bytes())

    def test_cli_distinguishes_policy_failure_from_input_error(self):
        suite = build_suite()
        suite["cases"][0]["candidate"]["events"] = [call()]
        path = self.write("suite.json", suite)
        self.assertEqual(self.run_cli(["compare", path])[0], 1)
        self.assertEqual(self.run_cli(["compare", path, "--fail-on", "regression"])[0], 1)
        self.assertEqual(self.run_cli(["compare", str(self.root / "missing.json")])[0], 2)

    def test_regression_gate_can_allow_preexisting_failures(self):
        suite = build_suite()
        case = suite["cases"][1]
        case["candidate"] = deepcopy(case["baseline"])
        path = self.write("suite.json", suite)
        self.assertEqual(self.run_cli(["compare", path])[0], 1)
        self.assertEqual(self.run_cli(["compare", path, "--fail-on", "regression"])[0], 0)

    def test_single_trace_exit_codes(self):
        trace = {"scenario_id": "single", "events": [call(), final()]}
        path = self.write("trace.json", trace)
        policy = self.write("policy.json", POLICY)
        self.assertEqual(self.run_cli(["evaluate", path, policy])[0], 0)
        trace["events"] = []
        path = self.write("trace.json", trace)
        self.assertEqual(self.run_cli(["evaluate", path, policy])[0], 1)


if __name__ == "__main__":
    unittest.main()
