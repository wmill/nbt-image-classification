# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A batch analysis pipeline that classifies pre-rendered Minecraft schematic views using a local Ollama vision model and writes a JSON catalog suitable for Elasticsearch bulk import. The README covers the full design vision — this doc covers what's actually implemented and why it's shaped the way it is.

## Architecture

The pipeline is a single-machine, sequential batch job — not a service.

- `analyze.py` — CLI entry and the run loop. Parses args, loads any existing catalog for resumability, walks `--input` subdirs, calls `analyze_one` per schematic, and atomically rewrites the catalog after each successful record.
- `analyzer.py` — `analyze_one(schematic_dir, client, model, prompt_template)` does the per-schematic work: load `meta.json`, collect 6 PNGs, render the prompt, call Ollama, strip markdown fences, `json.loads`, inject `schematic_id` + pass-through meta fields.
- `prompt.txt` — the model prompt, externalized so it can be tuned without code changes. Uses `{meta_excerpt}` as a format placeholder.
- `nbt-out/` — input fixture (git-ignored, ~11k schematic subdirs). Each subdir has `iso/top/north/south/east/west.png` + `meta.json`.

Key cross-cutting decisions:

- **`meta.json` is pre-computed context, not derived here.** The render tool (separate project) computes block counts, bbox, and a heuristic `placement.has_base`. We only pass a trimmed excerpt (`size`, `non_air_block_count`, `placement`, `top_blocks[:10]`) to the model. The README flags `has_base` as "simplistic, it could be wrong" — treat it as a hint, not ground truth.
- **Resumability is load-then-skip.** On startup `analyze.py` reads `--output` (if it exists) as a JSON array, builds a set of completed `schematic_id`s, and skips them. This means you can Ctrl-C at any point and rerun with the same args. A corrupt existing catalog aborts the run rather than overwriting.
- **Per-record atomic writes.** After each successful `analyze_one`, the full catalog is rewritten to `output.tmp` then `os.replace`d into place. O(n²) bytes over a run but `n≈11k` small records is cheap and survives mid-run kills without partial writes.
- **Failure is per-record.** Missing files, bad meta JSON, Ollama errors, or non-JSON model output all log a warning and continue — they never poison the catalog.
- **Deliberately not in v1**: fast mode / `--fast`, `--single`, `--reanalyze`, two-pass retry on low confidence, `es_import.py`, parallel workers. The README describes these; add them incrementally.

## Commands

```bash
# First-time setup
ollama pull llama3.2-vision:11b
uv sync

# Smoke test on one schematic
uv run analyze.py --input ./nbt-out --limit 1 --output /tmp/smoke.json

# Full run (defaults: ./nbt-out → ./schematic_catalog.json)
uv run analyze.py

# Override model / host
uv run analyze.py --model llava:13b --host http://localhost:11434
```

Python 3.13 is pinned via `.python-version`; `uv` manages deps. Only runtime dep is `ollama`.

## Environment variables

- `OLLAMA_MODEL` — default for `--model` (fallback `llama3.2-vision:11b`).
- `OLLAMA_HOST` — default for `--host` (fallback `http://localhost:11434`).

## Downstream

Catalog records are designed for Elasticsearch: full-text on `title`/`description`/`keywords`, keyword facets on `structure_type`/`style`/`placement.type`/`size_category`, numeric filters on `non_air_block_count` and `size.{width,height,depth}`. A separate `minecraft-api` MCP project will query ES and place chosen schematics in-world. Keep the record schema stable.
