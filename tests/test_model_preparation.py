import hashlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import prepare_model as prep
from samestorm import provenance


class ModelPreparation(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        (self.root / 'configs').mkdir()
        self.checkpoint = self.root / 'checkpoint'
        self.checkpoint.mkdir()
        entries = []
        for name, body in [('config.json', b'{"synthetic":true}'), ('model.safetensors', b'synthetic weights')]:
            path = self.checkpoint / name
            path.write_bytes(body)
            entry = dict(rfilename=name)
            if name.endswith('.safetensors'):
                entry['lfs'] = dict(sha256=hashlib.sha256(body).hexdigest())
            else:
                entry['blobId'] = hashlib.sha1(b'blob ' + str(len(body)).encode() + b'\0' + body).hexdigest()
            entries.append(entry)
        self.metadata = self.root / 'configs/metadata.json'
        self.metadata.write_text(json.dumps(dict(id='fixture/model', sha='revision', siblings=entries)))
        self.model = dict(id='fixture/model', revision='revision', metadata_path='configs/metadata.json',
                          metadata_sha256=provenance.sha256(self.metadata),
                          reference='F16', reference_path='model-F16.gguf', checkpoint_path='checkpoint')
        self.patch = patch.object(prep, 'ROOT', self.root)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_pinned_checkpoint_hashes_pass(self):
        self.assertEqual(set(prep.verify_checkpoint(self.model, self.checkpoint)), {'config.json', 'model.safetensors'})

    def test_changed_missing_or_unpinned_weights_fail(self):
        (self.checkpoint / 'model.safetensors').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            prep.verify_checkpoint(self.model, self.checkpoint)
        (self.checkpoint / 'model.safetensors').unlink()
        with self.assertRaisesRegex(ValueError, 'Missing checkpoint'):
            prep.verify_checkpoint(self.model, self.checkpoint)

    def test_changed_metadata_or_wrong_revision_fails(self):
        content = json.loads(self.metadata.read_text())
        content['sha'] = 'different-revision'
        self.metadata.write_text(json.dumps(content))
        with self.assertRaisesRegex(ValueError, 'metadata changed'):
            prep.verify_checkpoint(self.model, self.checkpoint)
        self.model['metadata_sha256'] = provenance.sha256(self.metadata)
        with self.assertRaisesRegex(ValueError, 'selected model/revision'):
            prep.verify_checkpoint(self.model, self.checkpoint)

    def test_dirty_or_wrong_toolchain_fails(self):
        (self.root / 'configs/toolchain.json').write_text(json.dumps(dict(llama_cpp_commit='pinned')))
        for commit, dirty in [('pinned', ''), ('different', ''), ('pinned', ' M converter.py')]:
            with self.subTest(commit=commit, dirty=dirty), patch.object(prep.subprocess, 'check_output', side_effect=[commit, dirty]):
                if commit == 'pinned' and not dirty:
                    self.assertEqual(prep.verify_toolchain(), self.root / 'vendor/llama.cpp')
                else:
                    with self.assertRaises(ValueError):
                        prep.verify_toolchain()

    def test_compressed_gguf_reference_fails(self):
        for kind in [1, 32, 15]:
            fake = SimpleNamespace(GGUFReader=lambda path: SimpleNamespace(fields={
                'general.file_type': SimpleNamespace(contents=lambda: kind)}),
                LlamaFileType=SimpleNamespace(MOSTLY_F16=1, MOSTLY_BF16=32))
            with self.subTest(kind=kind), patch.dict(sys.modules, {'gguf': fake}):
                if kind == 15:
                    with self.assertRaisesRegex(ValueError, 'never requantize'):
                        prep.require_uncompressed(self.root / 'reference.gguf', self.root)
                else:
                    prep.require_uncompressed(self.root / 'reference.gguf', self.root)

    def test_reference_receipt_detects_tampering(self):
        reference, receipt = self.root / 'reference.gguf', self.root / 'reference.gguf.json'
        reference.write_bytes(b'synthetic F16')
        receipt.write_text(json.dumps(dict(model_id=self.model['id'], model_revision=self.model['revision'],
                                           sha256=provenance.sha256(reference))))
        prep.verify_reference_receipt(self.model, reference, receipt)
        reference.write_bytes(b'different weights')
        with self.assertRaisesRegex(ValueError, 'conversion receipt'):
            prep.verify_reference_receipt(self.model, reference, receipt)

    def test_output_collisions_and_run_path_traversal_fail(self):
        output = self.root / 'existing.gguf'
        output.write_bytes(b'preserve')
        with self.assertRaisesRegex(ValueError, 'not be overwritten'):
            prep.require_absent([self.root / 'new.gguf', output])
        self.assertEqual(output.read_bytes(), b'preserve')
        with patch.object(provenance, 'ROOT', self.root):
            provenance.new_run_dir('one-run')
            with self.assertRaises(FileExistsError):
                provenance.new_run_dir('one-run')
            for run_id in ['../escape', '/tmp/escape', 'nested/run']:
                with self.assertRaises(ValueError):
                    provenance.new_run_dir(run_id)

    def test_failed_conversion_preserves_manifest_and_existing_file(self):
        (self.root / 'configs/models.json').write_text(json.dumps(dict(models=[self.model])))
        (self.root / 'configs/experiment.json').write_bytes((ROOT / 'configs/experiment.json').read_bytes())
        (self.root / 'configs/toolchain.json').write_bytes((ROOT / 'configs/toolchain.json').read_bytes())
        (self.root / 'src/samestorm').mkdir(parents=True)
        (self.root / 'src/samestorm/provenance.py').write_text('synthetic fixture')
        reference = self.root / self.model['reference_path']
        reference.write_bytes(b'preserve')
        args = ['prepare_model.py', 'convert', '--model-id', self.model['id'], '--run-id', 'failed-convert']
        with patch.object(sys, 'argv', args), patch.object(provenance, 'ROOT', self.root), \
             patch.object(prep, 'verify_toolchain', return_value=self.root), patch('sys.stderr', new=io.StringIO()):
            self.assertEqual(prep.main(), 1)
        record = json.loads((self.root / 'results/raw/failed-convert/manifest.json').read_text())
        self.assertEqual(record['status'], 'failed')
        self.assertEqual(reference.read_bytes(), b'preserve')

    def test_reference_policy_mismatch_fails_before_a_run(self):
        (self.root / 'configs/models.json').write_text(json.dumps(dict(models=[self.model])))
        settings = json.loads((ROOT / 'configs/experiment.json').read_text())
        settings['reference_precision'] = 'BF16'
        settings['precisions'][0] = 'BF16'
        (self.root / 'configs/experiment.json').write_text(json.dumps(settings))
        args = ['prepare_model.py', 'convert', '--model-id', self.model['id'], '--run-id', 'mismatch']
        with patch.object(sys, 'argv', args), patch('sys.stderr', new=io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                prep.main()
        self.assertEqual(raised.exception.code, 2)
        self.assertFalse((self.root / 'results').exists())


if __name__ == '__main__':
    unittest.main()
