"""Normalization shared by the QC scripts: make OCR text and keyed text comparable."""
import re

FOLDS = {'Chern': 'Chem', 'Hol ': 'Mol ', 'Atrn': 'Atm'}
NUMBER = re.compile(r'[+-]?\d+(?:\.\d+)?')


def strict(s: str) -> str:
    """Collapse single spaces inside numbers and before punctuation, fold a few glyph confusions."""
    for k, v in FOLDS.items():
        s = s.replace(k, v)
    s = re.sub(r'(?<=[\d.\-]) (?=[\d.\-])', '', s)
    s = re.sub(r'(?<=\d)[lI](?=\d)', '1', s)
    s = re.sub(r'(?<=\d)[Oo](?=\d)', '0', s)
    s = re.sub(r'\s+(?=[,.;:)\]])', '', s)
    return re.sub(r'\s+', ' ', s)


def loose(s: str) -> str:
    """Lowercase alphanumerics only."""
    for k, v in FOLDS.items():
        s = s.replace(k, v)
    return re.sub(r'[^a-z0-9]', '', s.lower())


def numbers(cell: str) -> list[str]:
    """Numeric tokens of a table cell, mantissa only ("9.96 x 10^-3" -> ["9.96"])."""
    head = re.split(r'\s*[x×]\s*10|\s*10\^', cell)[0]
    return [n for n in NUMBER.findall(head) if len(n.strip('+-')) >= 2 or '.' in n]


def cas_numbers(s: str) -> list[str]:
    return re.findall(r'\b\d{2,7}-\d{2}-\d\b', strict(s))


CAS = re.compile(r'^\d{2,7}-\d{2}-\d$')


def cas_valid(cas: str) -> bool | None:
    """Check digit of a CAS Registry Number; None if the string is not CAS-shaped.

    Digits are weighted by their position counted from the right (the check
    digit excluded), summed, and reduced modulo 10: 7440-59-7 -> 97 -> 7.
    """
    cas = cas.strip()
    if not CAS.match(cas):
        return None
    digits = cas.replace('-', '')
    body, check = digits[:-1], int(digits[-1])
    return sum(int(d) * w for d, w in zip(reversed(body), range(1, len(body) + 1))) % 10 == check
