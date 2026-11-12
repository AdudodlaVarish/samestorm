import contextlib
import copy
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import types
import unittest
from enum import IntEnum
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'src')]
import fertility
import throughput
import estimate_runtime as runtime
from samestorm.provenance import sha256


def bench_rows():
    return [dict(n_prompt=p, n_gen=n, n_gpu_layers=99, samples_ts=[rate] * 5, avg_ts=rate)
            for p, n, rate in [(512, 0, 1000), (0, 128, 100)]]


TELEMETRY = ('timestamp, name, clocks.current.sm [MHz], temperature.gpu, power.draw [W], memory.used [MiB]\n'
             'fixture, A100, 1200, 50, 100, 2000\nfixture, A100, 1300, 55, 120, 2400\n')


class TokenizerMeasurements(unittest.TestCase):
    def test_question_and_chat_counts_use_language_matched_english(self):
        prompts = [dict(example_id=i + ':' + lang, item_id=i, lang=lang,
                        messages=[dict(role='system', content='System'), dict(role='user', content=text)])
                   for i, lang, text in [('a', 'en', 'e' * 10), ('b', 'en', 'e' * 100),
                                          ('a', 'es', 's' * 20), ('b', 'es', 's' * 20), ('a', 'zh', '中' * 5)]]
        tokenizer = MagicMock()
        tokenizer.encode.side_effect = lambda text, **kw: list(range(len(text)))
        tokenizer.apply_chat_template.side_effect = lambda messages, **kw: list(range(len(messages[1]['content']) + 10))
        rows, summaries = fertility.measure(tokenizer, prompts)
        zh = next(r for r in summaries if r['lang'] == 'zh')
        self.assertEqual(zh['paired_english_tokens'], 10)
        self.assertEqual(zh['total_tokens_relative_to_en'], .5)
        self.assertEqual(rows[0]['chat_prompt_tokens'], 20)
        self.assertFalse(tokenizer.encode.call_args.kwargs['add_special_tokens'])
        self.assertFalse(tokenizer.apply_chat_template.call_args.kwargs['enable_thinking'])
        self.assertFalse(tokenizer.apply_chat_template.call_args.kwargs['truncation'])

    def test_tokenizer_only_hash_verification_does_not_require_weights(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / 'tokenizer'
            folder.mkdir()
            body = b'{"fixture":true}'
            (folder / 'tokenizer.json').write_bytes(body)
            blob = hashlib.sha1(b'blob ' + str(len(body)).encode() + b'\0' + body).hexdigest()
            metadata = dict(id='fixture', sha='a' * 40, siblings=[dict(rfilename='tokenizer.json', blobId=blob),
                            dict(rfilename='model.safetensors'), dict(rfilename='model.safetensors.index.json')])
            path = root / 'metadata.json'
            path.write_text(json.dumps(metadata))
            model = dict(id='fixture', revision='a' * 40, metadata_path='metadata.json', metadata_sha256=sha256(path))
            self.assertEqual(set(fertility.verify_tokenizer(root, model, folder)), {'tokenizer.json'})
            (folder / 'tokenizer.json').write_text('changed')
            with self.assertRaises(ValueError):
                fertility.verify_tokenizer(root, model, folder)


class ThroughputMeasurements(unittest.TestCase):
    def test_protocol_keeps_warmup_and_checks_both_workloads(self):
        command = throughput.bench_command(Path('llama-bench'), Path('model.gguf'))
        self.assertNotIn('--no-warmup', command)
        self.assertEqual(command[command.index('-r') + 1], '5')
        self.assertEqual(command[command.index('-ngl') + 1], '99')
        self.assertEqual(throughput.check_results(bench_rows()),
                         dict(prefill_tokens_per_second=1000, decode_tokens_per_second=100))
        for field, value in [('samples_ts', [1]), ('avg_ts', float('nan')), ('avg_ts', 0), ('n_gpu_layers', 0)]:
            rows = bench_rows()
            rows[0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                throughput.check_results(rows)

    def test_telemetry_requires_all_fields_and_reports_observed_peaks(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'gpu.csv'
            path.write_text(TELEMETRY)
            result = throughput.telemetry_summary(path)
            self.assertEqual(result['samples'], 2)
            self.assertEqual(result['observed_peaks']['memory.used [MiB]'], 2400)
            path.write_text(TELEMETRY.replace(', 100,', ', N/A,').replace(', 120,', ', N/A,'))
            with self.assertRaises(ValueError):
                throughput.telemetry_summary(path)

    def test_mocked_benchmark_retains_failed_outputs_and_cleans_telemetry(self):
        real_run = subprocess.run
        real_popen = subprocess.Popen
        class FileType(IntEnum):
            MOSTLY_F16 = 1
        reader = MagicMock()
        reader.fields = {'general.file_type': MagicMock()}
        reader.fields['general.file_type'].contents.return_value = 1
        gguf = types.SimpleNamespace(GGUFReader=MagicMock(return_value=reader), LlamaFileType=FileType)
        for succeeds in [True, False]:
            with self.subTest(succeeds=succeeds), tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                run = base / 'run'
                run.mkdir()
                toolchain = base / 'toolchain'
                (toolchain / 'build/bin').mkdir(parents=True)
                (toolchain / 'build/CMakeCache.txt').write_text('GGML_CUDA:BOOL=ON\n')
                (toolchain / 'build/bin/llama-bench').write_bytes(b'Synthetic executable fixture')
                model = base / 'model.gguf'
                model.write_bytes(b'Synthetic GGUF fixture')
                prep = base / 'preparation.json'
                prep.write_text('{}')
                telemetry = MagicMock()
                telemetry.poll.return_value = None
                def start(command, **kw):
                    if command[0] == 'git':
                        return real_popen(command, **kw)
                    kw['stdout'].write(TELEMETRY)
                    kw['stdout'].flush()
                    return telemetry
                def execute(command, **kw):
                    if command[0] == 'git':
                        return real_run(command, **kw)
                    for row in bench_rows() if succeeds else bench_rows()[:1]:
                        kw['stdout'].write(json.dumps(row) + '\n')
                    kw['stderr'].write('offloaded 33/33 layers to GPU\n')
                    return types.SimpleNamespace(returncode=0 if succeeds else 1)
                with patch.object(throughput, 'new_run_dir', return_value=run), \
                        patch.object(throughput, 'hardware_probe', return_value={'fixture': 'hardware'}), \
                        patch.object(throughput, 'verified_artifact', return_value=model), \
                        patch.object(throughput, 'verify_toolchain', return_value=toolchain), \
                        patch.dict(sys.modules, gguf=gguf), patch.object(throughput.subprocess, 'Popen', side_effect=start), \
                        patch.object(throughput.subprocess, 'run', side_effect=execute), \
                        patch.object(sys, 'argv', ['throughput.py', 'measure', '--run-id', 'fixture', '--model-manifest', str(prep)]), \
                        contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(throughput.main(), 0 if succeeds else 1)
                telemetry.terminate.assert_called_once()
                record = json.loads((run / 'manifest.json').read_text())
                self.assertEqual(record['status'], 'complete' if succeeds else 'failed')
                self.assertTrue((run / 'bench.jsonl').read_text())
                self.assertTrue((run / 'gpu.csv').is_file())


class RuntimeEstimates(unittest.TestCase):
    def setUp(self):
        self.packet = dict(prompts=[dict(example_id='a:en'), dict(example_id='a:es')],
            plan=dict(settings=dict(decoding=dict(max_tokens=320)), jobs=[dict(job_index=0,
                model_id='fixture', model_revision='a' * 40, precision='F16',
                primary_example_ids=['a:en', 'a:es'], repeat_example_ids=['a:es'])]))
        self.model = ('fixture', 'a' * 40)
        self.cell = (*self.model, 'F16')
        self.counts = {self.model: {eid: dict(chat_prompt_tokens=n, context_overflow=False)
                                  for eid, n in [('a:en', 10), ('a:es', 20)]}}
        self.rates = {self.cell: dict(prefill_tokens_per_second=100, decode_tokens_per_second=10, allocated_gpus=3)}

    def test_generation_budget_counts_repeats_and_allocated_gpus(self):
        report = runtime.estimate(self.packet, self.counts, self.rates)
        self.assertTrue(report['generation_estimate_complete'])
        self.assertEqual(report['jobs'][0]['prompt_tokens'], 50)
        self.assertEqual(report['jobs'][0]['output_token_cap'], 960)
        self.assertEqual(report['generation_only_total_seconds'], 96.5)
        self.assertAlmostEqual(report['generation_only_allocated_a100_hours'], 96.5 * 3 / 3600)
        self.assertFalse(report['full_campaign_estimate_available'])

    def test_missing_measurements_and_context_overflow_do_not_become_zero_cost(self):
        for counts, rates in [({}, {}), (self.counts, {})]:
            with self.subTest(counts=counts, rates=rates):
                report = runtime.estimate(self.packet, counts, rates)
                self.assertFalse(report['generation_estimate_complete'])
                self.assertIsNone(report['generation_only_total_seconds'])
                self.assertIsNone(report['full_campaign_a100_hours'])
        changed = copy.deepcopy(self.counts)
        changed[self.model]['a:es']['context_overflow'] = True
        report = runtime.estimate(self.packet, changed, self.rates)
        self.assertEqual(report['jobs'][0]['missing'], ['context_overflow_requires_resolution'])

    def test_stale_changed_or_failed_measurement_files_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'measurement.json'
            path.write_text('{}')
            saved = dict(stage='throughput-measure', status='complete', outputs={'measurement.json': sha256(path)})
            (root / 'manifest.json').write_text(json.dumps(saved))
            runtime.verified_output(root, 'throughput-measure', 'measurement.json')
            path.write_text('changed')
            with self.assertRaises(ValueError):
                runtime.verified_output(root, 'throughput-measure', 'measurement.json')
            saved['status'] = 'failed'
            (root / 'manifest.json').write_text(json.dumps(saved))
            with self.assertRaises(ValueError):
                runtime.verified_output(root, 'throughput-measure', 'measurement.json')

    def test_no_measurement_command_reports_pending_without_inference(self):
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            with patch.object(runtime, 'new_run_dir', return_value=run), \
                    patch.object(sys, 'argv', ['estimate_runtime.py', '--run-id', 'pending']), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(runtime.main(), 0)
            report = json.loads((run / 'runtime_estimate.json').read_text())
            self.assertEqual((report['measured_cells'], report['total_cells']), (0, 12))
            self.assertIsNone(report['generation_only_total_seconds'])


if __name__ == '__main__':
    unittest.main()
