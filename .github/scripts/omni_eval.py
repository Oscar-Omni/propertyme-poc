"""Scoped adoption of Oscar-Omni/omni-ci-workflows' native eval contract."""
import json
import math
import os
from pathlib import Path
import signal
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

CONFIG = Path(__file__).with_name('omni_eval_config.json')


class EvalError(Exception):
    pass


def require(condition, message):
    if not condition:
        raise EvalError(message)


def identifier(value):
    try:
        return str(uuid.UUID(value))
    except (ValueError, TypeError, AttributeError):
        raise EvalError('Invalid identifier in configuration or API response') from None


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Client:
    def __init__(self, base_url, key):
        self.base_url = base_url
        self.key = key

    def call(self, method, path, body=None):
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(self.base_url + path, data=data, method=method,
            headers={'Authorization': 'Bearer ' + self.key, 'Content-Type': 'application/json'})
        for attempt in range(3):
            try:
                with urllib.request.build_opener(NoRedirect).open(request, timeout=30) as response:
                    return json.load(response)
            except urllib.error.HTTPError as error:
                if method == 'GET' and error.code in {429, 500, 502, 503, 504} and attempt < 2:
                    time.sleep(5 * (attempt + 1))
                    continue
                raise EvalError(f'Omni API {method} failed with HTTP {error.code}; inspect Omni privately') from None
            except (urllib.error.URLError, TimeoutError, ValueError):
                raise EvalError(f'Omni API {method} failed; a POST outcome may be uncertain, inspect Omni before retrying') from None


def resolve_branch(client, model_id, name):
    if not name:
        return None
    matches, cursor, seen = [], None, set()
    while True:
        query = {'modelKind': 'BRANCH', 'baseModelId': model_id, 'pageSize': '100'}
        if cursor:
            require(cursor not in seen, 'Repeated pagination cursor')
            seen.add(cursor)
            query['cursor'] = cursor
        page = client.call('GET', '/v1/models?' + urllib.parse.urlencode(query))
        matches.extend(r for r in page['records'] if r.get('baseModelId') == model_id and r.get('name') == name)
        info = page['pageInfo']
        if not info['hasNextPage']:
            break
        cursor = info.get('nextCursor')
        require(bool(cursor), 'Missing pagination cursor')
    require(len(matches) == 1, 'Expected exactly one matching Omni branch under the configured model')
    return identifier(matches[0]['id'])


def snapshot(prompt_set):
    prompts = prompt_set['prompts']
    require(0 < len(prompts) <= 25, 'Prompt set must contain 1 to 25 prompts')
    rows = {identifier(p['id']): (p['prompt_text'], p.get('expectation')) for p in prompts}
    require(len(rows) == len(prompts), 'Duplicate prompt IDs')
    return rows


def validate_run(run, model_id, set_id, branch_id, expected):
    require(run['model_id'] == model_id and run['prompt_set_id'] == set_id
            and run['branch_id'] == branch_id and run['repeat_count'] == 1,
            'Eval run model, prompt set, branch, or repeat mapping differs from request')
    require(run['status'] in {'RUNNING', 'COMPLETE', 'CANCELLED'}, 'Unknown run state')
    require(run['status'] != 'CANCELLED', 'Eval run was cancelled')
    results = run['results']
    ids = [r.get('eval_prompt_id') for r in results]
    require(len(ids) == len(set(ids)) and set(ids) == set(expected), 'Missing, extra, or duplicate prompt results')
    for row in results:
        require((row['prompt'], row.get('expectation')) == expected[row['eval_prompt_id']],
                'Prompt or expectation changed between suite preflight and run creation')
        require(row.get('repeat_index') in {None, 0}, 'Unexpected prompt repeat')
        require(row.get('error_reason') is None and row['agentic_job']['state'] not in {'FAILED', 'CANCELLED'},
                'Agent job failed or was cancelled; inspect the run in Omni')
        require(row['agentic_job']['state'] in {'QUEUED', 'EXECUTING', 'DELIVERING', 'COMPLETE', 'FAILED', 'CANCELLED'}, 'Unknown agent job state')
        require(row['score'] in {None, 0, 1}, 'Unexpected judge score; binary policy requires review')
        for field in ('cost', 'scoring_cost', 'query_count', 'timing_ms'):
            value = row.get(field)
            require(value is None or (isinstance(value, (int, float)) and math.isfinite(value) and value >= 0),
                    'Invalid numeric diagnostic in API response')
    return run['status'] == 'COMPLETE' and all(
        r['score'] is not None and r['agentic_job']['state'] == 'COMPLETE' for r in results)


