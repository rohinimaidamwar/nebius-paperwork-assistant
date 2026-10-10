"""Extra tests for behaviour the first two files do not cover."""
import json

import httpx
import pytest

from paperwork_assistant import cli
from paperwork_assistant.assistant import ask, explain_document
from paperwork_assistant.memory import Memory
from paperwork_assistant.nebius_client import NebiusClient, NebiusError
from paperwork_assistant.redact import redact

def make_client(handler, **kw):
    return NebiusClient(api_key="k", transport=httpx.MockTransport(handler), sleep=lambda s: None, **kw)

def reply(content="", reasoning=None, finish="stop"):
    msg = {"role": "assistant", "content": content}
    if reasoning is not None:
        msg["reasoning_content"] = reasoning
    return {"choices": [{"message": msg, "finish_reason": finish}]}

DOC = {"doc_type": "insurance", "title": "Claim for [NAME_1]", "plain_summary": "Your claim was partly approved. You can appeal.",
       "deadlines": [{"date": "2026-10-31", "what": "Appeal deadline"}]}

def test_pan_is_masked_and_restored():
    red = redact("PAN ABCDE1234F on file")
    assert "ABCDE1234F" not in red.text and "[PAN_1]" in red.text
    assert red.restore(red.text) == "PAN ABCDE1234F on file"

def test_card_placeholder_keeps_following_space():
    assert redact("card 4111 1111 1111 1111 here").text == "card [CARD_1] here"

def test_client_retries_on_503_then_gives_up_clearly():
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(503, text="busy")
    with pytest.raises(NebiusError, match="after 3 attempts"):
        make_client(handler).chat([{"role": "user", "content": "x"}])
    assert calls["n"] == 3

def test_client_does_not_retry_400():
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(400, text="bad request")
    with pytest.raises(NebiusError, match="400"):
        make_client(handler).chat([{"role": "user", "content": "x"}])
    assert calls["n"] == 1

def test_partial_content_cut_off_by_token_limit_is_a_clear_error():
    c = make_client(lambda r: httpx.Response(200, json=reply('{"title": "cut off here', finish="length")))
    with pytest.raises(NebiusError, match="max_tokens"):
        c.chat([{"role": "user", "content": "x"}])

def test_cli_bad_model_output_is_a_clean_error(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("PAPERWORK_DB", str(tmp_path / "p.db"))
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a.txt").write_text("hello")
    c = make_client(lambda r: httpx.Response(200, json=reply("sorry, I cannot do that")))
    assert cli.main(["explain", "a.txt"], client=c) == 1
    assert "Error" in capsys.readouterr().err

def test_cli_non_text_file_is_a_clean_error(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("PAPERWORK_DB", str(tmp_path / "p.db"))
    monkeypatch.chdir(tmp_path)
    (tmp_path / "scan.bin").write_bytes(b"\xff\xfe\x00\x80")
    c = make_client(lambda r: httpx.Response(200, json=reply("{}")))
    assert cli.main(["explain", "scan.bin"], client=c) == 1
    assert "Error" in capsys.readouterr().err

def test_ask_keeps_masking_names_remembered_from_explain():
    bodies = []

    def handler(req):
        bodies.append(req.content.decode())
        return httpx.Response(200, json=reply(json.dumps(DOC) if len(bodies) == 1 else "Appeal by 2026-10-31."))
    mem, c = Memory(), make_client(handler)
    explain_document("Dear Ravi Kumar Sharma, your claim is partly approved.", c, mem, hide=["Ravi Kumar Sharma"])
    assert mem.hidden_names() == ["Ravi Kumar Sharma"]
    assert "Ravi Kumar Sharma" in mem.search("claim appeal")[0]["title"]  # stored restored, locally
    ask("When is the claim appeal deadline", c, mem)  # note: no --hide passed here
    assert "Ravi" not in bodies[1] and "Sharma" not in bodies[1]

def test_ask_refuses_to_show_reasoning_trace_as_answer():
    mem = Memory()
    mem.add({"title": "Claim", "plain_summary": "claim appeal", "deadlines": []})
    c = make_client(lambda r: httpx.Response(200, json=reply("", reasoning="Let me think about this...")))
    with pytest.raises(NebiusError, match="reasoning"):
        ask("claim appeal", c, mem)

def test_forget_all_also_clears_remembered_names():
    mem = Memory()
    mem.add({"title": "t", "plain_summary": "s", "deadlines": []})
    mem.add_hidden(["Ravi Kumar Sharma"])
    mem.forget()
    assert mem.hidden_names() == []

def test_common_words_alone_do_not_match_documents():
    mem = Memory()
    mem.add({"title": "Electricity bill", "plain_summary": "You owe money for the month.", "deadlines": []})
    assert mem.search("what is the") == []
