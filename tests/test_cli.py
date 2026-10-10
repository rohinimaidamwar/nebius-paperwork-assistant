import json

import httpx

from paperwork_assistant import cli
from paperwork_assistant.nebius_client import NebiusClient

GOOD = {"doc_type": "bill", "title": "Electricity bill", "plain_summary": "You owe Rs 900.",
        "deadlines": [{"date": "2099-01-15", "what": "Pay bill"}], "key_points": [], "actions_needed": ["Pay"]}

def client():
    def handler(req):
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(GOOD)}, "finish_reason": "stop"}]})
    return NebiusClient(api_key="k", transport=httpx.MockTransport(handler), sleep=lambda s: None)

def test_cli_explain_then_deadlines_then_forget(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("PAPERWORK_DB", str(tmp_path / "p.db"))
    monkeypatch.chdir(tmp_path)
    (tmp_path / "bill.txt").write_text("Electricity bill. Pay Rs 900 by 2099-01-15. Call 98765 43210.")
    assert cli.main(["explain", "bill.txt"], client=client()) == 0
    out = capsys.readouterr().out
    assert "Electricity bill" in out and "identifiers masked" in out and "not medical, legal or financial" in out
    assert cli.main(["deadlines", "--days", "100000"]) == 0
    assert "Pay bill" in capsys.readouterr().out
    assert cli.main(["forget", "--all"]) == 0
    assert "Deleted 1" in capsys.readouterr().out

def test_cli_reports_missing_file_cleanly(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("PAPERWORK_DB", str(tmp_path / "p.db"))
    monkeypatch.chdir(tmp_path)  # keep a real .env in the repo root out of the test
    assert cli.main(["explain", str(tmp_path / "nope.txt")], client=client()) == 1
    assert "Error" in capsys.readouterr().err
