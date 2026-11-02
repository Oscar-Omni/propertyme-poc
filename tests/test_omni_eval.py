import importlib.util
import json
import os
import urllib.error
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('eval_runner', Path(__file__).parents[1] / '.github/scripts/omni_eval.py')
eval_runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(eval_runner)
MODEL = '00000000-0000-0000-0000-000000000001'
SET = '00000000-0000-0000-0000-000000000002'
BRANCH = '00000000-0000-0000-0000-000000000003'
PROMPT = '00000000-0000-0000-0000-000000000004'
RUN = '00000000-0000-0000-0000-000000000005'
CONVERSATION = '00000000-0000-0000-0000-000000000006'
EXPECTED = {PROMPT: ('private prompt', 'private expectation')}


def run(score=1, state='COMPLETE', branch=BRANCH):
    return {'id': RUN, 'model_id': MODEL, 'prompt_set_id': SET, 'branch_id': branch,
        'repeat_count': 1, 'status': state, 'results': [{'eval_prompt_id': PROMPT,
        'prompt': 'private prompt', 'expectation': 'private expectation', 'score': score,
        'error_reason': None, 'repeat_index': 0, 'cost': 0.1, 'scoring_cost': 0.01,
        'agentic_job': {'state': 'COMPLETE', 'conversation_id': CONVERSATION}}]}


