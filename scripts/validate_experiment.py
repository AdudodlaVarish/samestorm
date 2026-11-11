"""Check the fixed pilot settings before preparing experiment runs."""
import argparse
import json
import sys
from pathlib import Path

QUANTS = {'Q8_0', 'Q6_K', 'Q4_K_M', 'Q3_K_M', 'Q2_K'}


def validate(settings):
    if not isinstance(settings, dict):
        return ['Experiment settings must be a JSON object.']
    errors = []
    for field, expected in {'context_tokens': 4096, 'thinking': False,
                            'retrieval': 'closed_book', 'use_model_chat_template': True}.items():
        if type(settings.get(field)) is not type(expected) or settings[field] != expected:
            errors.append(f'{field} must be {expected!r}.')
    seed = settings.get('seed')
    if type(seed) is not int or seed < 0:
        errors.append('seed must be a nonnegative integer.')
    fraction = settings.get('determinism_repeat_fraction')
    if type(fraction) not in (int, float) or fraction != 0.1:
        errors.append('determinism_repeat_fraction must be 0.1.')
    decoding = settings.get('decoding')
    if not isinstance(decoding, dict):
        errors.append('decoding must be an object.')
    else:
        for field, expected in {'temperature': 0, 'top_k': 1, 'repeat_penalty': 1.0, 'max_tokens': 320}.items():
            value = decoding.get(field)
            types = (int,) if field in {'top_k', 'max_tokens'} else (int, float)
            if type(value) not in types or value != expected:
                errors.append(f'decoding.{field} must be {expected}.')
    reference = settings.get('reference_precision')
    if reference not in ('F16', 'BF16'):
        errors.append('reference_precision must be F16 or BF16, never a quantized model.')
    precisions = settings.get('precisions')
    if (not isinstance(precisions, list) or not all(isinstance(p, str) for p in precisions)
            or len(precisions) != 6 or reference not in ('F16', 'BF16')
            or set(precisions) != QUANTS | {reference}):
        errors.append('precisions must contain each of the five quantizations and exactly one matching reference.')
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=Path(__file__).resolve().parents[1] / 'configs/experiment.json')
    args = parser.parse_args()
    try:
        errors = validate(json.loads(args.config.read_text(encoding='utf-8')))
    except (OSError, ValueError) as exc:
        errors = [str(exc)]
    for error in errors:
        print(f'FAIL: {error}', file=sys.stderr)
    if errors:
        return 1
    print('PASS: pilot decoding, context, seed, six precisions, uncompressed reference and repeat settings.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
