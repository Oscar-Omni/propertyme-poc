# Maintenance native eval CI

This copies the contract from [Oscar's native eval template](https://github.com/Oscar-Omni/omni-ci-workflows/tree/8e027501cf87f462af283f488c5ec5ad0c3f342f/workflows/omni-ai-eval) into this repository. The template is a copy-in library rather than a `workflow_call` workflow. Its consumers are unchanged.

## Configuration

`.github/scripts/omni_eval_config.json` is disabled until native prompt-set IDs are verified. The three maintenance suites contain 7 ambiguity prompts, 5 clear controls, and 4 clarified-definition controls. Null IDs are deliberate placeholders, not runnable identifiers.

The target is the PropertyMe MotherDuck model `2adbbe65-82d1-4c75-914d-9a8b32db3a3d` at `https://propertyme-poc.omniapp.co`. The candidate defaults to the existing Omni branch `oscar/test`. Prompt sets bind to the shared model; each eval run supplies its branch. The runner verifies this mapping from the API response. It never changes model context or YAML.

After reviewing the prompt sets, fill their actual IDs, slugs and counts in configuration. Separately approve and configure these GitHub Actions secrets:

| Name | Required target |
|---|---|
| `OMNI_API_KEY` | An approved identity with native eval and model-read access on the PropertyMe instance |
| `OMNI_BASE_URL` | Exactly `https://propertyme-poc.omniapp.co/api` |

Do not put credential values in configuration, logs, issues, or artifacts. Do not reuse credentials from another instance. This change creates no API key, OAuth flow, or secrets. Enable configuration only after the target, suite IDs, model/query prerequisites and secrets are verified.

## Running and interpreting

The paid workflow has only `workflow_dispatch`, and executes only on `main`. It cannot run the draft branch. No recurring or PR eval trigger is enabled. The separate offline check workflow uses no Omni secrets and runs contract tests on relevant PRs and pushes.

The manual `branch_name` selects an existing candidate Omni branch. Empty `baseline_branch_name` means live shared main; supply an existing baseline branch for an explicit comparison. Identical branch IDs are rejected. Confirm the intended Git state is already synced to Omni before dispatch: this runner does not upload YAML or prove that a Git commit was deployed. It resolves branch names within the exact shared model and rejects ambiguous matches.

Each suite runs baseline then candidate, with one repeat, one run at a time. Both runs must retain the same prompt IDs and text/expectation snapshots. Results are joined by prompt ID rather than prompt text or API ordering. Baseline and candidate must have comparable topic, data and provider settings for a meaningful experiment. No context intervention is created automatically.

Exit codes:

- `0`: all jobs and scores completed, with no new per-prompt regressions.
- `1`: at least one baseline pass became a candidate failure.
- `2`: operational failure, including a wrong mapping, prompt drift, duplicate/missing result, cancelled/failed job, missing score, API error or timeout.

A prompt that fails both arms remains visible but is not a new regression. Cost changes never gate. Native semantic accuracy does not establish correct clarification ordering. Audit ordered actions privately to verify that ambiguous prompts ask for missing definitions and stop before querying or ranking. The clarified-definition prompts are standalone controls; they do not share conversation history with other eval prompts.

## Diagnostics and limits

GitHub's step summary reports the outcome and per-prompt score changes. Seven-day artifacts contain allowlisted scores, costs, timings, run/branch/prompt IDs and conversation IDs for private inspection. Raw prompts, expectations, answers, SQL and error bodies are excluded. No PR comment is posted.

The workflow uses read-only repository permission, pinned official actions, and checkout without persisted credentials. It never executes fork PR code with Omni secrets and has no `pull_request_target` trigger. API redirects cannot forward bearer credentials. API POSTs are never retried automatically because a lost response may hide a successful write. GET transient HTTP retries are bounded.

Repository concurrency queues runs without cancelling an active comparison. Each native run has a 900-second polling deadline; asynchronous scoring receives up to 180 seconds within that deadline. The job timeout is 100 minutes for at most six sequential runs. Failure/interruption attempts cancellation of known active runs. A hard runner kill, lost creation response, or failed cancellation can leave an uncertain remote outcome. Inspect Omni before retrying; a different workflow or user can still occupy the service's concurrency allowance.

The current IDE warning concerns an unused root view, while Maintenance Jobs references a separate physically bound canonical view. That warning alone does not prove maintenance queries fail. Validate the target model and numerical controls separately before paid runs, and preserve model/context state. This CI change does not repair or delete model definitions.

## Verification

```sh
python -m unittest discover -s tests -v
python -m py_compile .github/scripts/omni_eval.py
zizmor --no-progress --format plain .github/workflows
```

Offline verification is separate from an authenticated native eval. A green offline workflow does not prove target credentials, native prompt-set persistence, topic execution or numerical answers.
