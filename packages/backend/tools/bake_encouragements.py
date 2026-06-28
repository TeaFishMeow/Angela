"""Pre-bake encouragement voice clips for roadshow playback.

Reads 演示用例/<scene>_分轨/encouragements.json. For each cue:
1. Generate a TTS wav with edge-tts.
2. If an RVC CLI and matching model exist, bake that wav into cue["prebaked"].
3. Otherwise copy the TTS wav to cue["prebaked"] so the roadshow still plays a local file,
   and write metadata marking that RVC was not applied.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import edge_tts


ROOT = Path(__file__).resolve().parents[3]
DEMO = ROOT / "演示用例"
SCENE_DIRS = {
    "chuanqi": DEMO / "传奇_分轨",
    "yinwei-aiqing": DEMO / "因为爱情_分轨",
}
VOICE_MAP = {
    "angela": "zh-CN-XiaoyiNeural",
    "neo": "zh-CN-YunxiNeural",
}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def rel(path: str) -> Path:
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


async def edge_tts_to_mp3(text: str, voice: str, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    communicate = edge_tts.Communicate(text, VOICE_MAP.get(voice, voice))
    await communicate.save(str(output))


def ffmpeg_to_wav(input_path: Path, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(input_path),
            "-ac",
            "1",
            "-ar",
            "24000",
            str(output_path),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def find_rvc_model(voice: str) -> tuple[Path | None, Path | None]:
    candidates = [
        ROOT / "packages" / "voice" / "models" / voice,
        ROOT / "RVC" / voice,
        ROOT / "RVC" / ("Azusa" if voice == "angela" else voice),
    ]
    for folder in candidates:
        if not folder.exists():
            continue
        pths = sorted(folder.glob("*.pth"))
        if not pths:
            continue
        indexes = sorted(folder.glob("*.index"))
        return pths[0], indexes[0] if indexes else None
    return None, None


def run_rvc(input_wav: Path, output_wav: Path, voice: str) -> bool:
    rvc = shutil.which("rvc")
    model, index = find_rvc_model(voice)
    if not rvc or not model:
        return False
    output_wav.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        rvc,
        "infer",
        "-m",
        str(model),
        "-i",
        str(input_wav),
        "-o",
        str(output_wav),
        "-p",
        "0",
        "-f0",
        "rmvpe",
    ]
    if index:
        cmd.extend(["-ir", str(index)])
    subprocess.run(cmd, check=True)
    return output_wav.exists()


async def bake_scene(scene_id: str, force: bool = False) -> list[dict[str, Any]]:
    scene_dir = SCENE_DIRS[scene_id]
    payload = read_json(scene_dir / "encouragements.json")
    results: list[dict[str, Any]] = []
    for cue in payload.get("cues", []):
        if not isinstance(cue, dict):
            continue
        cue_id = str(cue["id"])
        voice = str(cue.get("voice") or ("neo" if scene_id == "yinwei-aiqing" else "angela"))
        text = str(cue.get("text", ""))
        out = rel(str(cue["prebaked"]))
        work_dir = out.parent
        tts_mp3 = work_dir / f"{cue_id}_{voice}_tts.mp3"
        tts_wav = work_dir / f"{cue_id}_{voice}_tts.wav"
        meta = work_dir / f"{cue_id}_bake_meta.json"

        if force or not tts_wav.exists():
            await edge_tts_to_mp3(text, voice, tts_mp3)
            ffmpeg_to_wav(tts_mp3, tts_wav)

        used_rvc = False
        if force or not out.exists():
            try:
                used_rvc = run_rvc(tts_wav, out, voice)
            except Exception:
                used_rvc = False
            if not used_rvc:
                out.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(tts_wav, out)

        status = {
            "scene": scene_id,
            "id": cue_id,
            "voice": voice,
            "text": text,
            "tts_wav": str(tts_wav.relative_to(ROOT)),
            "prebaked": str(out.relative_to(ROOT)),
            "rvc_applied": used_rvc,
        }
        meta.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
        results.append(status)
    return results


async def main_async(args: argparse.Namespace) -> int:
    scene_ids = args.scene or list(SCENE_DIRS)
    all_results: list[dict[str, Any]] = []
    for scene_id in scene_ids:
        all_results.extend(await bake_scene(scene_id, force=args.force))
    print(json.dumps(all_results, ensure_ascii=False, indent=2))
    if any(not r["rvc_applied"] for r in all_results):
        print("[warn] Some clips used TTS wav fallback because RVC CLI/model was not available.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scene", choices=sorted(SCENE_DIRS), action="append")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
