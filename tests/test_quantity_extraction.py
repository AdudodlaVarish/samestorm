import contextlib
import io
import json
import sys
import tempfile
import types
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock,patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
import scale_judge as worker
import validate_quantities as pipeline
import scale_generate as generation
from samestorm.judges import config_paths,load_config
from samestorm.numerical import compare_lower_bound,numerical_evidence
from samestorm.provenance import sha256
from samestorm.quantity_extraction import quantity_evidence,extraction_payload

CASES='data/grading/multilingual_stress_v1/cases.jsonl'


class ExtractedArithmetic(unittest.TestCase):
    def key(self,value=20,unit='feet'):
        return dict(required_actions=[dict(action_id='distance',critical=True,
                    quantity=dict(value=value,unit=unit,source_comparison='greater_than'))])

    def result(self,answer,quote,state='affirmative',value=20,unit='feet'):
        raw=json.dumps(dict(quantities=[dict(action_id='distance',state=state,
            evidence_quote=answer if state!='missing' else '',quantity_quote=quote)]))
        return quantity_evidence(self.key(value,unit),answer,raw)

    def test_fresh_values_boundaries_and_non_twenty_thresholds(self):
        for quote,bound,unit,status in [
            ('32 feet',20,'feet','supported'),('18 feet',20,'feet','violated'),
            ('20 feet',20,'feet','violated'),('more than 20 feet',20,'feet','supported'),
            ('at least 20 feet',20,'feet','violated'),('13 feet',12,'feet','supported'),
            ('12 feet',12,'feet','violated'),('4.6 meters',4.5,'meter','supported'),
            ('4.5 meters',4.5,'meter','violated'),('6.0960 meters',20,'feet','violated'),
            ('6.1 meters',20,'feet','supported'),('less than 25 feet',20,'feet','needs_review')]:
            with self.subTest(quote=quote,bound=bound):
                result=self.result('Place it '+quote+' away.',quote,value=bound,unit=unit)
                self.assertEqual(result['actions'][0]['status'],status)
                self.assertFalse(result['headline_eligible'])
                self.assertFalse(result['semantic_extraction_validated'])
        self.assertEqual(compare_lower_bound(Decimal('7'), 'unknown',Decimal('6')),'needs_review')

    def test_literal_language_forms_do_not_claim_native_semantic_validation(self):
        for text,quote in [('Colóquelo a más de 20 pies.','más de 20 pies'),
                           ('Đặt máy cách hơn 20 feet.','hơn 20 feet'),
                           ('放置距离逾20英尺。','逾20英尺'),('保持25英尺的距离。','25英尺')]:
            with self.subTest(text=text):self.assertEqual(self.result(text,quote)['actions'][0]['status'],'supported')
        # Existing English-only mechanical grading is not silently expanded.
        self.assertEqual(numerical_evidence('25 feet',self.key()['required_actions'][0]['quantity'],'vi')['status'],'needs_review')

    def test_multiple_quantities_fraction_range_and_missing_extraction_abstain(self):
        for text,quote in [('Place it 9 feet or 32 feet away.','32 feet'),
                           ('Place it 20 1/2 feet away.','2 feet'),
                           ('Place it 20-32 feet away.','32 feet'),
                           ('Place it -32 feet away.','32 feet'),
                           ('Place it 1,000 feet away.','1,000 feet'),
                           ('Place it 6.096 meters away.','6.096 meters'),
                           ('Place it twenty feet away.','twenty feet')]:
            with self.subTest(text=text):self.assertEqual(self.result(text,quote)['actions'][0]['status'],'needs_review')
        for state in ['missing','needs_review']:
            r=self.result('Do not place it 9 feet away.','',state=state)
            self.assertEqual(r['actions'][0]['status'],'needs_review')
            self.assertIsNone(r['actions'][0]['label'])

    def test_comparator_cannot_be_omitted_and_quotes_must_be_exact(self):
        self.assertEqual(self.result('Place it more than 20 feet away.','20 feet')['actions'][0]['status'],'needs_review')
        with self.assertRaisesRegex(ValueError,'exact answer'):
            self.result('Place it 25 feet away.','30 feet')
        with self.assertRaisesRegex(ValueError,'empty quotes'):
            self.result('Place it 25 feet away.','25 feet',state='missing')

    def test_duplicate_ids_extra_fields_and_truncation_fail_closed(self):
        row=dict(action_id='distance',state='affirmative',evidence_quote='25 feet',quantity_quote='25 feet')
        for actions in [[row,row],[dict(row,action_id='unknown')],[dict(row,value=25)],[]]:
            with self.subTest(actions=actions),self.assertRaises(ValueError):
                quantity_evidence(self.key(),'25 feet',json.dumps(dict(quantities=actions)))
        with self.assertRaisesRegex(ValueError,'generation limit'):
            quantity_evidence(self.key(),'25 feet','{}',True)


