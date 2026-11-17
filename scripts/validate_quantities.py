"""Prepare distance-extraction tasks or report separate development evidence; no inference."""
import argparse
import json
import shutil
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'),str(ROOT/'scripts')]
from samestorm.judges import config_paths,load_config,local_path
from samestorm.provenance import manifest,new_run_dir,sha256
from samestorm.quantity_extraction import distance_actions,extraction_payload,quantity_evidence
from scale_judge import validation_tasks
from validate_dataset import COUNTS,load_items
from validate_grading import build_messages,check_cases,read_rows,write_rows


def read_extractions(path,role,spec,cases,keys,cases_path,answer_files=None):
    record=json.loads((path.parent/'manifest.json').read_text())
    if (record.get('stage')!='quantity-judge' or record.get('task_kind')!='quantity'
            or record.get('prompt_version')!='quantity_v1' or record.get('judge_role')!=role
            or record.get('model_id')!=spec['model_id'] or record.get('model_revision')!=spec['revision']
            or record.get('prompt_sha256')!=spec['prompt_sha256'] or record.get('cases_path')!=cases_path):
        raise ValueError('Quantity run does not match the selected cases, extraction prompt or model.')
    if record.get('status') not in {'complete','failed'}:
        raise ValueError('Quantity run has not finished.')
    if record.get('outputs',{}).get(path.name)!=sha256(path):
        raise ValueError('Quantity output differs from its manifest hash.')
    relative=[cases_path,'configs/judges.json',spec['prompt_path'],spec['prompt_revision_path']]
    relative += [f'{kind}/{kind}.{lang}.jsonl' for kind in ['questions','answers'] for lang in COUNTS]
    for name in relative:
        if record.get('inputs',{}).get(name)!=sha256(ROOT/name):
            raise ValueError('Quantity run used changed or unrecorded inputs: '+name)
    tasks=path.parent/'tasks.input.jsonl'
    if record.get('inputs',{}).get(tasks.name)!=sha256(tasks):
        raise ValueError('Saved extraction tasks differ from their hash.')
    copied=[]
    for relative in record.get('answer_files',[]):
        saved=local_path(path.parent,relative)
        for candidate in [saved,saved.parent/'manifest.json']:
            if record['inputs'].get(str(candidate.relative_to(path.parent)))!=sha256(candidate):
                raise ValueError('Saved generation input differs from its extraction snapshot.')
        copied.append(saved)
    if [sha256(p) for p in copied]!=[sha256(p) for p in (answer_files or [])]:
        raise ValueError('Extraction used different generated answer files.')
    validation_tasks(ROOT,tasks,spec,cases_path=cases_path,payload_builder=extraction_payload,response_files=copied)
    checked={}
    for row in read_rows(path):
        cid=row['case_id']
        if cid not in cases or cid in checked:
            raise ValueError('Unknown or duplicate extraction case ID.')
        if (row.get('judge_role')!=role or row.get('model_id')!=spec['model_id']
                or row.get('model_revision')!=spec['revision'] or row.get('synthetic') is not (not bool(answer_files))):
            raise ValueError('Extraction row role/model/synthetic scope mismatch.')
        result=dict(state='failed',evidence=None,error=row.get('error'))
        if row.get('judge_failure') is False and not row.get('judge_runtime_failure'):
            case=cases[cid]
            try:
                evidence=quantity_evidence(keys[case['lang']][case['item_id']],case['answer'],
                                          row['raw_judgment'],row.get('hit_generation_limit',False))
                if row.get('quantity_evidence')!=evidence:
                    raise ValueError('Saved quantity evidence differs from replayed extraction.')
                result=dict(state='valid',evidence=evidence)
            except (ValueError,KeyError,TypeError) as error:
                result['error']=str(error)
        checked[cid]=result
    return checked


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=['prepare','report'])
    parser.add_argument('--run-id',required=True)
    parser.add_argument('--cases',default='data/grading/cases.jsonl')
    parser.add_argument('--primary',type=Path)
    parser.add_argument('--secondary',type=Path)
    parser.add_argument('--answers',action='append',type=Path,default=[],
                        help='Verified target-generation answers; repeat for multiple runs instead of --cases.')
    args=parser.parse_args()
    run=new_run_dir(args.run_id)
    record=manifest(args.run_id,'quantity-'+args.mode,[],status='running',prompt_version='quantity_v1',
                    semantic_extraction_validated=False,headline_eligible=False)
    output=run/'manifest.json'
    output.write_text(json.dumps(record,indent=2)+'\n')
    try:
        config=load_config(ROOT,'quantity_v1')
        case_path=local_path(ROOT,args.cases);args.cases=str(case_path.relative_to(ROOT))
        if args.answers and args.cases!='data/grading/cases.jsonl':
            raise ValueError('Use generated answers or synthetic --cases, not both.')
        record['cases_path']=args.cases
        paths=[Path(__file__),ROOT/'scripts/scale_judge.py',ROOT/'scripts/validate_grading.py',
               ROOT/'src/samestorm/quantity_extraction.py',ROOT/'src/samestorm/numerical.py',
               ROOT/'src/samestorm/grading.py',ROOT/'src/samestorm/judges.py',case_path,
               *config_paths(ROOT,config)]
        paths += [ROOT/kind/f'{kind}.{lang}.jsonl' for kind in ['questions','answers'] for lang in COUNTS]
        for source in paths:
            target=run/'inputs'/source.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(source,target);record['inputs'][str(source.relative_to(ROOT))]=sha256(target)
        for index,path in enumerate(args.answers):
            folder=run/'inputs'/f'generation-{index}';folder.mkdir()
            for name,source in [('answers.jsonl',path),('manifest.json',path.parent/'manifest.json')]:
                target=folder/name;shutil.copyfile(source,target)
                record['inputs'][str(target.relative_to(run))]=sha256(target)
        if args.answers:
            from crossgrades import generation_answers
            answers,_=generation_answers(ROOT,args.answers)
            all_cases=[dict(case_id=a['answer_id'],item_id=a['item_id'],lang=a['lang'],answer=a['text'],synthetic=False)
                       for a in answers]
        else:
            all_cases=read_rows(case_path)
        keys={l:load_items(ROOT/f'answers/answers.{l}.jsonl') for l in COUNTS}
        questions={l:load_items(ROOT/f'questions/questions.{l}.jsonl') for l in COUNTS}
        if not args.answers:
            checks,_=check_cases(all_cases,questions,keys)
            if not all(r['passed'] for r in checks):
                raise ValueError('Invalid case annotations or expected design labels.')
        cases={c['case_id']:c for c in all_cases if distance_actions(keys[c['lang']][c['item_id']])}
        if not cases:
            raise ValueError('No supported distance actions in this input.')
        common=dict(cases=len(cases),excluded_non_distance_cases=len(all_cases)-len(cases),
                    cases_path=None if args.answers else args.cases,
                    cases_sha256=None if args.answers else sha256(case_path),prompt_version='quantity_v1',
                    data_source='verified_generated_answers' if args.answers else 'constructed_cases',
                    answer_sha256=[sha256(p) for p in args.answers],
                    semantic_extraction_validated=False,headline_eligible=False,
                    limitations=['Arithmetic is conditional on unvalidated AI relevance/polarity extraction.',
                                 'No judge decisions or headline metrics are replaced.',
                                 'Missing, uncertain and unsupported forms require review; no inferred omission.',
                                 'Source answers are development evidence, not independent human gold.'])
        if args.mode=='prepare':
            prompt=(ROOT/config['primary']['prompt_path']).read_text()
            tasks=[dict(case_id=c['case_id'],synthetic=not bool(args.answers),messages=build_messages(
                extraction_payload(questions[c['lang']][c['item_id']],keys[c['lang']][c['item_id']],
                                   c['answer'],c['lang']),prompt)) for c in cases.values()]
            write_rows(run/'quantity_tasks.jsonl',tasks)
            report=dict(common,inference_performed=False,tasks=len(tasks))
        else:
            results={}
            for role in ['primary','secondary']:
                path=getattr(args,role)
                if path is None:results[role]={};continue
                shutil.copyfile(path,run/(role+'.jsonl'))
                shutil.copyfile(path.parent/'manifest.json',run/(role+'.manifest.json'))
                results[role]=read_extractions(path,role,config[role],cases,keys,args.cases,args.answers)
            details=[];counts={role:Counter() for role in results}
            for cid,case in cases.items():
                for action in distance_actions(keys[case['lang']][case['item_id']]):
                    row=dict(case_id=cid,lang=case['lang'],action_id=action['action_id'])
                    for role,values in results.items():
                        result=values.get(cid,dict(state='missing',evidence=None))
                        row[role]=result
                        if result['state']=='valid':
                            evidence=next(a for a in result['evidence']['actions'] if a['action_id']==action['action_id'])
                            counts[role][evidence['status']]+=1
                        else:counts[role][result['state']]+=1
                    details.append(row)
            write_rows(run/'quantity_comparisons.jsonl',details)
            report=dict(common,results_present=any(results.values()),evidence_counts=counts,
                        raw_judge_decisions_overridden=False)
        (run/'quantity_extraction_report.json').write_text(json.dumps(report,indent=2)+'\n')
        record['status']='complete'
        print(f"PREPARED: {len(cases)} distance cases." if args.mode=='prepare' else 'REPORT: separate development evidence; no automatic grade overrides.')
        print(run/'quantity_extraction_report.json')
        return 0
    except Exception as error:
        record.update(status='failed',error=str(error));print(f'FAIL: {error}',file=sys.stderr);return 1
    finally:
        if record['status']=='running':record['status']='interrupted'
        record['outputs']={str(p.relative_to(run)):sha256(p) for p in run.iterdir() if p.is_file() and p!=output}
        output.write_text(json.dumps(record,indent=2)+'\n')


if __name__=='__main__':
    sys.exit(main())
