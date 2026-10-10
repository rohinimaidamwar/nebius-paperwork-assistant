"""Remove personal identifiers BEFORE text leaves the machine, and put them back afterwards.

Nebius Token Factory is a cloud service, so privacy here means data minimisation:
identifiers are replaced by placeholders such as [EMAIL_1], the model only sees the
placeholders, and this module restores the originals in the answer locally.

Regex redaction is a safety net, not a guarantee. Names and addresses cannot be
found reliably with patterns, so callers pass `hide` for names to mask explicitly.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

def _luhn_ok(digits: str) -> bool:
    total, flip = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if flip:
            d = d * 2 - 9 if d * 2 > 9 else d * 2
        total += d
        flip = not flip
    return total % 10 == 0

# Order matters: more specific patterns first.
PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("EMAIL", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("PAN", re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b")),
    ("AADHAAR", re.compile(r"(?<!\d)(?<!\d[ -])\d{4}[ -]?\d{4}[ -]?\d{4}(?![ -]?\d)")),
    # 13-19 digits with optional single spaces/dashes between them (no trailing separator).
    ("CARD", re.compile(r"\b\d(?:[ -]?\d){12,18}\b")),
    # Any other long digit run (phones, account numbers). Classified by digit count below.
    ("NUMBER", re.compile(r"(?<![\w.])\+?\d[\d ().-]{7,}\d(?!\w)")),
]

# Dates are protected from the number patterns so "2026-08-28" is never mistaken for an ID.
_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}[/.]\d{1,2}[/.]\d{2,4}\b")

@dataclass
class Redaction:
    text: str
    mapping: dict[str, str] = field(default_factory=dict) # placeholder -> original

    def restore(self, text: str) -> str:
        for placeholder, original in self.mapping.items():
            text = text.replace(placeholder, original)
        return text

def redact(text: str, hide: list[str] | None = None) -> Redaction:
    mapping: dict[str, str] = {}
    counters: dict[str, int] = {}

    def put(kind: str, original: str) -> str:
        for ph, orig in mapping.items():
            if orig == original:
                return ph
        counters[kind] = counters.get(kind, 0) + 1
        ph = f"[{kind}_{counters[kind]}]"
        mapping[ph] = original
        return ph

    out = text
    dates: list[str] = []

    def stash(m: re.Match[str]) -> str:
        dates.append(m.group(0))
        return f"\x00{len(dates) - 1}\x00"

    out = _DATE.sub(stash, out)

    for kind, pattern in PATTERNS:
        def sub(m: re.Match[str], kind: str = kind) -> str:
            raw = m.group(0)
            digits = re.sub(r"\D", "", raw)
            if kind == "CARD" and not _luhn_ok(digits):
                return raw # probably not a card number; the NUMBER pattern may still catch it
            if kind == "NUMBER":
                if len(digits) < 9:
                    return raw # short numbers (amounts, claim ids) are left alone
                return put("PHONE" if 10 <= len(digits) <= 13 else "NUMBER", raw)
            return put(kind, raw)
        out = pattern.sub(sub, out)

    out = re.sub(r"\x00(\d+)\x00", lambda m: dates[int(m.group(1))], out)

    # Names last, so an email like ravi.sharma@x.com is masked as one EMAIL, not as name fragments.
    # Mask each full name and also each part of it ("Ravi Kumar Sharma" -> "Sharma" in "Dear Mr. Sharma").
    names: set[str] = set()
    for full in hide or []:
        full = full.strip()
        if full:
            names.add(full)
            names.update(part for part in re.split(r"\s+", full) if len(part) >= 3)
    for name in sorted(names, key=len, reverse=True):
        out = re.sub(rf"\b{re.escape(name)}\b", lambda m: put("NAME", m.group(0)), out, flags=re.IGNORECASE)
    return Redaction(text=out, mapping=mapping)