class NativeEvalContractTests(unittest.TestCase):
    def test_regression_fails_even_when_other_prompts_improve(self):
        baseline, candidate = run(branch=None), run(score=0)
        for number in (7, 8):
            prompt_id = f'00000000-0000-0000-0000-{number:012d}'
            baseline['results'].append({'eval_prompt_id': prompt_id, 'score': 0})
            candidate['results'].append({'eval_prompt_id': prompt_id, 'score': 1})
        rows = eval_runner.compare(baseline, candidate)
        self.assertGreater(sum(r['candidate'] for r in rows), sum(r['baseline'] for r in rows))
        self.assertEqual([r['prompt_id'] for r in rows if r['regressed']], [PROMPT])

    def test_preexisting_failure_is_not_a_regression(self):
        self.assertFalse(eval_runner.compare(run(score=0, branch=None), run(score=0))[0]['regressed'])

    def test_operational_failures_never_pass(self):
        variants = []
        for key, value in [('model_id', SET), ('branch_id', None), ('prompt_set_id', MODEL),
                           ('status', 'CANCELLED'), ('repeat_count', 2)]:
            item = run(); item[key] = value; variants.append(item)
        for key, value in [('score', 0.9), ('error_reason', 'private failure'),
                           ('prompt', 'changed'), ('expectation', 'changed')]:
            item = run(); item['results'][0][key] = value; variants.append(item)
        item = run(); item['results'] = []; variants.append(item)
        item = run(); item['results'] *= 2; variants.append(item)
        item = run(); item['results'][0]['agentic_job']['state'] = 'FAILED'; variants.append(item)
        item = run(); item['results'][0]['cost'] = 'private response'; variants.append(item)
        for item in variants:
            with self.subTest(item=item), self.assertRaises(eval_runner.EvalError):
                eval_runner.validate_run(item, MODEL, SET, BRANCH, EXPECTED)

    def test_complete_without_score_waits_and_eventually_settles(self):
        class Client:
            calls = []
            def call(self, method, path, body=None):
                self.calls.append((method, path, body))
                return {'job_count': 1, 'run': run(score=None)} if method == 'POST' else {'run': run()}
        client = Client(); active = set(); evidence = []
        with patch.object(eval_runner.time, 'sleep'):
            result = eval_runner.execute_run(client, MODEL, SET, BRANCH, EXPECTED, evidence, active)
        self.assertEqual(result['results'][0]['score'], 1)
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(active, set())
        self.assertEqual(client.calls[0][2]['run_config']['branch_id'], BRANCH)
        self.assertNotIn('private', json.dumps(evidence))

    def test_polling_rejects_a_different_run_id(self):
        class Client:
            def call(self, method, *args):
                if method == 'POST':
                    return {'job_count': 1, 'run': run(score=None)}
                unexpected = run()
                unexpected['id'] = SET
                return {'run': unexpected}
        evidence, active = [], set()
        with patch.object(eval_runner.time, 'sleep'):
            with self.assertRaisesRegex(eval_runner.EvalError, 'run ID'):
                eval_runner.execute_run(Client(), MODEL, SET, BRANCH, EXPECTED, evidence, active)
        self.assertEqual(active, {RUN})
        self.assertEqual(evidence[-1]['id'], RUN)
        self.assertTrue(evidence[-1]['validation_failed'])

    def test_missing_scores_exhaust_grace_as_failure(self):
        class Client:
            def call(self, *args):
                return {'job_count': 1, 'run': run(score=None)}
        with patch.object(eval_runner.time, 'sleep'), patch.object(eval_runner.time, 'monotonic', side_effect=[0, 0, 181]):
            with self.assertRaisesRegex(eval_runner.EvalError, 'scoring grace'):
                eval_runner.execute_run(Client(), MODEL, SET, BRANCH, EXPECTED, [], set())

    def test_duplicate_branch_names_fail_instead_of_selecting_latest(self):
        class Client:
            def call(self, *args):
                return {'records': [{'id': BRANCH, 'name': 'oscar/test', 'baseModelId': MODEL}] * 2,
                        'pageInfo': {'hasNextPage': False}}
        with self.assertRaises(eval_runner.EvalError):
            eval_runner.resolve_branch(Client(), MODEL, 'oscar/test')

    def test_summary_and_artifacts_exclude_prompt_and_expectation(self):
        report = {'outcome': 'no regressions', 'runs': [eval_runner.safe_run(run())], 'comparisons': []}
        with tempfile.TemporaryDirectory() as directory:
            eval_runner.write_report(report, Path(directory))
            for file in Path(directory).iterdir():
                self.assertNotIn('private prompt', file.read_text())
                self.assertNotIn('private expectation', file.read_text())
            self.assertIn(CONVERSATION, (Path(directory) / 'results.json').read_text())

    def test_pending_config_cannot_start_api_calls(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(eval_runner, 'Client') as client:
            with patch.object(eval_runner, 'CONFIG') as config, patch.object(eval_runner, 'write_report'):
                config.read_text.return_value = '{"enabled":false}'
                self.assertEqual(eval_runner.main(), 2)
                client.assert_not_called()

    def test_main_exit_codes_and_branch_mapping(self):
        for candidate_score, expected_exit in [(1, 0), (0, 1)]:
            calls = []
            class Client:
                def __init__(self, *args):
                    pass
                def call(self, method, path, body=None):
                    calls.append((method, path, body))
                    if path.startswith('/v1/models?'):
                        return {'records': [{'id': BRANCH, 'name': 'oscar/test', 'baseModelId': MODEL}],
                                'pageInfo': {'hasNextPage': False}}
                    if '/prompt-sets/' in path:
                        return {'prompt_set': {'model_id': MODEL, 'slug': 'suite', 'is_archived': False,
                            'prompts': [{'id': PROMPT, 'prompt_text': 'private prompt', 'expectation': 'private expectation'}]}}
                    branch = body['run_config'].get('branch_id')
                    return {'job_count': 1, 'run': run(score=candidate_score if branch else 1, branch=branch)}
            cfg = {'enabled': True, 'model_id': MODEL, 'api_base_url': 'https://propertyme-poc.omniapp.co/api',
                   'prompt_sets': [{'id': SET, 'slug': 'suite', 'prompt_count': 1}]}
            with patch.object(eval_runner, 'CONFIG') as config, patch.object(eval_runner, 'Client', Client), patch.object(eval_runner, 'write_report') as output:
                config.read_text.return_value = json.dumps(cfg)
                with patch.dict(os.environ, {'OMNI_API_KEY': 'test-secret', 'OMNI_BASE_URL': cfg['api_base_url'],
                                             'BRANCH_NAME': 'oscar/test', 'BASELINE_BRANCH_NAME': ''}):
                    self.assertEqual(eval_runner.main(), expected_exit)
                report = output.call_args.args[0]
                self.assertEqual(report['baseline_branch_id'], None)
                self.assertEqual(report['candidate_branch_id'], BRANCH)
                self.assertNotIn('test-secret', json.dumps(report))
                posts = [body for method, _, body in calls if method == 'POST']
                self.assertEqual(len(posts), 2)
                self.assertNotIn('branch_id', posts[0]['run_config'])
                self.assertEqual(posts[1]['run_config']['branch_id'], BRANCH)

    def test_api_error_does_not_export_response_body_or_key(self):
        error = urllib.error.HTTPError('https://propertyme-poc.omniapp.co/api', 403,
                                      'private response', {}, None)
        with patch.object(eval_runner.urllib.request, 'build_opener') as opener:
            opener.return_value.open.side_effect = error
            with self.assertRaises(eval_runner.EvalError) as caught:
                eval_runner.Client('https://propertyme-poc.omniapp.co/api', 'test-secret').call('POST', '/v1/ai/eval/runs')
            self.assertNotIn('private response', str(caught.exception))
            self.assertNotIn('test-secret', str(caught.exception))
            self.assertEqual(opener.return_value.open.call_count, 1)

    def test_operational_failure_cancels_known_active_run_and_exports_receipt(self):
        class Client:
            def __init__(self, *args):
                pass
            def call(self, method, path, body=None):
                if path.startswith('/v1/models?'):
                    return {'records': [{'id': BRANCH, 'name': 'oscar/test', 'baseModelId': MODEL}],
                            'pageInfo': {'hasNextPage': False}}
                if '/prompt-sets/' in path:
                    return {'prompt_set': {'model_id': MODEL, 'slug': 'suite', 'is_archived': False,
                        'prompts': [{'id': PROMPT, 'prompt_text': 'private prompt', 'expectation': 'private expectation'}]}}
                if path.endswith('/cancel'):
                    return {}
                result = run(branch=None)
                result['results'][0]['agentic_job']['state'] = 'FAILED'
                return {'job_count': 1, 'run': result}
        cfg = {'enabled': True, 'model_id': MODEL, 'api_base_url': 'https://propertyme-poc.omniapp.co/api',
               'prompt_sets': [{'id': SET, 'slug': 'suite', 'prompt_count': 1}]}
        with patch.object(eval_runner, 'CONFIG') as config, patch.object(eval_runner, 'Client', Client), patch.object(eval_runner, 'write_report') as output:
            config.read_text.return_value = json.dumps(cfg)
            with patch.dict(os.environ, {'OMNI_API_KEY': 'test-secret', 'OMNI_BASE_URL': cfg['api_base_url'],
                                         'BRANCH_NAME': 'oscar/test', 'BASELINE_BRANCH_NAME': ''}):
                self.assertEqual(eval_runner.main(), 2)
            report = output.call_args.args[0]
            self.assertEqual(report['cleanup'], [{'run_id': RUN, 'cancellation': 'requested'}])
            self.assertTrue(report['runs'][0]['validation_failed'])
            self.assertNotIn('private prompt', json.dumps(report))

    def test_redirects_do_not_forward_authorization(self):
        self.assertIsNone(eval_runner.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://example.com'))


if __name__ == '__main__':
    unittest.main()
