import json
from datetime import date

import httpx
import pytest

from paperwork_assistant.assistant import ask, explain_document, normalize
from paperwork_assistant.jsonutil import ModelOutputError, extract_json
from paperwork_assistant.memory import Memory
from paperwork_assistant.nebius_client import NebiusClient, NebiusError
from paperwork_assistant.redact import redact

LETTER = open("demo/sample_letter.txt", encoding="utf-8").read()
GOOD_JSON = {
    "doc_type": "insurance", "title": "Claim decision for [NAME_1]",
    "plain_summary": "Part of your claim was approved. You can appeal.",
    "key_points": ["Rs 3,200 approved"], "amounts": [{"label": "Approved", "value": "Rs 3,200"}],
    "deadlines": [{"date": "2026-10-31", "what": "Appeal deadline"}, {"date": "soon", "what": "bad date"}],
    "actions_needed": ["Write an appeal if you disagree"], "questions_to_ask": ["What is the reasonable-charge limit?"],
    "unclear_or_risky": [],
}

def make_client(handler, **kw):
    return NebiusClient(api_key="test-key", transport=httpx.MockTransport(handler), sleep=lambda s: None, **kw)

def chat_reply(content="", reasoning=None, finish="stop"):
    msg = {"role": "assistant", "content": content}
    if reasoning is not None:
        msg["reasoning_content"] = reasoning
    return {"model": "nvidia/Nemotron-3-Nano-30B-A3B", "choices": [{"message": msg, "finish_reason": finish}]}

# -------- redaction --------
def test_redaction_masks_and_restores():
    red = redact(LETTER, hide=["Ravi Kumar Sharma"])
    for secret in ("ravi.sharma@example.com", "4829 1037 5561", "98765 43210", "Ravi Kumar Sharma"):
        assert secret not in red.text
    assert "[EMAIL_1]" in red.text and "[AADHAAR_1]" in red.text and "[NAME_1]" in red.text
    assert "ravi.sharma@example.com" in red.restore(red.text)

def test_name_parts_are_masked_too():
    red = redact("Dear Mr. Sharma, this is for Ravi Kumar Sharma.", hide=["Ravi Kumar Sharma"])
    assert "Sharma" not in red.text and "Ravi" not in red.text
    assert red.restore(red.text) == "Dear Mr. Sharma, this is for Ravi Kumar Sharma."

def test_dates_and_small_numbers_are_not_masked():
    text = "Claim 88231 on 2026-08-28 for Rs 4,800 due 31/10/2026"
    assert redact(text).text == text

def test_luhn_valid_card_masked_random_digits_not_marked_as_card():
    assert "[CARD_1]" in redact("card 4111 1111 1111 1111 here").text
    assert "[CARD_" not in redact("ref 1234 5678 9012 3456 here").text

def test_same_value_gets_same_placeholder():
    red = redact("a@b.com and again a@b.com")
    assert red.text.count("[EMAIL_1]") == 2 and len(red.mapping) == 1

# -------- json helpers --------
def test_extract_json_handles_fences_think_and_prose():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('<think>hmm {"x":0}</think>{"a": 2}') == {"a": 2}
    assert extract_json('Here you go: {"a": 3} thanks') == {"a": 3}
    with pytest.raises(ModelOutputError):
        extract_json("no json here")

def test_normalize_drops_bad_dates_and_fixes_types():
    n = normalize({"deadlines": [{"date": "2026-02-30", "what": "x"}, {"date": "2026-10-31", "what": "y"}],
                   "key_points": "single string"})
    assert [d["date"] for d in n["deadlines"]] == [None, "2026-10-31"]
    assert n["key_points"] == ["single string"] and n["doc_type"] == "other"

