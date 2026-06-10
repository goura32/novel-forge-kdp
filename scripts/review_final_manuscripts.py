from __future__ import annotations

import json
from pathlib import Path

from novel_forge_kdp.llm import OllamaOpenAIClient
from novel_forge_kdp.prompts import PromptStore
from novel_forge_kdp.schemas import load_schema

ROOT = Path("project_novel/isekai-cafe-mahou-no-coffee")
MODEL = "qwen3.6:35b-a3b-mtp-q4_K_M"
BASE_URL = "http://ws1.local:11434"


def main() -> int:
    series = json.loads((ROOT / "series_plan.json").read_text(encoding="utf-8"))
    prompts = PromptStore()
    schema = load_schema("volume_review")
    for volume_dir in sorted(ROOT.glob("volume_[0-9][0-9][0-9]")):
        manuscript_path = volume_dir / "exports" / "manuscript.md"
        if not manuscript_path.exists():
            manuscript_path = volume_dir / "volume_revised.md"
        manuscript = manuscript_path.read_text(encoding="utf-8")
        client = OllamaOpenAIClient(
            base_url=BASE_URL,
            model=MODEL,
            timeout_seconds=3600,
            log_dir=ROOT / "raw_logs",
        )
        review = client.complete_json(
            task=f"final_quality_review_{volume_dir.name}",
            messages=[
                {"role": "system", "content": "You are a professional Japanese KDP commercial fiction editor. Return only valid JSON matching the requested schema. Do not use markdown fences."},
                {"role": "user", "content": prompts.render("volume_review", series=json.dumps(series, ensure_ascii=False), manuscript=manuscript)},
            ],
            schema=schema,
        )
        out = volume_dir / "final_quality_review.json"
        out.write_text(json.dumps(review, ensure_ascii=False, indent=2), encoding="utf-8")
        print(volume_dir.name, review.get("score"), review.get("ready_for_publication"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
