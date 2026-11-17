import csv
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'scripts'),str(ROOT/'src')]
import crossgrades
import prepare_pilot_review as review
import scale_generate as generation
from samestorm.provenance import sha256
from validate_dataset import load_items
from validate_judges import student_ratings


class BlindPilotReview(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name)
        for kind in ['questions','answers']:
            (self.root/kind).mkdir()
            shutil.copy2(ROOT/f'{kind}/{kind}.en.jsonl',self.root/f'{kind}/{kind}.en.jsonl')
        evidence=self.root/'ai_logs/translation_prompts_responses.jsonl'
        evidence.parent.mkdir();evidence.write_text('Synthetic test evidence\n')
        self.packet=generation.prepare(ROOT,pilot=True,english_only=True)
        self.packet['input_sha256']={f'{k}/{k}.en.jsonl':sha256(self.root/f'{k}/{k}.en.jsonl')
                                     for k in ['questions','answers']}
        freeze=json.loads((ROOT/'data/grading/real_response_pilot/ENGLISH_FIRST_FREEZE.json').read_text())
        freeze['artifacts']=self.packet['input_sha256']
        freeze['review_evidence']={'ai_logs/translation_prompts_responses.jsonl':sha256(evidence)}
        frozen=self.root/'data/grading/real_response_pilot/ENGLISH_FIRST_FREEZE.json'
        frozen.parent.mkdir(parents=True);self.save(frozen,freeze)
        self.directory=self.root/'results/raw/pilot-fixture';self.directory.mkdir(parents=True)
        outputs=[]
        for job in self.packet['plan']['jobs']:
            folder=self.root/'results/raw'/('generate-'+job['precision']);folder.mkdir()
            rows=[]
            for prompt,repeat in generation.generation_cases(self.packet,job):
                rows.append(dict({k:v for k,v in prompt.items() if k!='messages'},
                    model_id=job['model_id'],model_revision=job['model_revision'],
                    quantization_type=job['precision'],repeat_index=repeat,runtime_failure=False,
                    answer='Synthetic answer for '+prompt['example_id']))
            path=folder/'answers.jsonl';crossgrades.write_rows(path,rows)
            receipt=folder/'manifest.json'
            self.save(receipt,dict(stage='generation-generate',run_id=folder.name,status='complete',
                benchmark_frozen=True,reviewed_inputs=self.packet['input_sha256'],development_pilot=True,
                pilot_english_only=True,model_id=job['model_id'],model_revision=job['model_revision'],
                quantization_type=job['precision'],completed_answers=6,expected_answers=6,runtime_failures=0,
                outputs={'answers.jsonl':sha256(path)}))
            outputs.append(dict(precision=job['precision'],answers=str(path.relative_to(self.root)),
                answers_sha256=sha256(path),manifest=str(receipt.relative_to(self.root)),
                manifest_sha256=sha256(receipt)))
        self.save(self.directory/'generation_bundle.json',dict(scope='english_first_development_pilot',
            main_answers=10,repeat_answers=2,outputs=outputs))
        self.save(self.directory/'manifest.json',dict(stage='pilot-preparation-and-generation',status='complete',
            outputs={'generation_bundle.json':sha256(self.directory/'generation_bundle.json')}))
        for mock in [patch.object(review,'prepare',return_value=self.packet),
                     patch.object(crossgrades,'generation_inputs',return_value=self.packet)]:
            mock.start();self.addCleanup(mock.stop)

    def save(self,path,value):path.write_text(json.dumps(value)+'\n')

    def test_exports_all_main_answers_blank_and_keeps_precision_outside_review_folder(self):
        answers,excluded,_=review.pilot_answers(self.root,self.directory)
        self.assertEqual((len(answers),len(excluded)),(10,2))
        run=self.root/'export';run.mkdir()
        with patch.object(review.secrets.SystemRandom,'shuffle',side_effect=lambda rows:rows.reverse()) as shuffle:
            result=review.export(self.root,run,answers)
        shuffle.assert_called_once()
        self.assertEqual(result['action_rows'],16)
        with (run/'review/student_review.csv').open(newline='') as stream:rows=list(csv.DictReader(stream))
        with (run/'review/answer_outcomes.csv').open(newline='') as stream:outcomes=list(csv.DictReader(stream))
        self.assertEqual(len(outcomes),10)
        self.assertTrue(all(r['status']==r['evidence_quote']==r['comment']=='' for r in rows))
        self.assertTrue(all(r['refusal']==r['wrong_language']=='' for r in outcomes))
        mapping=json.loads((run/'private_mapping.json').read_text())
        self.assertEqual(mapping[0]['answer_id'],answers[-1]['answer_id'])
        self.assertEqual({r['quantization_type'] for r in mapping},{'F16','Q4_K_M'})
        self.assertEqual(len({r['case_id'] for r in mapping}),10)
        self.assertTrue(all(r['answer']==next(a['text'] for a in mapping if a['case_id']==r['case_id']) for r in rows))
        for file in (run/'review').iterdir():
            for token in ['quantization_type','target_model_id','Q4_K_M','F16','generation_run_id','expected_status']:
                self.assertNotIn(token,file.read_text())
        cases={r['case_id']:dict(item_id=r['item_id'],lang='en',answer=r['text']) for r in mapping}
        for row in rows:row['status']='uncertain'
        ratings=student_ratings(rows,cases,{'en':load_items(self.root/'questions/questions.en.jsonl')},
                                {'en':load_items(self.root/'answers/answers.en.jsonl')})
        self.assertEqual(len(ratings),16)

    def test_changed_answer_or_parent_receipt_is_rejected(self):
        path=self.root/'results/raw/generate-F16/answers.jsonl'
        path.write_text(path.read_text()+'\n')
        with self.assertRaisesRegex(ValueError,'changed'):review.pilot_answers(self.root,self.directory)
        self.save(self.directory/'manifest.json',dict(stage='pilot-preparation-and-generation',status='failed'))
        with self.assertRaisesRegex(ValueError,'complete, unchanged'):review.pilot_answers(self.root,self.directory)

    def test_incomplete_matrix_rejected_even_with_updated_hashes(self):
        path=self.root/'results/raw/generate-F16/answers.jsonl'
        crossgrades.write_rows(path,crossgrades.read_rows(path)[:-1])
        receipt=path.parent/'manifest.json';record=json.loads(receipt.read_text())
        record['outputs']['answers.jsonl']=sha256(path);self.save(receipt,record)
        bundle_path=self.directory/'generation_bundle.json';bundle=json.loads(bundle_path.read_text())
        bundle['outputs'][0].update(answers_sha256=sha256(path),manifest_sha256=sha256(receipt))
        self.save(bundle_path,bundle)
        parent=json.loads((self.directory/'manifest.json').read_text())
        parent['outputs']['generation_bundle.json']=sha256(bundle_path)
        self.save(self.directory/'manifest.json',parent)
        with self.assertRaisesRegex(ValueError,'prompt/repeat matrix'):
            review.pilot_answers(self.root,self.directory)

    def test_export_does_not_overwrite_existing_review(self):
        answers,_,_=review.pilot_answers(self.root,self.directory)
        run=self.root/'export';run.mkdir()
        review.export(self.root,run,answers)
        before=(run/'review/student_review.csv').read_bytes()
        with self.assertRaises(FileExistsError):review.export(self.root,run,answers)
        self.assertEqual((run/'review/student_review.csv').read_bytes(),before)


if __name__=='__main__':unittest.main()
