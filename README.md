# Paperwork Assistant (Nebius x NVIDIA Global AI Hackathon, Personal AI track)

Explains letters, bills, insurance decisions and medical reports in plain language, remembers deadlines between sessions, and answers follow-up questions. It runs **NVIDIA Nemotron on Nebius Token Factory**.

## What makes it "personal AI"
- **Persistent local memory** (SQLite on your machine): summaries and deadlines survive between sessions. Raw document text is not stored. The saved summaries do contain the real names and identifiers (they are restored locally), so treat the `.db` file as sensitive. It is git-ignored.
- **Data minimisation before the cloud call**: emails, phone numbers, Aadhaar/PAN-style IDs, card numbers, other long digit runs and any names you pass with `--hide` are replaced by placeholders (`[EMAIL_1]`) before anything is sent. The originals are restored locally in the answer. Names passed with `--hide` are remembered locally so `ask` keeps masking them.
- **You can delete everything**: `paperwork forget --all` removes documents and remembered names, and overwrites the deleted data in the database file.

Token Factory is a cloud service, so this is honest data minimisation, not "nothing leaves your machine". Regex redaction is a safety net and can miss things (addresses, unusual names). Do not describe it as guaranteed anonymisation in your submission.

## Quick start
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env          # put your NEBIUS_API_KEY in .env
pytest                        # 29 tests, no network needed (run from the repo root)
paperwork models              # see which Nemotron model ids your key can use, set NEBIUS_MODEL
paperwork explain demo/sample_letter.txt --hide "Ravi Kumar Sharma"
paperwork deadlines --days 60
paperwork ask "when is my appeal due?"
paperwork forget --all
```

## Hackathon requirements this follows
| Requirement (from the Devpost page as I read it) | How |
|---|---|
| Run on Nebius Token Factory or AI Cloud | `nebius_client.py` calls `https://api.tokenfactory.nebius.com/v1/` (OpenAI-compatible) |
| Use at least one NVIDIA open source model | Default model is a Nemotron id; set `NEBIUS_MODEL` to one listed by `paperwork models` |
| Track: Personal AI | Persistent memory, privacy step, deadlines, follow-up Q&A |
| Public repo with an open source license | MIT `LICENSE` (put your name in it) |
| Demo video under 3 minutes | Script in `docs/DEMO_SCRIPT.md` |

Re-read the Rules and Resources tabs. The page also names sponsor tools for this track (I did not check NemoClaw, OpenShell or Hermes Agent) and partner Tavily. None is required by this code. If the Rules make any of them mandatory, add them.

## Verified vs not verified
Verified by automated tests (mocked Nebius server, no network): request shape and auth header, retries, reasoning-model fallback, truncation errors, redaction, memory, CLI error handling.
**Not verified**: live calls to Nebius. Run `paperwork models` and one real `explain` before recording your demo.
- **Model id:** public listings show the Token Factory id as `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`. The default uses that spelling, but only your key's `paperwork models` output is authoritative.
- **Output limit:** the client asks for `max_tokens=4000`. Check the model's actual output limit and adjust if the API rejects it.

## Known behaviour of Nemotron on Token Factory
A public issue from May 2026 (nebius/api #211) reports that the Nemotron models there are reasoning models, and that the answer can end up in `reasoning_content` with `content` empty. This client strips `<think>` blocks, falls back to `reasoning_content`, raises a clear error if the reply was cut off, and never uses native tool calls. `ask` refuses to show a reasoning-only reply as an answer. Check whether the issue is still current.

## Layout
```text
src/paperwork_assistant/
  nebius_client.py   OpenAI-compatible client, retries, reasoning fallback, truncation errors
  redact.py          mask and restore identifiers
  jsonutil.py        strip <think> blocks, extract JSON from model output
  assistant.py       explain_document, ask, output normalisation
  memory.py          SQLite memory, deadlines, remembered names, forget
  cli.py             paperwork explain|deadlines|ask|models|forget
demo/sample_letter.txt   synthetic letter
tests/                   test_paperwork.py, test_cli.py, test_extras.py
```

## Ideas to raise your chances (in order of value)
1. A small web UI (drag a file, see the plain-language card and a deadline calendar). Judges respond to a visible product.
2. Image/PDF input via OCR, since real paperwork is often scans (today only UTF-8 text files work). Keep redaction after OCR.
3. A measured result for the video: e.g. run 20 synthetic documents and report deadline-extraction accuracy.

## Disclaimer
Explains documents in plain language. Not medical, legal or financial advice.
