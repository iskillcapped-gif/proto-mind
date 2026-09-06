#!/usr/bin/env python3
"""Measure local project-note selection on disposable RU/UK/EN examples."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from proto_mind.project_recall_evals import evaluate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=ROOT / "evals/project_recall/cases.json")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    raw = args.corpus.read_bytes()
    report = evaluate(json.loads(raw))
    report["corpus_sha256"] = hashlib.sha256(raw).hexdigest()
    if args.output:
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({key: value for key, value in report.items() if key != "results"},
                     ensure_ascii=False, indent=2))
    for row in report["results"]:
        if not row["pass"]:
            print(f'{row["mode"]} {row["id"]}: expected={row["expected"]}, selected={row["selected"]}')
    return 0 if all(row["pass"] for row in report["results"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
