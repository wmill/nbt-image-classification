import json
import logging
import re
from pathlib import Path

import ollama

from composite import ORDER, build_composite, composite_to_png_bytes

log = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).parent / "prompt.txt"
_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _load_meta(schematic_dir: Path) -> dict | None:
    meta_path = schematic_dir / "meta.json"
    if not meta_path.is_file():
        log.warning("%s: missing meta.json", schematic_dir.name)
        return None
    try:
        return json.loads(meta_path.read_text())
    except json.JSONDecodeError as e:
        log.warning("%s: malformed meta.json (%s)", schematic_dir.name, e)
        return None


def _meta_excerpt(meta: dict) -> str:
    keep = {
        "size": meta.get("size"),
        "non_air_block_count": meta.get("non_air_block_count"),
        "placement": meta.get("placement"),
        "top_blocks": (meta.get("top_blocks") or [])[:10],
    }
    return json.dumps(keep, indent=2)


def _view_paths(schematic_dir: Path) -> dict[str, Path] | None:
    paths = {v: schematic_dir / f"{v}.png" for v in ORDER}
    missing = [p.name for p in paths.values() if not p.is_file()]
    if missing:
        log.warning("%s: missing views %s", schematic_dir.name, missing)
        return None
    return paths


def _strip_fences(text: str) -> str:
    return _FENCE_RE.sub("", text).strip()


def analyze_one(
    schematic_dir: Path,
    client: ollama.Client,
    model: str,
    prompt_template: str,
) -> dict | None:
    meta = _load_meta(schematic_dir)
    if meta is None:
        return None
    paths = _view_paths(schematic_dir)
    if paths is None:
        return None

    composite_png = composite_to_png_bytes(build_composite(paths))
    prompt = prompt_template.replace("{meta_excerpt}", _meta_excerpt(meta))

    try:
        resp = client.chat(
            model=model,
            messages=[{"role": "user", "content": prompt, "images": [composite_png]}],
            format="json",
            options={"temperature": 0.3, "num_predict": 2048},
        )
    except Exception as e:
        log.warning("%s: ollama call failed (%s)", schematic_dir.name, e)
        return None

    raw = resp["message"]["content"]
    try:
        record = json.loads(_strip_fences(raw), strict=False)
    except json.JSONDecodeError as e:
        log.warning("%s: model output not valid JSON (%s); raw=%r", schematic_dir.name, e, raw[:800])
        return None

    if not isinstance(record, dict):
        log.warning("%s: model output not a JSON object", schematic_dir.name)
        return None

    record["schematic_id"] = schematic_dir.name
    if "size" in meta:
        record.setdefault("size", meta["size"])
    if "non_air_block_count" in meta:
        record.setdefault("non_air_block_count", meta["non_air_block_count"])
    return record


def load_prompt() -> str:
    return PROMPT_PATH.read_text()
