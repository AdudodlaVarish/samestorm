"""Export blank, shuffled English student worksheets from a completed combined pilot."""
import argparse
import csv
import json
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'scripts'),str(ROOT/'src')]
from crossgrades import generation_answers, read_rows
from samestorm.judges import local_path
from samestorm.provenance import manifest, new_run_dir, sha256
from scale_generate import assert_reviewed_inputs, generation_cases, prepare
from validate_dataset import load_items


def pilot_answers(root,directory):
    packet = prepare(root,pilot=True,english_only=True)
    freeze = root/'data/grading/real_response_pilot/ENGLISH_FIRST_FREEZE.json'
    assert_reviewed_inputs(root,json.loads(freeze.read_text()),packet['input_sha256'],
                           [p['example_id'] for p in packet['prompts']])
    parent = json.loads((directory/'manifest.json').read_text())
    bundle_path = directory/'generation_bundle.json'
    if (parent.get('stage')!='pilot-preparation-and-generation' or parent.get('status')!='complete'
            or parent.get('outputs',{}).get('generation_bundle.json')!=sha256(bundle_path)):
        raise ValueError('A complete, unchanged combined pilot generation bundle is required.')
    bundle = json.loads(bundle_path.read_text())
    jobs = packet['plan']['jobs']
    if (bundle.get('scope')!='english_first_development_pilot'
            or bundle.get('main_answers')!=packet['plan']['primary_answers']
            or bundle.get('repeat_answers')!=packet['plan']['repeat_answers']
            or [r['precision'] for r in bundle['outputs']]!=[j['precision'] for j in jobs]):
        raise ValueError('Generation bundle differs from the reviewed English pilot scope.')
    paths = []
    sources = [directory/'manifest.json',bundle_path,freeze]
    for output,job in zip(bundle['outputs'],jobs,strict=True):
        path = local_path(root,output['answers'])
        receipt = local_path(root,output['manifest'])
        if (receipt!=path.parent/'manifest.json' or sha256(path)!=output['answers_sha256']
                or sha256(receipt)!=output['manifest_sha256']):
            raise ValueError('Generation answer file or manifest changed.')
        record = json.loads(receipt.read_text())
        expected = [(p['example_id'],repeat) for p,repeat in generation_cases(packet,job)]
        rows = read_rows(path)
        if (record.get('status')!='complete' or record.get('development_pilot') is not True
                or record.get('pilot_english_only') is not True
                or record.get('quantization_type')!=job['precision']
                or record.get('completed_answers')!=len(expected) or record.get('expected_answers')!=len(expected)
                or record.get('runtime_failures')!=0
                or [(r['example_id'],r['repeat_index']) for r in rows]!=expected):
            raise ValueError('Generation run is incomplete or differs from its scoped prompt/repeat matrix.')
        paths.append(path);sources.extend([path,receipt])
    answers,excluded = generation_answers(root,paths)
    if (len(answers)!=packet['plan']['primary_answers'] or any(a['lang']!='en' for a in answers)
            or len(excluded)!=packet['plan']['repeat_answers']
            or any(r['exclusion']!='repeat' for r in excluded)):
        raise ValueError('Expected every English main answer and only the planned repeat exclusions.')
    return answers,excluded,sources


def write_csv(path,fields,rows):
    with path.open('w',newline='',encoding='utf-8') as stream:
        writer = csv.DictWriter(stream,fieldnames=fields)
        writer.writeheader();writer.writerows(rows)


