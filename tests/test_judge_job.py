import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
JOB = ROOT / 'scripts/jobs/judges.sbatch'


class CombinedJudgeJob(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.directory = Path(temp.name)
        self.calls = self.directory / 'calls.jsonl'
        worker = self.directory / 'fake python'
        worker.write_text(f'#!{sys.executable}\n' + '''import json, os, sys
from pathlib import Path
with Path(os.environ['TEST_CALLS']).open('a') as stream:
    stream.write(json.dumps(sys.argv[1:]) + '\\n')
if '--judge-role' in sys.argv and sys.argv[sys.argv.index('--judge-role') + 1] == os.environ.get('TEST_FAIL_ROLE'):
    sys.exit(7)
''')
        worker.chmod(0o755)
        self.environment = dict(os.environ, SAMESTORM_REPO=str(self.directory),
            SAMESTORM_PYTHON=str(worker), SLURM_JOB_ID='fixture',
            SAMESTORM_PRIMARY_JUDGE_DIR='/pinned primary',
            SAMESTORM_SECONDARY_JUDGE_DIR='/pinned secondary',
            SAMESTORM_TASKS='/validation packets.jsonl', SAMESTORM_TASK_KIND='validation',
            SAMESTORM_OFFSET='2', SAMESTORM_LIMIT='10', TEST_CALLS=str(self.calls), TEST_FAIL_ROLE='')

    def execute(self, **changes):
        result = subprocess.run(['bash', str(JOB), 'validate'],
            env={**self.environment, **changes}, capture_output=True, text=True)
        calls = [json.loads(line) for line in self.calls.read_text().splitlines()] if self.calls.exists() else []
        return result, calls

    def test_two_judges_then_comparison_in_one_job(self):
        result, calls = self.execute()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(calls), 3)
        for call, role in zip(calls[:2], ['primary', 'secondary']):
            self.assertEqual(call, ['scripts/scale_judge.py', 'judge',
                '--run-id', f'judge-fixture-judge-{role}', '--judge-role', role,
                '--model-dir', '/pinned ' + role, '--input', '/validation packets.jsonl',
                '--task-kind', 'validation', '--offset', '2', '--limit', '10'])
        self.assertEqual(calls[2], ['scripts/validate_judges.py', '--run-id', 'judge-fixture-comparison',
            '--primary', 'results/raw/judge-fixture-judge-primary/judgments.jsonl',
            '--secondary', 'results/raw/judge-fixture-judge-secondary/judgments.jsonl'])

    def test_failure_stops_later_stages(self):
        for role, expected in [('primary', 1), ('secondary', 2)]:
            self.calls.unlink(missing_ok=True)
            result, calls = self.execute(TEST_FAIL_ROLE=role)
            self.assertEqual(result.returncode, 7)
            self.assertEqual(len(calls), expected)

    def test_missing_checkpoint_or_wrong_task_kind_fails_before_workers(self):
        for changes in [dict(SAMESTORM_SECONDARY_JUDGE_DIR=''), dict(SAMESTORM_TASK_KIND='crossgrade')]:
            with self.subTest(changes=changes):
                result, calls = self.execute(**changes)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(calls, [])
