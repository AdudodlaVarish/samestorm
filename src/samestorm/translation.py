"""Sentence-sized inputs for MT models trained on individual sentences."""


def split_sentences(text):
    parts, start = [], 0
    for i, char in enumerate(text):
        following = text[i + 1:i + 2]
        decimal = char == '.' and i > 0 and text[i - 1].isdigit() and following.isdigit()
        boundary = (char == '\n' or char in '。！？' or
                    (char in '.!?' and not decimal and (not following or following.isspace())))
        if boundary:
            part = text[start:i + 1].strip()
            if part:
                parts.append(part)
            start = i + 1
    tail = text[start:].strip()
    if tail:
        parts.append(tail)
    if not parts or ''.join(''.join(p.split()) for p in parts) != ''.join(text.split()):
        raise ValueError('Sentence splitting lost source characters or the source is blank.')
    return parts
