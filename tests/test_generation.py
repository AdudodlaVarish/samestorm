import contextlib
import io
import json
import os
import sys
import tempfile
import types
import unittest
from enum import IntEnum
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'src')]
import scale_generate as generation
from samestorm.provenance import sha256


def response(text='Fixture response.', finish='stop'):
    return dict(choices=[dict(message=dict(content=text), finish_reason=finish)],
                timings=dict(cache_n=0, prompt_n=10, predicted_n=5))


class GenerationInputs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.packet = generation.prepare(ROOT)

    def test_complete_matrix_and_repeats_use_question_only_messages(self):
        self.assertEqual(len(self.packet['prompts']), 184)
        plan = self.packet['plan']
        self.assertEqual((len(plan['jobs']), plan['primary_answers'], plan['repeat_answers']), (12, 2208, 228))
        for job in plan['jobs']:
            cases = generation.generation_cases(self.packet, job)
            self.assertEqual(len(cases), 203)
            self.assertEqual(sum(repeat for _, repeat in cases), 19)
        for prompt in self.packet['prompts']:
            self.assertEqual(prompt['split'], 'dev')
            self.assertEqual([m['role'] for m in prompt['messages']], ['system', 'user'])
            self.assertEqual(set(prompt['messages'][1]), {'role', 'content'})
            self.assertNotIn('required_actions', prompt)
            self.assertNotIn('official_sources', prompt)
        self.assertFalse(plan['execution_authorized'])

    def test_generation_requires_explicit_recorded_review_and_unchanged_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'fixture.txt'
            path.write_text('Reviewed fixture')
            expected = {'fixture.txt': sha256(path)}
            review = dict(frozen=True, approved_by='student', approved_at='fixture-date',
                          keys_and_alignment_evidence_reviewed=True, question_translations_reviewed=True,
                          artifacts=expected)
            generation.assert_reviewed_inputs(root, review, expected)
            for changes in [dict(frozen=False), dict(approved_by=None), dict(approved_at=''),
                            dict(keys_and_alignment_evidence_reviewed=False), dict(artifacts={})]:
                with self.subTest(changes=changes), self.assertRaises(ValueError):
                    generation.assert_reviewed_inputs(root, dict(review, **changes), expected)
            path.write_text('Changed fixture')
            with self.assertRaises(ValueError):
                generation.assert_reviewed_inputs(root, review, expected)

    def test_gguf_requires_matching_successful_preparation_and_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'configs').mkdir()
            (root / 'configs/toolchain.json').write_text(json.dumps(dict(llama_cpp_commit='a' * 40)))
            path = root / 'model-Q4_K_M.gguf'
            path.write_bytes(b'Synthetic file, not a GGUF')
            job = dict(model_id='fixture', model_revision='b' * 40, precision='Q4_K_M', model_path=path.name)
            receipt = dict(stage='model-preparation-quantize', status='complete', model_id=job['model_id'],
                           model_revision=job['model_revision'], llama_cpp_commit='a' * 40,
                           outputs=[dict(path=path.name, quantization_type='Q4_K_M', sha256=sha256(path))])
            self.assertEqual(generation.verified_artifact(root, job, receipt), path)
            for changes in [dict(status='failed'), dict(model_revision='wrong'), dict(outputs=[]),
                            dict(llama_cpp_commit='wrong'), dict(stage='model-preparation-convert')]:
                with self.subTest(changes=changes), self.assertRaises(ValueError):
                    generation.verified_artifact(root, job, dict(receipt, **changes))
            path.write_bytes(b'Changed synthetic file')
            with self.assertRaises(ValueError):
                generation.verified_artifact(root, job, receipt)

    def test_bad_response_cache_thinking_or_finish_reason_is_rejected(self):
        self.assertFalse(generation.response_record(response())['runtime_failure'])
        self.assertTrue(generation.response_record(response(finish='length'))['generation_truncated'])
        invalid = [response(''), response(finish='unknown'), dict(response(), timings={})]
        cached = response()
        cached['timings']['cache_n'] = 1
        invalid.append(cached)
        thinking = response()
        thinking['choices'][0]['message']['reasoning_content'] = 'Unexpected thinking'
        invalid.append(thinking)
        for raw in invalid:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                generation.response_record(raw)

    def test_failures_raw_outputs_and_repeats_are_retained(self):
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            prompt = self.packet['prompts'][0]
            job = self.packet['plan']['jobs'][0]
            cases = [(prompt, 0), (prompt, 1), (self.packet['prompts'][1], 0)]
            invalid = response('')
            request = MagicMock(side_effect=[response(), invalid, OSError('Fixture connection failure')])
            record = dict(completed_answers=0, runtime_failures=0)
            generation.collect_answers(cases, job, request, run, record)
            rows = generation.read_rows(run / 'answers.jsonl')
            self.assertEqual([r['repeat_index'] for r in rows], [0, 1, 0])
            self.assertEqual([r['runtime_failure'] for r in rows], [False, True, True])
            self.assertEqual(rows[1]['response'], invalid)
            self.assertIn('Fixture connection failure', rows[2]['error'])
            self.assertEqual((record['completed_answers'], record['runtime_failures']), (3, 2))
            self.assertEqual(request.call_count, 3)

    def test_local_generation_is_rejected_before_gpu_commands(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(generation.subprocess, 'check_output') as command:
            with self.assertRaisesRegex(ValueError, 'no laptop fallback'):
                generation.hardware_probe(ROOT)
            command.assert_not_called()


class GenerationWorker(unittest.TestCase):
    def test_fake_server_preserves_protocol_and_cleans_processes(self):
        packet = generation.prepare(ROOT)
        job = packet['plan']['jobs'][0]
        # Exercise one primary response and its repeat without running a model.
        job = dict(job, primary_example_ids=job['primary_example_ids'][:1],
                   repeat_example_ids=job['primary_example_ids'][:1])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            toolchain = root / 'toolchain'
            (toolchain / 'build/bin').mkdir(parents=True)
            (toolchain / 'build/CMakeCache.txt').write_text('GGML_CUDA:BOOL=ON\n')
            (toolchain / 'build/bin/llama-server').write_bytes(b'Synthetic executable fixture')
            class FileType(IntEnum):
                MOSTLY_F16 = 1
            reader = MagicMock()
            reader.fields = {'general.file_type': MagicMock(), 'tokenizer.chat_template': MagicMock()}
            reader.fields['general.file_type'].contents.return_value = 1
            reader.fields['tokenizer.chat_template'].contents.return_value = 'Fixture chat template'
            gguf = types.SimpleNamespace(GGUFReader=MagicMock(return_value=reader), LlamaFileType=FileType)
            for full_offload in [True, False]:
                with self.subTest(full_offload=full_offload):
                    run = root / str(full_offload)
                    run.mkdir()
                    server, telemetry = MagicMock(), MagicMock()
                    server.poll.return_value = telemetry.poll.return_value = None
                    def start(command, **kwargs):
                        if 'llama-server' in command[0]:
                            kwargs['stdout'].write(f'offloaded {32 if full_offload else 0}/32 layers to GPU\n')
                            kwargs['stdout'].flush()
                            return server
                        return telemetry
                    health = MagicMock()
                    health.status = 200
                    reply = MagicMock()
                    reply.read.return_value = json.dumps(response()).encode()
                    requests = []
                    def http(req, **kwargs):
                        handle = MagicMock()
                        if isinstance(req, str):
                            handle.__enter__.return_value = health
                        else:
                            requests.append(json.loads(req.data))
                            handle.__enter__.return_value = reply
                        return handle
                    args = types.SimpleNamespace(run_id='fixture')
                    record = {}
                    with patch.dict(sys.modules, gguf=gguf), patch.object(generation, 'verify_toolchain', return_value=toolchain), \
                            patch.object(generation.importlib.metadata, 'version', return_value='fixture'), \
                            patch.object(generation.subprocess, 'Popen', side_effect=start), patch.object(generation, 'urlopen', side_effect=http):
                        if full_offload:
                            generation.run_server(args, packet, job, root / 'model.gguf', run, record)
                        else:
                            with self.assertRaisesRegex(ValueError, 'complete GPU layer offload'):
                                generation.run_server(args, packet, job, root / 'model.gguf', run, record)
                    server.terminate.assert_called_once()
                    telemetry.terminate.assert_called_once()
                    if full_offload:
                        self.assertEqual(len(generation.read_rows(run / 'answers.jsonl')), 2)
                        self.assertEqual([r['max_tokens'] for r in requests], [16, 320, 320])
                        for request in requests:
                            self.assertEqual(request['temperature'], 0)
                            self.assertEqual(request['top_k'], 1)
                            self.assertEqual(request['repeat_penalty'], 1)
                            self.assertFalse(request['cache_prompt'])
                            self.assertEqual(request['chat_template_kwargs'], {'enable_thinking': False})
                    else:
                        self.assertEqual(requests, [])

    def test_missing_review_inputs_produce_failed_manifest_without_inference(self):
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            with patch.object(generation, 'new_run_dir', return_value=run), \
                    patch.object(sys, 'argv', ['scale_generate.py', 'generate', '--run-id', 'blocked']), \
                    patch.object(generation, 'run_server') as server, contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(generation.main(), 1)
            server.assert_not_called()
            record = json.loads((run / 'manifest.json').read_text())
            self.assertEqual(record['status'], 'failed')
            self.assertFalse(record['benchmark_frozen'])
            self.assertIn('reviewed freeze manifest', record['error'])


if __name__ == '__main__':
    unittest.main()
