import argparse
import json
import logging
import os
import sys
from pathlib import Path

import ollama

from analyzer import analyze_one, load_prompt

log = logging.getLogger("analyze")

DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2-vision:11b")
DEFAULT_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Batch-analyze Minecraft schematic renders with a local vision LLM.")
    p.add_argument("--input", type=Path, default=Path("./nbt-out"), help="Directory of <id>/ schematic subdirs (default: ./nbt-out).")
    p.add_argument("--output", type=Path, default=Path("./schematic_catalog.json"), help="Catalog JSON file (default: ./schematic_catalog.json).")
    p.add_argument("--model", default=DEFAULT_MODEL, help=f"Ollama vision model (default: {DEFAULT_MODEL}).")
    p.add_argument("--host", default=DEFAULT_HOST, help=f"Ollama host URL (default: {DEFAULT_HOST}).")
    p.add_argument("--limit", type=int, default=None, help="Stop after this many new schematics (for smoke tests).")
    return p.parse_args()


def load_existing(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        log.error("Existing catalog at %s is not valid JSON (%s). Refusing to overwrite.", path, e)
        sys.exit(1)
    if not isinstance(data, list):
        log.error("Existing catalog at %s is not a JSON array.", path)
        sys.exit(1)
    return data


def write_atomic(path: Path, records: list[dict]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(records, indent=2))
    os.replace(tmp, path)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = parse_args()

    if not args.input.is_dir():
        log.error("Input directory does not exist: %s", args.input)
        return 2

    records = load_existing(args.output)
    done = {r.get("schematic_id") for r in records if isinstance(r, dict)}
    log.info("Loaded %d existing records from %s", len(records), args.output)

    subdirs = sorted(p for p in args.input.iterdir() if p.is_dir())
    pending = [p for p in subdirs if p.name not in done]
    log.info("Found %d subdirs in %s (%d already done, %d pending)", len(subdirs), args.input, len(subdirs) - len(pending), len(pending))

    client = ollama.Client(host=args.host)
    prompt_template = load_prompt()

    processed = 0
    for sub in pending:
        if args.limit is not None and processed >= args.limit:
            break
        log.info("[%d/%s] analyzing %s", processed + 1, args.limit or len(pending), sub.name)
        record = analyze_one(sub, client=client, model=args.model, prompt_template=prompt_template)
        if record is None:
            continue
        records.append(record)
        write_atomic(args.output, records)
        processed += 1

    log.info("Done. %d new records written. Catalog now has %d total.", processed, len(records))
    return 0


if __name__ == "__main__":
    sys.exit(main())
