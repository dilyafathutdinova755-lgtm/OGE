#!/usr/bin/env python3
"""Parses the hook-bank docx files into per-group JSON hook banks (data/hooks/).

Two shapes are supported:
- a multi-section docx (300_хуков_ОГЭ_Тренажёр.docx) where each group is a
  numbered "N. <header>" line followed by its own numbered hooks;
- a flat single-group docx (200_хуков_ГДЗ.docx) that is just one numbered
  list for a single group.
"""
import json
import pathlib
import re
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "hooks"

MULTI_SECTION_SOURCES = [
    {
        "docx_glob": "300_*.docx",
        "sections": [
            ("english", "1. ОГЭ по английскому языку — 100 хуков"),
            ("russian", "2. ОГЭ по русскому языку — 100 хуков"),
            ("general", "3. Функции и общая реклама приложения — 100 хуков"),
        ],
    },
]

FLAT_SOURCES = [
    {"docx_glob": "200_*.docx", "group": "gdz"},
]


def load_paragraphs(docx_path: pathlib.Path) -> list[str]:
    with zipfile.ZipFile(docx_path) as z:
        xml = z.read("word/document.xml").decode("utf-8")
    paras = re.findall(r"<w:p[ >].*?</w:p>", xml, re.S)
    return [re.sub(r"<[^>]+>", "", p) for p in paras]


def numbered_lines(lines: list[str]) -> list[str]:
    hooks = []
    for line in lines:
        m = re.match(r"^\d+\.\s*(.+)$", line.strip())
        if m:
            hooks.append(m.group(1).strip())
    return hooks


def write_bank(group: str, hooks: list[str]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"{group}.json"
    out_path.write_text(json.dumps(hooks, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{group}: {len(hooks)} hooks -> {out_path.relative_to(ROOT)}")


def main() -> None:
    for source in MULTI_SECTION_SOURCES:
        matches = list(ROOT.glob(source["docx_glob"]))
        if not matches:
            continue
        texts = load_paragraphs(matches[0])
        sections = source["sections"]
        for idx, (group, header) in enumerate(sections):
            start = texts.index(header) + 1
            end = texts.index(sections[idx + 1][1]) if idx + 1 < len(sections) else len(texts)
            write_bank(group, numbered_lines(texts[start:end]))

    for source in FLAT_SOURCES:
        matches = list(ROOT.glob(source["docx_glob"]))
        if not matches:
            continue
        texts = load_paragraphs(matches[0])
        write_bank(source["group"], numbered_lines(texts))


if __name__ == "__main__":
    main()