def safe_run(run):
    fields = ('eval_prompt_id', 'score', 'cost', 'scoring_cost', 'query_count', 'timing_ms')
    return {'id': identifier(run['id']), 'prompt_set_id': identifier(run['prompt_set_id']),
        'branch_id': run['branch_id'], 'status': run['status'],
        'results': [{**{k: r.get(k) for k in fields},
            'conversation_id': identifier(r['agentic_job']['conversation_id'])
                if r['agentic_job'].get('conversation_id') else None,
            'job_state': r['agentic_job']['state']} for r in run['results']]}


def execute_run(client, model_id, set_id, branch_id, expected, evidence, active, timeout=900):
    body = {'prompt_set_id': set_id, 'description': 'Maintenance CI native accuracy comparison',
            'run_config': {'repeat_count': 1}}
    if branch_id:
        body['run_config']['branch_id'] = branch_id
    response = client.call('POST', '/v1/ai/eval/runs', body)
    run = response['run']
    run_id = identifier(run['id'])
    active.add(run_id)
    evidence.append({'id': run_id, 'prompt_set_id': set_id, 'branch_id': branch_id, 'status': 'CREATED'})
    require(response['job_count'] == len(expected), 'Eval did not create every expected prompt execution')
    deadline, completed_at, interval = time.monotonic() + timeout, None, 5
    while True:
        try:
            require(identifier(run['id']) == run_id, 'Polled run ID differs from the created run ID')
            settled = validate_run(run, model_id, set_id, branch_id, expected)
        except EvalError:
            evidence[-1]['validation_failed'] = True
            raise
        evidence[-1] = safe_run(run)
        if settled:
            active.remove(run_id)
            return run
        now = time.monotonic()
        if run['status'] == 'COMPLETE' and completed_at is None:
            completed_at = now
        require(now < deadline, 'Eval polling timed out')
        require(completed_at is None or now - completed_at < 180, 'Run completed without all scores within scoring grace')
        time.sleep(min(interval, max(0, deadline - now)))
        interval = min(interval * 2, 20)
        run = client.call('GET', '/v1/ai/eval/runs/' + run_id)['run']


def compare(baseline, candidate):
    before = {r['eval_prompt_id']: r for r in baseline['results']}
    after = {r['eval_prompt_id']: r for r in candidate['results']}
    require(set(before) == set(after), 'Baseline and candidate prompt IDs differ')
    return [{'prompt_id': key, 'baseline': before[key]['score'], 'candidate': after[key]['score'],
        'regressed': before[key]['score'] == 1 and after[key]['score'] == 0} for key in sorted(before)]


def write_report(report, directory):
    directory.mkdir(parents=True, exist_ok=True)
    data = json.dumps(report, indent=2)
    (directory / 'results.json').write_text(data + '\n')
    lines = ['# Maintenance native Omni eval', '', f"Outcome: {report['outcome']}", '',
             'Native accuracy judge only. Clarification order requires a separate private conversation audit.',
             'No prompts, expectations, raw responses, error bodies, or credentials are exported.', '']
    if report.get('error'):
        lines.extend([report['error'], ''])
    for item in report['comparisons']:
        lines.extend([f"## Suite `{item['prompt_set_id']}`", '',
            '| Prompt ID | Baseline | Candidate | Regression |', '|---|---:|---:|---|'])
        for row in item['rows']:
            lines.append(f"| {row['prompt_id']} | {row['baseline']} | {row['candidate']} | {row['regressed']} |")
    for run in report['runs']:
        results = run.get('results', [])
        passed = sum(row.get('score') == 1 for row in results)
        scored = sum(row.get('score') is not None for row in results)
        spend = sum((row.get('cost') or 0) + (row.get('scoring_cost') or 0) for row in results)
        lines.extend(['', f"Run `{run['id']}`, branch `{run['branch_id']}`, state `{run['status']}`.",
            f'Passed {passed}/{scored} scored executions. Recorded answer + judge cost USD {spend:.4f}.'])
    (directory / 'summary.md').write_text('\n'.join(lines) + '\n')
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as output:
            output.write('\n'.join(lines) + '\n')


