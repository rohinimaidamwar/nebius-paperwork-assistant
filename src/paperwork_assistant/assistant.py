"""Core logic: redact -> ask Nemotron on Nebius -> parse -> restore -> remember."""
from __future__ import annotations

import re
from datetime import date
from typing import Any

from . import DISCLAIMER
from .jsonutil import extract_json
from .memory import Memory
from .nebius_client import NebiusClient, NebiusError
from .redact import Redaction, redact

EXPLAIN_SYSTEM = """You explain paperwork (letters, bills, insurance and medical reports) to a non-expert in plain language.
Rules:
- Use only information that is in the document. If something is unclear, say so in "unclear_or_risky".
- Do not diagnose, give medical, legal or financial advice, or predict outcomes.
- Keep placeholders such as [NAME_1] or [EMAIL_1] exactly as written.
- Write at about a 9th grade reading level. Keep plain_summary under 120 words.
- Reply with ONE JSON object and nothing else, using exactly these keys:
{"doc_type": "insurance|bill|medical_report|legal|government|bank|other",
 "title": "short title",
 "plain_summary": "string",
 "key_points": ["string"],
 "amounts": [{"label": "string", "value": "string"}],
 "deadlines": [{"date": "YYYY-MM-DD or null", "what": "string"}],
 "actions_needed": ["string"],
 "questions_to_ask": ["questions the reader could ask the sender or a professional"],
 "unclear_or_risky": ["anything confusing, missing or worth double-checking"]}"""

ASK_SYSTEM = """You answer questions about the user's own saved paperwork summaries.
Use only the summaries provided. If the answer is not there, say you do not have it.
Do not give medical, legal or financial advice. Keep placeholders such as [NAME_1] as written. Be brief."""

_LIST_KEYS = ("key_points", "actions_needed", "questions_to_ask", "unclear_or_risky")

def _iso_or_none(value: Any) -> str | None:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value.strip()):
        return None
    try:
        date.fromisoformat(value.strip())
    except ValueError:
        return None
    return value.strip()

def normalize(raw: dict[str, Any]) -> dict[str, Any]:
    """Coerce model output into the expected shape so later code can trust it."""
    out: dict[str, Any] = {
        "doc_type": str(raw.get("doc_type") or "other"),
        "title": str(raw.get("title") or "Untitled document"),
        "plain_summary": str(raw.get("plain_summary") or ""),
    }
    for key in _LIST_KEYS:
        value = raw.get(key) or []
        out[key] = [str(v) for v in value] if isinstance(value, list) else [str(value)]
    out["amounts"] = [{"label": str(a.get("label", "")), "value": str(a.get("value", ""))}
                      for a in raw.get("amounts") or [] if isinstance(a, dict)]
    out["deadlines"] = [{"date": _iso_or_none(d.get("date")), "what": str(d.get("what", ""))}
                        for d in raw.get("deadlines") or [] if isinstance(d, dict)]
    return out

def _restore_all(value: Any, redaction: Redaction) -> Any:
    if isinstance(value, str):
        return redaction.restore(value)
    if isinstance(value, list):
        return [_restore_all(v, redaction) for v in value]
    if isinstance(value, dict):
        return {k: _restore_all(v, redaction) for k, v in value.items()}
    return value

def explain_document(text: str, client: NebiusClient, memory: Memory | None = None,
                     hide: list[str] | None = None, save: bool = True) -> dict[str, Any]:
    red = redact(text, hide)
    reply = client.chat([
        {"role": "system", "content": EXPLAIN_SYSTEM},
        {"role": "user", "content": f"Document:\n\n{red.text}"},
    ])
    result = _restore_all(normalize(extract_json(reply.text)), red)
    doc_id = None
    if memory is not None and save:
        doc_id = memory.add(result)
        if hide:
            memory.add_hidden(hide)  # so `ask` keeps masking these names later
    return {"result": result, "doc_id": doc_id, "model": reply.model,
            "identifiers_masked": len(red.mapping), "disclaimer": DISCLAIMER}

def ask(question: str, client: NebiusClient, memory: Memory, hide: list[str] | None = None) -> dict[str, Any]:
    docs = memory.search(question)
    if not docs:
        return {"answer": "I do not have any saved paperwork that matches that question.",
                "sources": [], "disclaimer": DISCLAIMER}

    context = "\n\n".join(
        f"[doc {d['doc_id']}] {d['title']}: {d['plain_summary']} Deadlines: "
        + "; ".join(f"{x['date']} {x['what']}" for x in d.get("deadlines", []) if x.get("date"))
        for d in docs)

    # Saved summaries contain real names, so mask the names remembered from earlier `explain --hide` runs too.
    names = list(dict.fromkeys([*(hide or []), *memory.hidden_names()]))
    red = redact(f"Saved summaries:\n{context}\n\nQuestion: {question}", names)
    reply = client.chat([{"role": "system", "content": ASK_SYSTEM}, {"role": "user", "content": red.text}])
    if reply.used_reasoning_fallback:
        # The text would be the model's reasoning trace, not an answer. Do not show it.
        raise NebiusError("The model returned only its reasoning, not an answer. Try again or raise max_tokens.")

    return {"answer": red.restore(reply.text), "sources": [d["doc_id"] for d in docs],
            "model": reply.model, "disclaimer": DISCLAIMER}