# -------- client --------
def test_client_sends_bearer_key_model_and_path():
    seen = {}

    def handler(req):
        seen["url"], seen["auth"], seen["body"] = str(req.url), req.headers["authorization"], json.loads(req.content)
        return httpx.Response(200, json=chat_reply("hi"))
    c = make_client(handler, model="nvidia/Nemotron-3-Nano-30B-A3B")
    assert c.chat([{"role": "user", "content": "x"}]).text == "hi"
    assert seen["url"] == "https://api.tokenfactory.nebius.com/v1/chat/completions"
    assert seen["auth"] == "Bearer test-key" and seen["body"]["model"].startswith("nvidia/Nemotron")

def test_client_falls_back_to_reasoning_content_when_content_empty():
    c = make_client(lambda r: httpx.Response(200, json=chat_reply("", reasoning='{"a": 1}')))
    reply = c.chat([{"role": "user", "content": "x"}])
    assert reply.used_reasoning_fallback and reply.text == '{"a": 1}'

def test_client_raises_clear_error_when_reasoning_truncated():
    c = make_client(lambda r: httpx.Response(200, json=chat_reply("", reasoning="thinking...", finish="length")))
    with pytest.raises(NebiusError, match="max_tokens"):
        c.chat([{"role": "user", "content": "x"}])

def test_client_retries_on_429_then_succeeds():
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(429, text="slow down") if calls["n"] < 3 else httpx.Response(200, json=chat_reply("ok"))
    assert make_client(handler).chat([{"role": "user", "content": "x"}]).text == "ok"

def test_client_does_not_retry_auth_errors_and_lists_models():
    c = make_client(lambda r: httpx.Response(401, text="bad key"))
    with pytest.raises(NebiusError, match="401"):
        c.chat([{"role": "user", "content": "x"}])
    c2 = make_client(lambda r: httpx.Response(200, json={"data": [{"id": "b"}, {"id": "a"}]}))
    assert c2.list_models() == ["a", "b"]

def test_missing_key_is_a_clear_error(monkeypatch):
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    with pytest.raises(NebiusError, match="NEBIUS_API_KEY"):
        NebiusClient()

# -------- end to end --------
def test_explain_sends_no_identifiers_restores_output_and_remembers():
    sent = {}

    def handler(req):
        sent["body"] = req.content.decode()
        return httpx.Response(200, json=chat_reply(json.dumps(GOOD_JSON)))
    mem = Memory()
    out = explain_document(LETTER, make_client(handler), mem, hide=["Ravi Kumar Sharma"])
    for secret in ("ravi.sharma@example.com", "4829 1037 5561", "98765 43210", "Ravi Kumar Sharma"):
        assert secret not in sent["body"]
    assert out["result"]["title"] == "Claim decision for Ravi Kumar Sharma"  # restored locally
    assert out["identifiers_masked"] >= 4 and out["doc_id"] == 1
    assert [d["date"] for d in out["result"]["deadlines"]] == ["2026-10-31", None]
    assert mem.upcoming(today=date(2026, 10, 1), days=60) == [
        {"date": "2026-10-31", "what": "Appeal deadline", "doc_id": 1, "title": "Claim decision for Ravi Kumar Sharma"}]
    assert mem.upcoming(today=date(2026, 11, 5)) == []

def test_ask_answers_from_memory_and_skips_model_when_nothing_saved():
    mem = Memory()
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(200, json=chat_reply("Your appeal is due 2026-10-31."))
    c = make_client(handler)
    assert "do not have" in ask("When is my appeal due", c, mem)["answer"] and calls["n"] == 0
    mem.add(normalize(GOOD_JSON))
    out = ask("What is the appeal deadline for my claim", c, mem)
    assert "2026-10-31" in out["answer"] and out["sources"] == [1] and calls["n"] == 1

def test_forget_one_and_all():
    mem = Memory()
    a, b = mem.add(normalize(GOOD_JSON)), mem.add(normalize(GOOD_JSON))
    assert mem.forget(a) == 1 and mem.count() == 1
    assert len(mem.upcoming(today=date(2026, 10, 1), days=60)) == 1  # cascade removed the other's deadline
    assert mem.forget() == 1 and mem.count() == 0 and b == 2