def main():
    report = {'outcome': 'operational failure', 'runs': [], 'comparisons': []}
    active, client = set(), None
    exit_code = 2
    try:
        cfg = json.loads(CONFIG.read_text())
        require(cfg['enabled'], 'CI configuration is pending verified prompt-set IDs and approved secrets')
        model_id = identifier(cfg['model_id'])
        require(os.environ.get('OMNI_BASE_URL', '').rstrip('/') == cfg['api_base_url'], 'OMNI_BASE_URL must match the approved target API base URL')
        require(bool(os.environ.get('OMNI_API_KEY')), 'Missing GitHub Actions secret OMNI_API_KEY')
        sets = cfg['prompt_sets']
        require(0 < len(sets) <= 3, 'Expected 1 to 3 maintenance suites')
        require(len({identifier(s['id']) for s in sets}) == len(sets), 'Duplicate suite IDs')
        client = Client(cfg['api_base_url'], os.environ['OMNI_API_KEY'])
        baseline_id = resolve_branch(client, model_id, os.environ.get('BASELINE_BRANCH_NAME', ''))
        candidate_name = os.environ.get('BRANCH_NAME', '')
        require(bool(candidate_name), 'Candidate Omni branch name is required')
        candidate_id = resolve_branch(client, model_id, candidate_name)
        require(baseline_id != candidate_id, 'Baseline and candidate must differ')
        report.update(model_id=model_id, baseline_branch_id=baseline_id, candidate_branch_id=candidate_id)
        suites = []
        for suite in sets:
            current = client.call('GET', '/v1/ai/eval/prompt-sets/' + identifier(suite['id']))['prompt_set']
            require(current['model_id'] == model_id and not current['is_archived'] and current['slug'] == suite['slug'], 'Prompt set is archived or belongs to another model or slug')
            expected = snapshot(current)
            require(len(expected) == suite['prompt_count'], 'Prompt count changed; review suite before spending')
            suites.append((suite, expected))
        for suite, expected in suites:
            baseline = execute_run(client, model_id, suite['id'], baseline_id, expected, report['runs'], active)
            candidate = execute_run(client, model_id, suite['id'], candidate_id, expected, report['runs'], active)
            report['comparisons'].append({'prompt_set_id': suite['id'], 'rows': compare(baseline, candidate)})
        regressed = any(r['regressed'] for s in report['comparisons'] for r in s['rows'])
        report['outcome'] = 'regression' if regressed else 'no regressions'
        exit_code = 1 if regressed else 0
    except EvalError as error:
        report['error'] = str(error)
    except (KeyError, TypeError, ValueError, OSError):
        report['error'] = 'Invalid configuration or API response; inspect Omni privately'
    finally:
        for run_id in sorted(active):
            try:
                client.call('POST', '/v1/ai/eval/runs/' + run_id + '/cancel')
                report.setdefault('cleanup', []).append({'run_id': run_id, 'cancellation': 'requested'})
            except EvalError:
                report.setdefault('cleanup', []).append({'run_id': run_id, 'cancellation': 'uncertain; inspect Omni before retrying'})
        write_report(report, Path('omni-eval-artifacts'))
    return exit_code


if __name__ == '__main__':
    def interrupted(_signum, _frame):
        raise EvalError('Runner interrupted; cancellation will be attempted for known run IDs')
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    raise SystemExit(main())