def export(root,run,answers):
    questions = load_items(root/'questions/questions.en.jsonl')
    keys = load_items(root/'answers/answers.en.jsonl')
    shuffled = list(answers);secrets.SystemRandom().shuffle(shuffled)
    review = run/'review';review.mkdir()
    action_rows,outcome_rows,mapping = [],[],[]
    for index,answer in enumerate(shuffled,1):
        cid = f'review-{index:03d}'
        iid,text = answer['item_id'],answer['text']
        question = questions[iid]['question']
        mapping.append(dict(case_id=cid,**answer))
        for action in keys[iid]['required_actions']:
            action_rows.append(dict(case_id=cid,item_id=iid,action_id=action['action_id'],
                question=question,answer=text,required_action=action['text'],critical=action['critical'],
                condition=action['condition'],quantity=json.dumps(action['quantity'],ensure_ascii=False),
                grading_scope=action.get('grading_scope',''),
                numeric_identifier=json.dumps(action.get('numeric_identifier'),ensure_ascii=False),
                status='',evidence_quote='',comment=''))
        outcome_rows.append(dict(case_id=cid,question=question,answer=text,refusal='',wrong_language='',comment=''))
    write_csv(review/'student_review.csv',list(action_rows[0]),action_rows)
    write_csv(review/'answer_outcomes.csv',list(outcome_rows[0]),outcome_rows)
    (run/'private_mapping.json').write_text(json.dumps(mapping,ensure_ascii=False,indent=2)+'\n')
    (review/'README.md').write_text('''# Blind English pilot grading

Research prototype. Follow local officials and call 911 in an emergency.

Copy this review folder to a separate working folder before editing. Keep the
original export unchanged. Open only the review files while grading; the parent
directory contains the private source/model mapping. Do not inspect AI verdicts.
Answers are shuffled and model metadata is omitted. Identical answers remain
separate ratings. This is a small development pilot, not independent validation.

In student_review.csv, edit only status, evidence_quote and comment. Judge the
answer against each required action and its condition, quantity and grading scope:

| Status | Meaning |
| --- | --- |
| correct | Gives the required instruction; equivalent wording is fine. |
| missing | Leaves out the required instruction. |
| reversal | Advises the opposite of the required instruction. |
| quantity_error | Gives the wrong amount or numerical bound. |
| condition_error | Gives the wrong condition for when to act. |
| uncertain | You cannot decide; explain why in comment. |

For correct, reversal, quantity_error and condition_error, copy an exact nonempty
substring from the answer into evidence_quote. For missing, leave the quote empty.
For uncertain, a quote is optional but must be exact if supplied. Do not rewrite
answers or required actions. Blank statuses remain unrated.

In answer_outcomes.csv, edit only refusal, wrong_language and comment. Use true,
false or uncertain for each outcome. Refusal means the answer declines to answer;
wrong_language means it is not delivered in the requested English. These are
separate from action errors. Blank outcomes remain unrated. Runtime failures come
from generation logs; this export requires successful generation runs.

There are ten main answers and sixteen action rows. The two fixed-seed repeats
remain in the generation files for determinism checks and are not extra grading
examples. There are no AI-expected labels or prefilled student ratings here.
After finishing, return both completed CSV files before viewing judge results.
''',encoding='utf-8')
    return dict(main_answers=len(answers),action_rows=len(action_rows),outcome_rows=len(outcome_rows),
                student_ratings_filled=0,judges_run=False,headline_eligible=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pilot-run',type=Path,required=True)
    parser.add_argument('--run-id',required=True)
    args = parser.parse_args()
    run = new_run_dir(args.run_id)
    record = manifest(args.run_id,'pilot-blind-review-preparation',[],status='running',headline_eligible=False)
    output = run/'manifest.json'
    output.write_text(json.dumps(record,indent=2)+'\n')
    try:
        answers,excluded,sources = pilot_answers(ROOT,local_path(ROOT,str(args.pilot_run)))
        sources += [Path(__file__),ROOT/'scripts/crossgrades.py',ROOT/'scripts/scale_generate.py',
                    ROOT/'questions/questions.en.jsonl',ROOT/'answers/answers.en.jsonl']
        record['inputs'] = {str(p.relative_to(ROOT)):sha256(p) for p in sources}
        record.update(export(ROOT,run,answers),excluded_repeats=len(excluded),status='complete')
        print('PREPARED: blank blind worksheet for 10 main answers / 16 action ratings.')
        print(run/'review')
        return 0
    except Exception as error:
        record.update(status='failed',error=str(error))
        print('FAIL: '+str(error),file=sys.stderr)
        return 1
    finally:
        if record['status']=='running':record['status']='interrupted'
        record['outputs'] = {str(p.relative_to(run)):sha256(p) for p in run.rglob('*')
                             if p.is_file() and p!=output}
        output.write_text(json.dumps(record,indent=2)+'\n')


if __name__=='__main__':sys.exit(main())
