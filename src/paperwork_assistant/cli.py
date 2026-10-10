"""Command line interface: paperwork explain|deadlines|ask|models|forget"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

from . import DISCLAIMER
from .assistant import ask, explain_document
from .memory import Memory
from .nebius_client import NebiusClient, NebiusError

def load_env(path: str = ".env") -> None:
    """Tiny .env loader so the project needs no extra dependency."""
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="paperwork", description="Plain-language paperwork assistant (Nemotron on Nebius).")
    sub = p.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("explain", help="explain a text file")
    e.add_argument("file")
    e.add_argument("--hide", action="append", default=[], help="a name to mask before sending (repeatable)")
    e.add_argument("--no-save", action="store_true", help="do not save to local memory")
    e.add_argument("--json", action="store_true")
    d = sub.add_parser("deadlines", help="list upcoming deadlines from saved documents")
    d.add_argument("--days", type=int, default=30)
    a = sub.add_parser("ask", help="ask about saved documents")
    a.add_argument("question")
    a.add_argument("--hide", action="append", default=[])
    sub.add_parser("models", help="list models your key can use")
    f = sub.add_parser("forget", help="delete saved documents")
    g = f.add_mutually_exclusive_group(required=True)
    g.add_argument("--id", type=int)
    g.add_argument("--all", action="store_true")
    return p

def main(argv: list[str] | None = None, client: NebiusClient | None = None) -> int:
    load_env()
    args = build_parser().parse_args(argv)
    memory = Memory(os.getenv("PAPERWORK_DB", "./paperwork.db"))
    try:
        if args.cmd == "deadlines":
            items = memory.upcoming(days=args.days)
            if not items:
                print(f"No deadlines in the next {args.days} days.")
            for i in items:
                print(f"{i['date']} {i['what']} ({i['title']}, doc {i['doc_id']})")
            return 0

        if args.cmd == "forget":
            n = memory.forget(None if args.all else args.id)
            print(f"Deleted {n} document(s).")
            return 0

        client = client or NebiusClient()
        if args.cmd == "models":
            print("\n".join(client.list_models()))
            return 0

        if args.cmd == "explain":
            text = Path(args.file).read_text(encoding="utf-8")
            out = explain_document(text, client, memory, hide=args.hide, save=not args.no_save)
            if args.json:
                print(json.dumps(out, indent=2, ensure_ascii=False))
            else:
                r = out["result"]
                print(f"{r['title']}  [{r['doc_type']}]\n\n{r['plain_summary']}\n")
                for label, key in (("Key points", "key_points"), ("Do next", "actions_needed"),
                                   ("Ask", "questions_to_ask"), ("Check carefully", "unclear_or_risky")):
                    if r[key]:
                        print(label + ":")
                        print("\n".join(f"  - {x}" for x in r[key]))
                for dl in r["deadlines"]:
                    print(f"Deadline: {dl['date'] or 'date unclear'} {dl['what']}")
                print(f"\n({out['identifiers_masked']} identifiers masked before sending.)\n{DISCLAIMER}")
            return 0
        if args.cmd == "ask":
            out = ask(args.question, client, memory, hide=args.hide)
            print(out["answer"] + "\n\n" + DISCLAIMER)
            return 0
    except (NebiusError, OSError, ValueError, sqlite3.Error) as e:
        # ValueError covers unusable model output (ModelOutputError) and files that are not UTF-8 text.
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
