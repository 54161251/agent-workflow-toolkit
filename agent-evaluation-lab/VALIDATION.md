# Validation

Created and verified locally on 2026-10-21 with Python 3.12.14 on Windows.

- `python -m unittest discover -s tests -v`: **27 tests passed**.
- Tests cover input boundaries, nonfinite/negative/bool metrics, duplicate JSON
  keys, tool and repository scope, exact-call retry limits, required successful
  calls, incomplete traces, budget boundaries, output markers, hash stability,
  paired regressions, HTML escaping, CLI exit codes, and overwrite refusal.
- The seven-case synthetic suite yields 1/7 passing baseline traces and 7/7
  passing candidate traces. These are handcrafted fixture expectations.
- Static HTML and JSON are generated from the same report object. The renderer
  uses escaped text, no JavaScript, and no external assets.
- Inputs, examples, and tests require no third-party dependencies, API keys,
  paid services, or network access. No live agent or model was evaluated.

Tests used a writable workspace temporary directory. The root GitHub Actions
workflow also defines unit-test and synthetic-demo jobs for Python 3.11–3.13;
remote CI status must be checked on the specific commit before claiming a pass.

Not verified: genuine provider telemetry, semantic answer quality, adversarial
security guarantees, production scale, deployment, or integration with the other
toolkit components. The tests establish the implemented deterministic behavior
within the documented input limits.