class QuantityPipeline(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.directory=Path(temp.name)

    def command(self,module,name,*args,expected=0):
        run=self.directory/name;run.mkdir()
        with patch.object(module,'new_run_dir',return_value=run),patch.object(sys,'argv',
                [module.__name__,'--run-id',name,*args]),contextlib.redirect_stdout(io.StringIO()),\
                contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(module.main(),expected)
        return run

    def test_prepare_all_distance_cases_and_check_both_roles_without_gold_leakage(self):
        run=self.command(pipeline,'prepared','prepare','--cases',CASES)
        tasks=run/'quantity_tasks.jsonl';config=load_config(ROOT,'quantity_v1')
        self.assertEqual(len(pipeline.read_rows(tasks)),36)
        for role in ['primary','secondary']:
            checked=self.command(worker,role,'check','--task-kind','quantity','--cases',CASES,
                '--input',str(tasks),'--judge-role',role)
            r=json.loads((checked/'manifest.json').read_text())
            self.assertEqual(r['stage'],'quantity-check');self.assertEqual(r['prompt_version'],'quantity_v1')
            self.assertEqual(json.loads((checked/'setup_report.json').read_text())['valid_tasks'],36)
            for path in config_paths(ROOT,config):
                self.assertEqual(r['inputs'][str(path.relative_to(ROOT))],sha256(path))
        for row in pipeline.read_rows(tasks):
            payload=json.loads(row['messages'][1]['content'])
            self.assertNotIn('expected_labels',payload)
            self.assertTrue(all(a['quantity'] for a in payload['required_actions']))
        pending=self.command(pipeline,'pending','report','--cases',CASES)
        report=json.loads((pending/'quantity_extraction_report.json').read_text())
        self.assertFalse(report['results_present']);self.assertFalse(report['raw_judge_decisions_overridden'])
        self.assertEqual(report['evidence_counts']['primary'],{'missing':36})

    def test_worker_keeps_extraction_evidence_separate_from_judge_grade(self):
        config=load_config(ROOT,'quantity_v1');spec=config['primary']
        case=pipeline.read_rows(ROOT/CASES)[2]  # Spanish affirmative 25-foot placement.
        self.assertIn('quantity-safe',case['case_id'])
        key=pipeline.load_items(ROOT/f"answers/answers.{case['lang']}.jsonl")[case['item_id']]
        question=pipeline.load_items(ROOT/f"questions/questions.{case['lang']}.jsonl")[case['item_id']]
        task=dict(case_id=case['case_id'],synthetic=True,messages=[
            dict(role='system',content=(ROOT/spec['prompt_path']).read_text()),
            dict(role='user',content=json.dumps(extraction_payload(question,key,case['answer'],case['lang'])))])
        path=self.directory/'tasks.jsonl';pipeline.write_rows(path,[task])
        raw=json.dumps(dict(quantities=[dict(action_id='co-001-base--co-outdoor-distance',state='affirmative',
            evidence_quote=case['answer'],quantity_quote='25 pies')]))
        tokenizer,model,torch=MagicMock(),MagicMock(),MagicMock()
        tokens=MagicMock();tokens.shape=(1,10);tokens.to.return_value=tokens
        tokenizer.apply_chat_template.return_value=tokens;tokenizer.decode.return_value=raw
        generated=MagicMock();generated.__len__.return_value=5;generated.tolist.return_value=[1,2]
        model.generate.return_value.__getitem__.return_value=generated
        model.hf_device_map={'':'cuda:0'};model.generation_config.eos_token_id=2
        torch.cuda.device_count.return_value=3;torch.cuda.max_memory_allocated.return_value=100
        runtime=types.SimpleNamespace(AutoTokenizer=MagicMock(),AutoModelForCausalLM=MagicMock())
        runtime.AutoTokenizer.from_pretrained.return_value=tokenizer
        runtime.AutoModelForCausalLM.from_pretrained.return_value=model
        args=types.SimpleNamespace(input=path,model_dir=self.directory/'checkpoint',judge_role='primary',
                                  offset=0,limit=0,task_kind='quantity',cases=CASES)
        with patch.dict(sys.modules,transformers=runtime),patch.object(worker,'verify_checkpoint',return_value={}):
            worker.run_judge(args,self.directory,{},config,torch)
        row=pipeline.read_rows(self.directory/'judgments.jsonl')[0]
        self.assertNotIn('grade',row)
        self.assertFalse(row['judge_failure'])
        self.assertEqual(row['quantity_evidence']['actions'][0]['status'],'supported')

    def test_report_replays_provenance_and_preserves_failed_and_missing_cases(self):
        prepared=self.command(pipeline,'packet','prepare','--cases',CASES)
        source=self.directory/'fixture-extraction';source.mkdir()
        config=load_config(ROOT,'quantity_v1');spec=config['primary']
        cases=pipeline.read_rows(ROOT/CASES);case=cases[2]
        key=pipeline.load_items(ROOT/'answers/answers.es.jsonl')[case['item_id']]
        raw=json.dumps(dict(quantities=[dict(action_id='co-001-base--co-outdoor-distance',state='affirmative',
            evidence_quote=case['answer'],quantity_quote='25 pies')]))
        path=source/'judgments.jsonl'
        good=dict(case_id=case['case_id'],synthetic=True,judge_role='primary',model_id=spec['model_id'],
                  model_revision=spec['revision'],judge_failure=False,raw_judgment=raw,hit_generation_limit=False,
                  quantity_evidence=quantity_evidence(key,case['answer'],raw))
        bad=dict(good,case_id=cases[3]['case_id'],judge_failure=True,error='Synthetic rejection',raw_judgment='{}')
        del bad['quantity_evidence']
        pipeline.write_rows(path,[good,bad])
        (source/'tasks.input.jsonl').write_bytes((prepared/'quantity_tasks.jsonl').read_bytes())
        paths=[ROOT/CASES,*config_paths(ROOT,config)]
        paths += [ROOT/kind/f'{kind}.{lang}.jsonl' for kind in ['questions','answers'] for lang in pipeline.COUNTS]
        record=dict(stage='quantity-judge',task_kind='quantity',prompt_version='quantity_v1',status='failed',
            judge_role='primary',model_id=spec['model_id'],model_revision=spec['revision'],
            cases_path=CASES,prompt_sha256=spec['prompt_sha256'],
            inputs={str(p.relative_to(ROOT)):sha256(p) for p in paths},outputs={path.name:sha256(path)})
        record['inputs']['tasks.input.jsonl']=sha256(source/'tasks.input.jsonl')
        (source/'manifest.json').write_text(json.dumps(record))
        before=path.read_bytes()
        run=self.command(pipeline,'reported','report','--cases',CASES,'--primary',str(path))
        report=json.loads((run/'quantity_extraction_report.json').read_text())
        self.assertEqual(report['evidence_counts']['primary'],{'supported':1,'failed':1,'missing':34})
        self.assertFalse(report['raw_judge_decisions_overridden'])
        self.assertEqual(path.read_bytes(),before)
        path.write_bytes(before+b'\n')
        self.command(pipeline,'tampered','report','--cases',CASES,'--primary',str(path),expected=1)

    def test_verified_actual_answer_preparation_worker_and_report(self):
        packet=generation.prepare(ROOT,pilot=True)
        prompt=next(p for p in packet['prompts'] if p['example_id']=='co-001-base:en')
        job=packet['plan']['jobs'][0]
        source=self.directory/'synthetic-generation';source.mkdir()
        path=source/'answers.jsonl'
        answer='Use the generator outside, 32 feet from the home, doors and windows.'
        row={k:v for k,v in prompt.items() if k!='messages'}
        row.update(model_id=job['model_id'],model_revision=job['model_revision'],
            quantization_type=job['precision'],repeat_index=0,runtime_failure=False,answer=answer)
        pipeline.write_rows(path,[row])
        # This receipt is a unit-test fixture, not an actual approval or generated answer.
        record=dict(run_id='synthetic-test-generation',stage='generation-generate',benchmark_frozen=True,
            reviewed_inputs=packet['input_sha256'],model_id=job['model_id'],
            model_revision=job['model_revision'],quantization_type=job['precision'],
            outputs={path.name:sha256(path)})
        (source/'manifest.json').write_text(json.dumps(record))
        prepared=self.command(pipeline,'actual-prep','prepare','--answers',str(path))
        task=pipeline.read_rows(prepared/'quantity_tasks.jsonl')[0]
        self.assertFalse(task['synthetic'])
        checked=self.command(worker,'actual-check','check','--task-kind','quantity',
            '--input',str(prepared/'quantity_tasks.jsonl'),'--answer-file',str(path))
        spec=load_config(ROOT,'quantity_v1')['primary']
        raw=json.dumps(dict(quantities=[dict(action_id='co-001-base--co-outdoor-distance',state='affirmative',
            evidence_quote=answer,quantity_quote='32 feet')]))
        key=pipeline.load_items(ROOT/'answers/answers.en.jsonl')['co-001-base']
        judgments=checked/'judgments.jsonl'
        pipeline.write_rows(judgments,[dict(case_id=task['case_id'],synthetic=False,judge_role='primary',
            model_id=spec['model_id'],model_revision=spec['revision'],judge_failure=False,
            raw_judgment=raw,hit_generation_limit=False,quantity_evidence=quantity_evidence(key,answer,raw))])
        m=json.loads((checked/'manifest.json').read_text())
        m.update(stage='quantity-judge',judge_role='primary',model_id=spec['model_id'],
                 model_revision=spec['revision'],prompt_sha256=spec['prompt_sha256'])
        m['outputs'][judgments.name]=sha256(judgments)
        (checked/'manifest.json').write_text(json.dumps(m))
        reported=self.command(pipeline,'actual-report','report','--answers',str(path),'--primary',str(judgments))
        report=json.loads((reported/'quantity_extraction_report.json').read_text())
        self.assertEqual(report['data_source'],'verified_generated_answers')
        self.assertIsNone(report['cases_path'])
        self.assertEqual(report['evidence_counts']['primary'],{'supported':1})
        path.write_bytes(path.read_bytes()+b'\n')
        self.command(worker,'actual-tampered','check','--task-kind','quantity',
            '--input',str(prepared/'quantity_tasks.jsonl'),'--answer-file',str(path),expected=1)


if __name__=='__main__':unittest.main()
