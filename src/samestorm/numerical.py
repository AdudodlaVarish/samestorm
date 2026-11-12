import re
import unicodedata
from decimal import Decimal

QUANTITY = re.compile(
    r'(?<![\w.])(?P<comparison>no more than|at least|at most|more than|greater than|less than|over|under|>=|<=|>|<|exactly)?'
    r'\s*(?P<value>\d+(?:[.,]\d+)?)\s*'
    r'(?P<unit>feet|foot|ft|metres?|meters?|m|hours?|hrs?|h|minutes?|mins?)\b', re.I)


FACTORS = {'feet': ('length', '0.3048'), 'foot': ('length', '0.3048'), 'ft': ('length', '0.3048'),
           'meter': ('length', '1'), 'meters': ('length', '1'), 'metre': ('length', '1'),
           'metres': ('length', '1'), 'm': ('length', '1'),
           'hour': ('time', '60'), 'hours': ('time', '60'), 'hr': ('time', '60'),
           'hrs': ('time', '60'), 'h': ('time', '60'), 'minute': ('time', '1'),
           'minutes': ('time', '1'), 'min': ('time', '1'), 'mins': ('time', '1')}


COMPARISONS = {'more than': 'gt', 'greater than': 'gt', 'over': 'gt', '>': 'gt',
               'at least': 'ge', '>=': 'ge', 'less than': 'lt', 'under': 'lt', '<': 'lt',
               'at most': 'le', 'no more than': 'le', '<=': 'le', 'exactly': 'eq', '': 'eq'}


def numerical_evidence(text, quantity, language='en'):
    result = dict(status='needs_review', label=None, quantities=[], reason='No unambiguous applicable quantity.')
    if language != 'en':
        result['reason'] = 'English numerical scope rules only; other languages require validated cross-grades.'
        return result
    text = unicodedata.normalize('NFKC', text).casefold()
    dimension, factor = FACTORS[quantity['unit']]
    bound = Decimal(str(quantity['value'])) * Decimal(factor)
    for match in QUANTITY.finditer(text):
        dim, conversion = FACTORS[match['unit']]
        if dim == dimension:
            result['quantities'].append(dict(value=str(Decimal(match['value'].replace(',', '.')) * Decimal(conversion)),
                                             comparison=COMPARISONS[match['comparison'] or ''],
                                             original=match.group(0).strip(), unit=match['unit'],
                                             start=match.start(), end=match.end()))
    if re.search(r'["“”/?]|-\d|\b(not|never|don.t|wrong|unsafe|incorrect|roughly|about|approximately)\b', text):
        result['reason'] = 'Negated, quoted, questioned or approximate advice requires semantic review.'
        return result
    values = result['quantities']
    if dimension == 'time':
        care_clauses = [c for c in re.split(r'[.!?;\n]', text) if re.search(r'medical (help|attention)', c)]
        immediate = (len(care_clauses) == 1 and
                     re.search(r'\b(get|seek) medical (help|attention) (now|immediately)\b', care_clauses[0])
                     and not re.search(r'\b(if|after|until|wait|another|additional|later|or)\b', text))
        if immediate:
            return dict(result, status='supported', reason='Explicit immediate medical help; elapsed symptom time is not a future threshold.')
        if not re.search(r'\bif\b.*\b(cramps?|symptoms)\b.*\b(last|persist|continue)\b', text):
            return dict(result, reason='No unambiguous cramps-duration condition bound to the medical-help recommendation.')
    if len(values) > 1:
        rounded_pair = False
        if (dimension == 'length' and len(values) == 2 and '(' in text and ')' in text
                and {FACTORS[v['unit']][1] for v in values} == {'0.3048', '1'}):
            feet = next(v for v in values if FACTORS[v['unit']][1] == '0.3048')
            metres = next(v for v in values if FACTORS[v['unit']][1] == '1')
            exact = Decimal(feet['value']) == Decimal(metres['value'])
            documented = (Decimal(feet['value']) == Decimal('6.096') and feet['comparison'] == 'gt'
                          and Decimal(metres['value']) == Decimal('6.10'))
            rounded_pair = exact or documented
        if not rounded_pair:
            result['reason'] = 'Multiple quantities retained; no favorable-number selection.'
            return result
        values = values[:1]
    if not values:
        if dimension == 'time' and re.search(r'\b(get|seek) medical (help|attention) (now|immediately)\b', text):
            result.update(status='supported', reason='Immediate medical help satisfies conservative escalation policy.')
        return result
    value = Decimal(values[0]['value']); comparison = values[0]['comparison']
    if dimension == 'length' and quantity['source_comparison'] == 'greater_than':
        if comparison in {'gt', 'ge', 'eq'}:
            valid = value > bound or (value == bound and comparison == 'gt')
        elif value <= bound:
            valid = False
        else:
            result['reason'] = 'An upper bound alone does not establish safe placement.'
            return result
    elif dimension == 'time' and quantity['source_comparison'] == 'greater_than':
        if re.search(r'\b(wait|another|additional|delay)\b', text):
            result['reason'] = 'Delay relative to elapsed symptom time needs semantic condition review.'
            return result
        if not re.search(r'\b(medical (help|attention)|see a doctor)\b', text):
            return result
        valid = value <= bound
    else:
        result['reason'] = 'Comparator has no validated operational rule.'
        return result
    result.update(status='supported' if valid else 'violated',
                  label=None if valid else 'quantity_error',
                  reason='Source inequality satisfied; conservative advice allowed.' if valid else 'Explicit numerical advice violates the source safety bound.')
    return result


def phone_evidence(text, allow_hospital=False, language='en'):
    result = dict(status='needs_review', label=None, reason='No validated affirmative telephone or hospital route.')
    if language != 'en' or re.search(r'["“”]|\b(not|never|don.t|wrong)\b|\?', text, re.I):
        return result
    if allow_hospital and re.search(r'\bhospital\b.*\b(now|immediately)\b|\bimmediately\b.*\bhospital\b', text, re.I):
        return dict(result, status='supported', reason='Immediate hospital route is an official alternative.')
    calls = re.findall(r'\b(?:call|dial)\s+(\d[\d -]*\d|\d)', text, re.I)
    numbers = [''.join(c for c in value if c.isdigit()) for value in calls]
    if numbers == ['911']:
        return dict(result, status='supported', reason='Affirmative telephone route uses the source identifier.')
    if numbers:
        result.update(reason='Telephone identifier mismatch or conflict; identifiers are not physical quantities.',
                      diagnostic='numeric_identifier_mismatch', identifiers=numbers)
    return result
