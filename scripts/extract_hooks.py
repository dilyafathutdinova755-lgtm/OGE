#!/usr/bin/env python3
"""Parse 300_хуков_ОГЭ_Тренажёр.docx into per-group JSON hook banks."""
import glob
import json
import pathlib
import re
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "hooks"

SECTIONS = [
    ("english", "1. ОГЭ по английскому языку — 100 хуков"),
    ("russian", "2. ОГЭ по русскому языку — 100 хуков"),
    ("general", "3. Функции и общая реклама приложения — 100 хуков"),
]


def load_paragraphs() -> list[str]:
    docx_path = glob.glob(str(ROOT / "*.docx"))[0]
    with zipfile.ZipFile(docx_path) as z:
        xml = z.read("word/document.xml").decode("utf-8")
    paras = re.findall(r"<w:p[ >].*?</w:p>", xml, re.S)
    return [re.sub(r"<[^>]+>", "", p) for p in paras]


def main() -> None:
    texts = load_paragraphs()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for idx, (group, header) in enumerate(SECTIONS):
        start = texts.index(header) + 1
        end = texts.index(SECTIONS[idx + 1][1]) if idx + 1 < len(SECTIONS) else len(texts)
        hooks = []
        for line in texts[start:end]:
            m = re.match(r"^\d+\.\s*(.+)$", line.strip())
            if m:
                hooks.append(m.group(1).strip())
        assert len(hooks) == 100, f"{group}: expected 100 hooks, got {len(hooks)}"
        out_path = OUT_DIR / f"{group}.json"
        out_path.write_text(json.dumps(hooks, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"{group}: {len(hooks)} hooks -> {out_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
