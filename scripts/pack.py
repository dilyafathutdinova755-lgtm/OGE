"""Packages rendered videos into one zip archive per group (playbook section 07)."""
from __future__ import annotations

import pathlib
import zipfile

GROUP_LABELS = {
    "english": "АНГЛИЙСКИЙ",
    "russian": "РУССКИЙ",
    "general": "ОБЩЕЕ",
    "gdz": "ГДЗ",
    "history": "ИСТОРИЯ",
}

DEFAULT_SIZE_LIMIT_MB = 35


def package_group(group: str, video_paths: list[pathlib.Path], archive_dir: pathlib.Path,
                   size_limit_mb: float = DEFAULT_SIZE_LIMIT_MB) -> pathlib.Path:
    label = GROUP_LABELS[group]
    archive_dir.mkdir(parents=True, exist_ok=True)
    zip_path = archive_dir / f"{label}.ВИДЕО.zip"

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED) as zf:
        for i, video_path in enumerate(video_paths, start=1):
            zf.write(video_path, arcname=f"{label}.ВИДЕО_{i}.mp4")

    size_mb = zip_path.stat().st_size / (1024 * 1024)
    if size_mb > size_limit_mb:
        print(f"  ! {zip_path.name}: {size_mb:.1f} МБ превышает лимит вложения {size_limit_mb} МБ")
    else:
        print(f"  {zip_path.name}: {size_mb:.1f} МБ ({len(video_paths)} роликов)")
    return zip_path
