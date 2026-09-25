"""Install the pinned, unmodified Claude Agent SDK in a separate runtime."""
from pathlib import Path
import argparse

from prepare_document_runtime import prepare

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    prepare(args.python, args.destination,
            Path(__file__).resolve().parent.parent / "requirements-claude.txt",
            marker_name="proto-mind-claude-runtime.json")
