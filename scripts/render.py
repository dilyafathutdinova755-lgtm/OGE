#!/usr/bin/env python3
"""Renders the 15-second hook/photo/tail videos described in the playbook
and packages them into per-group zip archives.

Usage:
    python3 scripts/render.py batch --per-group 3 --out-dir out/2026-09-16
    python3 scripts/render.py adhoc --group english --count 2 --out-dir out/adhoc
"""
from __future__ import annotations

import argparse
import json
import pathlib
import shutil
import subprocess
import tempfile

from pack import package_group
from state_store import GROUPS, StateStore
from text_overlay import CANVAS_H, CANVAS_W, build_overlay

ROOT = pathlib.Path(__file__).resolve().parent.parent
HOOKS_DIR = ROOT / "data" / "hooks"
TAIL_DIR = ROOT / "assets" / "tail"
AUDIO_DIR = ROOT / "assets" / "audio"

DEFAULT_HOOK_DURATION = 6.0
FPS = 60
TARGET_TOTAL_DURATION = 15.02
TEXT_FADE_START = 0.5
TEXT_FADE_DURATION = 0.4

# Groups where the tail clip ends on something that must not get cut off
# (e.g. the App Store screen). For these, the hook segment shrinks below
# DEFAULT_HOOK_DURATION as needed so the *whole* tail clip plays out within
# the music track's length, down to MIN_HOOK_DURATION.
FLEXIBLE_HOOK_GROUPS = {"gdz"}
MIN_HOOK_DURATION = 3.0

VIDEO_CODEC_ARGS = ["-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p", "-r", str(FPS)]
AUDIO_CODEC_ARGS = ["-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2"]


def run(cmd: list[str]) -> None:
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(cmd)}\n{result.stdout}")


def probe_duration(path: pathlib.Path) -> float:
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)]
    out = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return float(out.stdout.strip())


def load_pool(pattern_dir: pathlib.Path, glob: str) -> list[pathlib.Path]:
    return sorted(pattern_dir.glob(glob))


def load_photo_pool() -> list[pathlib.Path]:
    return sorted(ROOT.glob("*.jpeg"))


def load_hook_pool(group: str) -> list[str]:
    return json.loads((HOOKS_DIR / f"{group}.json").read_text(encoding="utf-8"))


def render_hook_segment(photo_path: pathlib.Path, hook_text: str, out_path: pathlib.Path,
                         tmp_dir: pathlib.Path, duration: float) -> None:
    overlay_img, _ = build_overlay(photo_path, hook_text)
    overlay_path = tmp_dir / "overlay.png"
    overlay_img.save(overlay_path)

    frames = max(2, round(duration * FPS))
    bg_chain = (
        f"scale={CANVAS_W}:{CANVAS_H}:force_original_aspect_ratio=increase,"
        f"crop={CANVAS_W}:{CANVAS_H},"
        f"scale={CANVAS_W * 4}:{CANVAS_H * 4}:flags=lanczos,"
        f"zoompan=z='1+0.08*on/{frames - 1}':d={frames}:s={CANVAS_W}x{CANVAS_H}:fps={FPS},"
        f"format=yuv420p[bg]"
    )
    ov_chain = (
        f"format=yuva420p,"
        f"fade=t=in:st={TEXT_FADE_START}:d={TEXT_FADE_DURATION}:alpha=1[ov]"
    )
    filter_complex = f"[0:v]{bg_chain};[1:v]{ov_chain};[bg][ov]overlay=0:0:format=auto[outv]"

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-t", str(duration), "-i", str(photo_path),
        "-loop", "1", "-t", str(duration), "-i", str(overlay_path),
        "-filter_complex", filter_complex,
        "-map", "[outv]",
        "-t", str(duration),
        *VIDEO_CODEC_ARGS, "-an",
        str(out_path),
    ]
    run(cmd)


def render_tail_segment(tail_path: pathlib.Path, duration: float, out_path: pathlib.Path) -> None:
    vf = (
        f"scale={CANVAS_W}:{CANVAS_H}:force_original_aspect_ratio=increase,"
        f"crop={CANVAS_W}:{CANVAS_H},fps={FPS},format=yuv420p"
    )
    cmd = [
        "ffmpeg", "-y",
        "-i", str(tail_path),
        "-t", str(duration),
        "-vf", vf,
        *VIDEO_CODEC_ARGS, "-an",
        str(out_path),
    ]
    run(cmd)


def concat_segments(hook_path: pathlib.Path, tail_path: pathlib.Path, out_path: pathlib.Path, tmp_dir: pathlib.Path) -> None:
    list_path = tmp_dir / "concat.txt"
    list_path.write_text(f"file '{hook_path}'\nfile '{tail_path}'\n", encoding="utf-8")
    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_path), "-c", "copy", str(out_path)]
    run(cmd)


