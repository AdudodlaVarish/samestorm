import argparse
import hashlib
import json
import math
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

COUNTS = {'en': 48, 'es': 48, 'vi': 48, 'zh': 40}
COMPARISONS = {'greater_than', 'greater_or_equal', 'less_than', 'less_or_equal', 'equal'}
ROLES = {'base': 'base', 'p1': 'paraphrase', 'p2': 'paraphrase', 'cf1': 'counterfactual'}
HAZARDS = {'flood', 'heat', 'winter_power_co', 'tornado'}


def load_items(path):
    items = {}
    for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError as exc:
            raise ValueError(f'{path.name}:{number}: invalid JSON') from exc
        if not isinstance(row, dict) or not isinstance(row.get('item_id'), str) or not row['item_id']:
            raise ValueError(f'{path.name}:{number}: missing string item_id')
        if row['item_id'] in items:
            raise ValueError(f'{path.name}:{number}: duplicate item_id {row["item_id"]}')
        items[row['item_id']] = row
    return items


def validate(root):
    root = Path(root).resolve()
    errors, questions, answers, hashes = [], {}, {}, {}

    def require(condition, message):
        if not condition:
            errors.append(message)

    def nonempty(value):
        return isinstance(value, str) and bool(value.strip())

    def local_file(relative, label):
        if not nonempty(relative):
            errors.append(f'{label}: missing local path')
            return None
        path = (root / relative).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            errors.append(f'{label}: file missing or path escapes dataset: {relative}')
            return None
        return path

    for lang, count in COUNTS.items():
        try:
            qs = load_items(root / 'questions' / f'questions.{lang}.jsonl')
            keys = load_items(root / 'answers' / f'answers.{lang}.jsonl')
        except (OSError, ValueError) as exc:
            errors.append(str(exc))
            continue
        questions[lang], answers[lang] = qs, keys
        require(len(qs) == count and len(keys) == count, f'{lang}: expected {count} questions and keys')
        require(qs.keys() == keys.keys(), f'{lang}: question/answer IDs do not match')
        families = defaultdict(set)
        for item_id, question in qs.items():
            family, _, role = item_id.rpartition('-')
            require(bool(family) and role in {'base', 'p1', 'p2', 'cf1'}, f'{item_id}/{lang}: invalid pilot ID')
            families[family].add(role)
            text = question.get('question' if lang == 'en' else 'translated_question')
            require(nonempty(text), f'{item_id}/{lang}: missing question text')
            if lang != 'en':
                require(question.get('lang') == lang, f'{item_id}/{lang}: wrong question language')
                require(question.get('english_original') == questions.get('en', {}).get(item_id, {}).get('question'),
                        f'{item_id}/{lang}: English original does not match')
        require(len(families) == count // 4 and all(roles == {'base', 'p1', 'p2', 'cf1'} for roles in families.values()),
                f'{lang}: expected complete four-question families')

        for item_id, key in keys.items():
            label = f'{item_id}/{lang}'
            require(key.get('lang') == lang, f'{label}: wrong answer language')
            sources = key.get('sources')
            if not isinstance(sources, list) or not sources:
                errors.append(f'{label}: missing source list')
                continue
            source_ids = set()
            for source in sources:
                if not isinstance(source, dict):
                    errors.append(f'{label}: source must be an object')
                    continue
                sid = source.get('source_id')
                if not nonempty(sid):
                    errors.append(f'{label}: missing source_id')
                    continue
                require(sid not in source_ids, f'{label}: duplicate source_id {sid}')
                source_ids.add(sid)
                require(source.get('lang') == lang, f'{label}/{sid}: source language mismatch')
                for field in ['official_quote', 'document_group_id', 'passage_ref', 'extraction']:
                    require(nonempty(source.get(field)), f'{label}/{sid}: missing {field}')
                url = source.get('url')
                try:
                    parts = urlsplit(url) if isinstance(url, str) else urlsplit('')
                    host = (parts.hostname or '').lower()
                    official = parts.scheme == 'https' and (host.endswith('.gov') or host in {
                        'apps.state.or.us', 'sharedsystems.dhsoha.state.or.us'})
                except ValueError:
                    official = False
                require(official, f'{label}/{sid}: expected official HTTPS URL')
                try:
                    datetime.fromisoformat(source['retrieved'].replace('Z', '+00:00'))
                except (KeyError, TypeError, ValueError, AttributeError):
                    errors.append(f'{label}/{sid}: invalid retrieval date')
                require('published' in source, f'{label}/{sid}: publication date or null required')
                provenance = 'original' if lang == 'en' else 'agency-published'
                require(source.get('translation_provenance') == provenance, f'{label}/{sid}: incorrect source provenance')
                path = local_file(source.get('snapshot_path'), f'{label}/{sid}')
                if path:
                    if path not in hashes:
                        hashes[path] = hashlib.sha256(path.read_bytes()).hexdigest()
                    require(hashes[path] == source.get('sha256'), f'{label}/{sid}: source checksum mismatch')
                local_file(source.get('derived_text_path'), f'{label}/{sid}/derived text')

            local_ids = set()
            for field, id_field in [('required_actions', 'action_id'), ('forbidden_claims', 'claim_id')]:
                entries = key.get(field)
                if not isinstance(entries, list) or (field == 'required_actions' and not entries):
                    errors.append(f'{label}: invalid {field} list')
                    continue
                for entry in entries:
                    if not isinstance(entry, dict):
                        errors.append(f'{label}: {field} entry must be an object')
                        continue
                    eid = entry.get(id_field)
                    if not nonempty(eid):
                        errors.append(f'{label}: missing {id_field}')
                        continue
                    require(eid not in local_ids, f'{label}: duplicate action/claim ID {eid}')
                    local_ids.add(eid)
                    require(nonempty(entry.get('text')), f'{label}/{eid}: missing instruction text')
                    refs = entry.get('source_refs')
                    require(isinstance(refs, list) and bool(refs) and all(
                        isinstance(ref, str) and ref in source_ids for ref in refs), f'{label}/{eid}: invalid source references')
                    if field != 'required_actions':
                        continue
                    for flag in ['critical', 'negation_sensitive']:
                        require(type(entry.get(flag)) is bool, f'{label}/{eid}: {flag} must be boolean')
                    require(isinstance(entry.get('condition'), str), f'{label}/{eid}: condition must be a string')
                    require('quantity' in entry, f'{label}/{eid}: quantity or null required')
                    quantity = entry.get('quantity')
                    if quantity is not None:
                        if not isinstance(quantity, dict):
                            errors.append(f'{label}/{eid}: quantity must be an object or null')
                            continue
                        for name in ['value', 'tolerance']:
                            number = quantity.get(name)
                            require(type(number) in (int, float) and math.isfinite(number), f'{label}/{eid}: invalid {name}')
                        tolerance = quantity.get('tolerance')
                        require(type(tolerance) in (int, float) and tolerance >= 0, f'{label}/{eid}: invalid tolerance')
                        require(nonempty(quantity.get('unit')), f'{label}/{eid}: missing unit')
                        require(quantity.get('source_comparison') in COMPARISONS, f'{label}/{eid}: invalid source comparison')

    english_ids = questions.get('en', {}).keys()
    for lang, qs in questions.items():
        require(qs.keys() <= english_ids, f'{lang}: question ID lacks English counterpart')
        if lang in {'es', 'vi'}:
            require(qs.keys() == english_ids, f'{lang}: missing required English counterpart IDs')
        for item_id, key in answers[lang].items():
            english = answers.get('en', {}).get(item_id, {})
            original = {a['action_id']: a for a in english.get('required_actions', []) if isinstance(a, dict) and nonempty(a.get('action_id'))}
            actions = key.get('required_actions', [])
            if not isinstance(actions, list):
                continue
            translated = {a['action_id']: a for a in actions if isinstance(a, dict) and nonempty(a.get('action_id'))}
            require(translated.keys() == original.keys(), f'{item_id}/{lang}: actions differ from English key')
            for aid in original.keys() & translated.keys():
                for field in ['critical', 'negation_sensitive', 'quantity', 'numeric_identifier', 'grading_scope']:
                    require(translated[aid].get(field) == original[aid].get(field),
                            f'{item_id}/{lang}/{aid}: {field} differs from English key')
    try:
        metadata = load_items(root / 'data' / 'item_metadata.jsonl')
    except (OSError, ValueError) as exc:
        errors.append(str(exc))
        return errors
    require(metadata.keys() == english_ids, 'metadata: IDs must match English question IDs exactly')
    metadata_families = defaultdict(list)
    for item_id, row in metadata.items():
        label = f'{item_id}/metadata'
        family, _, suffix = item_id.rpartition('-')
        require(row.get('family_id') == family, f'{label}: family_id does not match question ID')
        role = row.get('role')
        valid_role = isinstance(role, str) and role in ROLES.values()
        require(valid_role and role == ROLES.get(suffix), f'{label}: role does not match question ID')
        require(row.get('split') == 'dev', f'{label}: pilot split must be dev')
        hazard = row.get('hazard')
        valid_hazard = isinstance(hazard, str) and hazard in HAZARDS
        require(valid_hazard, f'{label}: invalid hazard')
        langs = row.get('languages_available')
        valid_langs = (isinstance(langs, list) and all(isinstance(lang, str) for lang in langs)
                       and len(langs) == len(set(langs)) and set(langs) <= COUNTS.keys())
        require(valid_langs, f'{label}: languages must be a unique list of known codes')
        if valid_langs:
            actual = {lang for lang in COUNTS if item_id in questions.get(lang, {}) and item_id in answers.get(lang, {})}
            require(set(langs) == actual, f'{label}: languages do not match question/answer files')
        if row.get('family_id') == family and family and valid_role and valid_hazard and valid_langs:
            metadata_families[family].append(row)
    require(len(metadata_families) == 12, 'metadata: expected 12 complete families')
    hazard_counts = Counter()
    for family, rows in metadata_families.items():
        require(Counter(r['role'] for r in rows) == Counter(base=1, paraphrase=2, counterfactual=1),
                f'{family}/metadata: expected base, two paraphrases and counterfactual')
        hazards = {r['hazard'] for r in rows}
        require(len(hazards) == 1, f'{family}/metadata: inconsistent hazard within family')
        require(len({tuple(sorted(r['languages_available'])) for r in rows}) == 1,
                f'{family}/metadata: inconsistent language coverage within family')
        if len(hazards) == 1:
            hazard_counts.update(hazards)
    require(hazard_counts == Counter({hazard: 3 for hazard in HAZARDS}),
            'metadata: expected three families per hazard')
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        errors = validate(args.root)
    except (OSError, ValueError, TypeError) as exc:
        print(f'FAIL: {exc}', file=sys.stderr)
        return 1
    for error in errors:
        print(f'FAIL: {error}', file=sys.stderr)
    if errors:
        return 1
    print('PASS: 184 question/key pairs; en=48, es=48, vi=48, zh=40. Source checksums and 48 metadata rows across 12 dev families are consistent.')
    print('Structural/source-integrity checks only; this does not validate semantics, grading accuracy or authorize experiments.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
