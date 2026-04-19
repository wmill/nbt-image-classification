# schematic-analyzer

A batch analysis pipeline that uses a local vision LLM (via Ollama) to identify and describe Minecraft schematic files, generating structured metadata for Elasticsearch indexing. Intended to integrate with the `minecraft-api` MCP project to enable natural-language search and placement of schematics in-game via Claude.

---

## What It Does

1. Reads a directory of pre-rendered schematic views (orthographic PNGs + metadata JSON produced by a separate render tool)
2. Sends the images and block metadata to a local vision model via Ollama
3. Produces structured JSON per schematic: title, description, keywords, structure type, style, placement info, size category, confidence score
4. Writes results incrementally to a catalog JSON file suitable for bulk-indexing into Elasticsearch

---

## Input Format

Each schematic is expected to have its own subdirectory containing:

```
schematics/
  173/
    iso.png        # Isometric view — primary identification image
    top.png        # Top-down orthographic
    north.png
    south.png
    east.png
    west.png
    meta.json      # Block counts, dimensions, placement analysis (see below)
```

### `meta.json` Schema

```json
{
  "source": "/path/to/original.schematic",
  "size": { "width": 91, "height": 38, "depth": 93 },
  "non_air_block_count": 25147,
  "non_air_bbox": {
    "min_x": 0, "min_y": 0, "min_z": 0,
    "max_x": 90, "max_y": 32, "max_z": 92
  },
  "placement": {
    "has_base": true,
    "reason": "bottom layer 100% filled vs median 3% — likely has base",
    "bottom_fill": 1.0,
    "median_fill": 0.031
  },
  "top_blocks": [
    { "name": "minecraft:cobblestone", "count": 15896, "fraction": 0.632 },
    ...
  ]
}
```

---

## Output Format

Each analyzed schematic produces a record like:

```json
{
  "schematic_id": "173",
  "title": "Medieval Castle with Courtyard",
  "description": "A large walled fortress with crenellated battlements, corner towers, and an interior courtyard containing trees, a water feature, and farm plots. Built primarily from cobblestone with oak wood accents. A flagpole rises from the tallest corner tower.",
  "keywords": ["castle", "fortress", "medieval", "walls", "battlements", "courtyard", "tower", "moat", "gatehouse", "cobblestone", "large", "interior"],
  "structure_type": "fortification",
  "style": "medieval",
  "placement": {
    "type": "surface",
    "notes": "Has solid base, water at perimeter suggests moat or waterfront placement"
  },
  "size_category": "massive",
  "has_interior": true,
  "confidence": 0.95
}
```

All results are written incrementally to `schematic_catalog.json` so a failed run doesn't lose progress.

---

## Tech Stack

- **Runtime:** Python 3.11+
- **Vision LLM:** Ollama with `llama3.2-vision:11b` (default) — runs locally on macOS/Apple Silicon
- **Ollama Python SDK:** `ollama` pip package
- **Output:** JSON catalog file, ready for Elasticsearch bulk import

### Ollama Model Requirements

The default model is `llama3.2-vision:11b`. Pull it before first run:

```bash
ollama pull llama3.2-vision:11b
```

Other supported models (configure via env or CLI flag):
- `llava:13b` — fallback, good for pixel-art style images
- `llama3.2-vision:90b` — higher accuracy, slower (fine on M4 48GB)
- `moondream2` — very fast, lower accuracy

---

## Project Structure

```
schematic-analyzer/
  analyze.py          # Main entry point — batch analysis runner
  analyzer.py         # Core logic: image loading, prompt construction, Ollama call, JSON parsing
  config.py           # Configuration: model name, paths, prompt template
  prompt.txt          # The LLM prompt template (externalized for easy tuning)
  es_import.py        # (future) Elasticsearch bulk import helper
  requirements.txt
  README.md
```

---

## Usage

```bash
# Analyze all schematics in a directory
python analyze.py --input /path/to/rendered/schematics --output schematic_catalog.json

# Analyze a single schematic directory (for testing)
python analyze.py --input /path/to/rendered/schematics/173 --single

# Use a different model
python analyze.py --input ./schematics --model llava:13b

# Re-analyze only entries with confidence below threshold
python analyze.py --input ./schematics --reanalyze --min-confidence 0.7
```

---

## Configuration

All defaults can be overridden via environment variables or CLI flags:

| Config | Default | Description |
|--------|---------|-------------|
| `OLLAMA_MODEL` | `llama3.2-vision:11b` | Vision model to use |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama API endpoint |
| `VIEWS` | `iso,top,north,south,east,west` | Which views to send (comma-separated) |
| `PRIMARY_VIEWS` | `iso,top` | Fast mode: only send these two views |
| `FAST_MODE` | `false` | Use primary views only (faster, slightly less accurate) |

---

## Prompt Design Notes

The prompt is in `prompt.txt` and is designed to be tuned independently of the code. Key design decisions:

- **Iso view is primary** — the isometric render gives the most structural information at a glance
- **Block metadata is included** — helps disambiguate (e.g. "is that sand a desert biome or a beach?")
- **Placement is pre-analyzed** — `has_base` from metadata is passed to the model as context; the model is still asked to characterize placement type (surface/waterfront/elevated/floating/underground) from visual evidence
- **Structured JSON output only** — the prompt explicitly forbids markdown fences and preamble; the code strips them as a safety measure anyway
- **Confidence score** — lets downstream tooling flag schematics for human review; anything under 0.7 should be manually inspected

---

## Elasticsearch Integration (Planned)

The catalog JSON is designed for ES indexing with:

- Full-text search on `title`, `description`, `keywords`
- Keyword facets on `structure_type`, `style`, `placement.type`, `size_category`
- Numeric filters on block count and dimensions (passed through from meta.json)

The MCP integration will expose a `search_schematics` tool that queries ES and returns candidate schematics, then uses the existing `place_nbt_structure` API to place the selected one in-world.

---

## Future Work

- `es_import.py` — bulk import script for Elasticsearch
- MCP tool: `search_schematics(query, filters)` → returns matches with preview thumbnails
- MCP tool: `place_schematic(id, x, y, z)` → wraps existing `place_nbt_structure`
- Two-pass analysis: fast mode (iso+top) with auto-retry on low confidence using all 6 views
- Web UI for browsing and correcting catalog entries