def mux_audio(video_path: pathlib.Path, music_path: pathlib.Path, duration: float, out_path: pathlib.Path) -> None:
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-i", str(music_path),
        "-t", str(duration),
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "copy", *AUDIO_CODEC_ARGS,
        "-shortest",
        str(out_path),
    ]
    run(cmd)


def render_one(group: str, state: StateStore, out_path: pathlib.Path) -> None:
    hooks = load_hook_pool(group)
    photos = load_photo_pool()
    tails = load_pool(TAIL_DIR / group, "*.mov")
    tracks = load_pool(AUDIO_DIR, "*.m4a")

    hook_text = hooks[state.next_from_pool("hooks", group, len(hooks))]
    photo_path = photos[state.next_from_pool("photos", None, len(photos))]
    tail_path = tails[state.next_round_robin("tails", group, len(tails))]
    music_path = tracks[state.next_round_robin("music", None, len(tracks))]

    music_duration = probe_duration(music_path)
    target_total = min(TARGET_TOTAL_DURATION, music_duration)
    tail_source_duration = probe_duration(tail_path)

    if group in FLEXIBLE_HOOK_GROUPS:
        # Shrink the hook (down to MIN_HOOK_DURATION) so the tail clip plays
        # out in full whenever the music track allows it - the tail ends on
        # the app's own promo/App Store screen and must not get cut short.
        tail_duration = min(tail_source_duration, max(0.0, target_total - MIN_HOOK_DURATION))
        hook_duration = target_total - tail_duration
    else:
        hook_duration = DEFAULT_HOOK_DURATION
        tail_duration = max(0.0, target_total - hook_duration)
        tail_duration = min(tail_duration, tail_source_duration)

    with tempfile.TemporaryDirectory(prefix="render_") as tmp:
        tmp_dir = pathlib.Path(tmp)
        hook_seg = tmp_dir / "hook.mp4"
        tail_seg = tmp_dir / "tail.mp4"
        concat_out = tmp_dir / "concat.mp4"

        render_hook_segment(photo_path, hook_text, hook_seg, tmp_dir, hook_duration)
        if tail_duration > 0:
            render_tail_segment(tail_path, tail_duration, tail_seg)
            concat_segments(hook_seg, tail_seg, concat_out, tmp_dir)
        else:
            concat_out = hook_seg

        out_path.parent.mkdir(parents=True, exist_ok=True)
        mux_audio(concat_out, music_path, target_total, out_path)

    print(f"  {out_path.name}  hook=\"{hook_text[:40]}...\"  photo={photo_path.name}  "
          f"tail={tail_path.name}  music={music_path.name}  total={target_total:.2f}s")


def cmd_batch(args: argparse.Namespace) -> None:
    state = StateStore()
    out_root = pathlib.Path(args.out_dir)
    groups = args.groups.split(",") if args.groups else list(GROUPS)
    archives = []
    for group in groups:
        print(f"[{group}]")
        video_paths = []
        for i in range(1, args.per_group + 1):
            out_path = out_root / group / f"{group}_{i}.mp4"
            render_one(group, state, out_path)
            video_paths.append(out_path)
        archives.append(package_group(group, video_paths, out_root))
    state.save()
    print("\nГотово:")
    for a in archives:
        print(f"  {a}")


def cmd_adhoc(args: argparse.Namespace) -> None:
    state = StateStore()
    out_root = pathlib.Path(args.out_dir)
    print(f"[{args.group}] внеплановая мини-партия x{args.count}")
    video_paths = []
    for i in range(1, args.count + 1):
        out_path = out_root / args.group / f"{args.group}_{i}.mp4"
        render_one(args.group, state, out_path)
        video_paths.append(out_path)
    package_group(args.group, video_paths, out_root)
    state.save()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_batch = sub.add_parser("batch", help="Плановая партия: N роликов на каждую активную группу")
    p_batch.add_argument("--per-group", type=int, required=True)
    p_batch.add_argument("--out-dir", default="out/batch")
    p_batch.add_argument("--groups", help=f"Через запятую, по умолчанию все: {','.join(GROUPS)}")
    p_batch.set_defaults(func=cmd_batch)

    p_adhoc = sub.add_parser("adhoc", help="Внеплановая мини-партия для одной группы")
    p_adhoc.add_argument("--group", choices=GROUPS, required=True)
    p_adhoc.add_argument("--count", type=int, required=True)
    p_adhoc.add_argument("--out-dir", default="out/adhoc")
    p_adhoc.set_defaults(func=cmd_adhoc)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
