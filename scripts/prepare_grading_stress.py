"""Assemble all 90 multilingual development pairs with design-accepted r2 replacements."""
import argparse
import copy
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'scripts')]
from samestorm.judges import local_path
from samestorm.provenance import sha256
from validate_grading import check_cases, read_rows, write_rows
from validate_dataset import COUNTS, load_items


def review_rows(path, revision=False):
    rows = {}
    for block in re.split(r'^## ', path.read_text(encoding='utf-8'), flags=re.M)[1:]:
        pattern = r'^Student English evidence decision: \*\*(.*?)\*\*' if revision else r'^Student back-translation review: \*\*(.*?)\*\*'
        match = re.search(pattern, block, re.M)
        if not match:
            continue
        pair = block.splitlines()[0]
        if pair in rows or match.group(1) not in {'consistent English evidence', 'discrepancy', 'uncertain'}:
            raise ValueError('Duplicate or incomplete English pair review: ' + pair)
        design = re.search(r'^Student revision decision: \*\*(.*?)\*\*', block, re.M) if revision else None
        if revision and (not design or design.group(1) != 'accept proposed design'):
            raise ValueError('Each replacement must have student design acceptance: ' + pair)
        rows[pair] = match.group(1)
    return rows


def assemble(root):
    source = root / 'data/grading/multilingual_draft'
    original = read_rows(source / 'cases.jsonl')
    revisions = read_rows(source / 'revision-r2/cases.jsonl')
    original_reviews = review_rows(source / 'LANGUAGE_REVIEW.md')
    revised_reviews = review_rows(source / 'revision-r2/REVIEW.md', revision=True)
    if len(original) != 180 or len(revisions) != 28 or len(original_reviews) != 90 or len(revised_reviews) != 14:
        raise ValueError('Expected the reviewed 180-case draft and 14 revision pairs.')
    meta = json.loads((source / 'manifest.json').read_text())
    revised_meta = json.loads((source / 'revision-r2/manifest.json').read_text())
    for name in ['cases.jsonl', 'LANGUAGE_REVIEW.md', 'revision-r2/cases.jsonl', 'revision-r2/REVIEW.md']:
        if sha256(source / name) != meta['outputs'][name]:
            raise ValueError('Reviewed input differs from its recorded hash: ' + name)
    if revised_meta['design_accepted_pairs'] != 14 or revised_meta['native_language_verified_pairs'] != 0:
        raise ValueError('Revision acceptance/verification scope differs from the recorded review.')
    for name, digest in meta['inputs'].items():
        if name.startswith(('answers/', 'questions/', 'sources/')) and sha256(root / name) != digest:
            raise ValueError('Approved dataset/source input changed: ' + name)
    parents = {c['case_id']: c for c in original}
    if len(parents) != len(original):
        raise ValueError('Original case IDs must be unique.')
    replacements = {}
    for case in revisions:
        parent = case['supersedes_case_id']
        if parent not in parents or parent in replacements or case['pair_id'] not in revised_reviews:
            raise ValueError('Unknown/duplicate replacement or unreviewed revision.')
        if any(case[k] != parents[parent][k] for k in ['lang', 'item_id', 'expected_labels']):
            raise ValueError('Revision changed scenario/language or proposed labels.')
        replacements[parent] = case
    selected = []
    for parent in original:
        revised = parent['case_id'] in replacements
        case = copy.deepcopy(replacements.get(parent['case_id'], parent))
        status = revised_reviews[case['pair_id']] if revised else original_reviews[parent['pair_id']]
        case['review_status'] = 'development_diagnostic_native_language_unverified'
        case['review'] = dict(original_case_id=parent['case_id'], original_pair_id=parent['pair_id'],
            source_revision='r2' if revised else 'original',
            design_decision='accept proposed design' if revised else 'original design review remains unresolved',
            english_evidence=status, native_language_verified=False,
            worksheet='data/grading/multilingual_draft/' + ('revision-r2/REVIEW.md' if revised else 'LANGUAGE_REVIEW.md'))
        selected.append(case)
    if len({c['case_id'] for c in selected}) != 180 or len({c['review']['original_pair_id'] for c in selected}) != 90:
        raise ValueError('Assembly lost or duplicated cases/pairs.')
    for lang in ['es', 'vi', 'zh']:
        subset = [c for c in selected if c['lang'] == lang]
        if len(subset) != 60 or sum(bool(c['expected_labels']) for c in subset) != 30:
            raise ValueError('Each language must retain 30 designed safe and 30 designed harmful cases.')
    for pair in original_reviews:
        subset = [c for c in selected if c['review']['original_pair_id'] == pair]
        if len(subset) != 2 or sum(bool(c['expected_labels']) for c in subset) != 1:
            raise ValueError('A complete safe/flawed pair is required: ' + pair)
    questions = {l: load_items(root / f'questions/questions.{l}.jsonl') for l in COUNTS}
    keys = {l: load_items(root / f'answers/answers.{l}.jsonl') for l in COUNTS}
    checks, _ = check_cases(selected, questions, keys)
    if not all(c['passed'] for c in checks):
        raise ValueError('Selected cases have invalid annotations/evidence or proposed label mapping.')
    return selected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='data/grading/multilingual_stress_v1',
                        help='New repository-relative directory; existing outputs are never overwritten.')
    args = parser.parse_args()
    output = local_path(ROOT, args.output)
    cases = assemble(ROOT)
    output.mkdir(parents=True, exist_ok=False)
    write_rows(output / 'cases.jsonl', cases)
    pairs = {c['review']['original_pair_id']: c['review'] for c in cases}
    source = ROOT / 'data/grading/multilingual_draft'
    inputs = [Path(__file__), source / 'cases.jsonl', source / 'LANGUAGE_REVIEW.md',
              source / 'revision-r2/cases.jsonl', source / 'revision-r2/REVIEW.md', source / 'revision-r2/manifest.json']
    record = dict(stage='multilingual-development-stress-assembly', status='complete',
        case_count=180, pair_count=90, original_records_retained=152, revised_records=28,
        cases_by_language=dict(Counter(c['lang'] for c in cases)),
        english_evidence_pair_counts=dict(Counter(r['english_evidence'] for r in pairs.values())),
        flagged_pairs=sum(r['english_evidence'] != 'consistent English evidence' for r in pairs.values()),
        native_language_verified_cases=0, independent_human_gold=False, validated=False, headline_eligible=False,
        note='All pairs retained. Expected labels are AI-authored design expectations; pair reviews are not blind action ratings.',
        inputs={str(p.relative_to(ROOT)): sha256(p) for p in inputs}, outputs={'cases.jsonl': sha256(output / 'cases.jsonl')})
    (output / 'selection_manifest.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
    print('PASS: 180 cases, 90 pairs, 152 original + 28 r2; no selection by MT agreement.')
    print(output / 'cases.jsonl')
    return 0


if __name__ == '__main__':
    sys.exit(main())
