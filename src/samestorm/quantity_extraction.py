"""Development-only AI quantity selection followed by literal parsing and arithmetic."""
import json
import re
from decimal import Decimal

from samestorm.grading import judge_payload
from samestorm.numerical import FACTORS, compare_lower_bound

# Deliberately limited literal vocabulary; unfamiliar forms require review.
UNITS = {'feet':'feet', 'foot':'feet', 'ft':'feet', 'pie':'feet', 'pies':'feet', 'bộ':'feet', '英尺':'feet',
         'm':'meter', 'meter':'meter', 'meters':'meter', 'metre':'meter', 'metres':'meter',
         'metro':'meter', 'metros':'meter', 'mét':'meter', '米':'meter'}
OPERATORS = {'':'eq', 'exactly':'eq', '>':'gt', '>=':'ge', '<':'lt', '<=':'le',
             'more than':'gt', 'greater than':'gt', 'over':'gt', 'at least':'ge',
             'less than':'lt', 'under':'lt', 'at most':'le', 'no more than':'le',
             'más de':'gt', 'hơn':'gt', '逾':'gt'}
UNIT_PATTERN = '|'.join(re.escape(x) for x in sorted(UNITS, key=len, reverse=True))
OP_PATTERN = '|'.join(re.escape(x) for x in sorted(OPERATORS, key=len, reverse=True) if x)
LITERAL = re.compile(r'(?<![A-Za-z0-9.,])(?P<comparison>'+OP_PATTERN+r')?\s*'
                     r'(?P<value>[0-9]+(?:[.,][0-9]+)?)\s*'
                     r'(?P<unit>'+UNIT_PATTERN+r')(?![a-zA-ZÀ-ỹ])', re.I)


def distance_actions(key):
    return [a for a in key['required_actions'] if a.get('quantity')
            and FACTORS.get(a['quantity']['unit'], (None,))[0] == 'length'
            and a['quantity']['source_comparison'] == 'greater_than']


def extraction_payload(question, key, answer, language):
    payload = judge_payload(question, key, answer, language)
    ids = {a['action_id'] for a in distance_actions(key)}
    payload['required_actions'] = [a for a in payload['required_actions'] if a['action_id'] in ids]
    return payload


def quantity_evidence(key, answer, raw, truncated=False):
    if truncated:
        raise ValueError('Quantity extractor hit its generation limit.')
    fence = re.fullmatch(r'\s*```(?:json)?[ \t]*\r?\n(.*?)\r?\n```\s*',raw,flags=re.DOTALL)
    parsed = json.loads(fence.group(1) if fence else raw)
    if not isinstance(parsed,dict) or set(parsed) != {'quantities'} or not isinstance(parsed['quantities'],list):
        raise ValueError('Quantity extraction requires exactly a quantities list.')
    expected = {a['action_id']:a for a in distance_actions(key)}
    records = parsed['quantities']
    for row in records:
        if (not isinstance(row,dict) or set(row) != {'action_id','state','evidence_quote','quantity_quote'}
                or not all(isinstance(v,str) for v in row.values())
                or row['state'] not in {'affirmative','missing','needs_review'}):
            raise ValueError('Malformed quantity extraction record.')
    if not expected or len(records) != len(expected) or {r['action_id'] for r in records} != set(expected):
        raise ValueError('Exactly one extraction is required per supported distance action.')
    checked = []
    mentions = [m for m in LITERAL.finditer(answer)]
    for row in records:
        evidence, quote = row['evidence_quote'],row['quantity_quote']
        if ((evidence and evidence not in answer) or (quote and (not evidence or quote not in evidence))
                or (row['state']=='affirmative' and (not evidence or not quote))
                or (row['state']=='missing' and (evidence or quote))):
            raise ValueError('Extraction evidence must be exact answer text; missing has empty quotes.')
        result = dict(row,status='needs_review',label=None,reason='Semantic extraction requires review.')
        if row['state'] == 'affirmative':
            # Multiple quantities, fractions and unfamiliar forms must not become a favorable selection.
            match = LITERAL.fullmatch(quote)
            covered = (len(mentions)==1 and mentions[0].group().strip()==quote.strip())
            ambiguous = re.search(r'[/⁄½¼¾]|[0-9]\s*[-–]\s*[0-9]|(?<!\w)[+-]\s*[0-9]|[0-9][,.][0-9]{3}(?![0-9])',answer)
            if match and covered and not ambiguous:
                unit = UNITS[match['unit'].casefold()]
                value = Decimal(match['value'].replace(',','.'))
                comparison = OPERATORS[(match['comparison'] or '').casefold()]
                source = expected[row['action_id']]['quantity']
                _,factor = FACTORS[unit]; _,source_factor = FACTORS[source['unit']]
                normalized = value*Decimal(factor)
                bound = Decimal(str(source['value']))*Decimal(source_factor)
                status = compare_lower_bound(normalized,comparison,bound)
                result.update(status=status,label='quantity_error' if status=='violated' else None,
                    value=str(value),unit=unit,comparison=comparison,
                    normalized_value_meters=str(normalized),source_bound_meters=str(bound),
                    reason='Arithmetic conditional on the AI affirmative/context extraction.')
            else:
                result['reason']='Unrecognized, ambiguous or multiple quantity expressions require review.'
        checked.append(result)
    return dict(evidence_type='ai_extracted_mechanical_distance_development',actions=checked,
                semantic_extraction_validated=False,semantic_complete=False,headline_eligible=False)
