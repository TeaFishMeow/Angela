"""Scene 数据层（路演版 proto v0.2）。

替 kom 的 songs.py：以 **scene（场）** 为单位，读 scene.json manifest + 轨道。
- manifest 优先级：演示用例/<曲>_分轨/scene.json（真值）→ assets/scenes/<id>/scene.json → data/samples/scene.<id>.json（兜底）
- 轨道（lyrics/visemes/actions）：分轨目录真值 → data/samples/<kind>.<id>.json → <kind>.sample.json
- backing.wav 未烘焙时 backing_url 回退 instrumental（纯伴奏，无数字人声）

字段约定见 docs/03；URL 前缀见 docs/02 §3.2 / docs/03 §7。
"""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "assets"
SAMPLES = ROOT / "data" / "samples"
SCENES_DIR = ASSETS / "scenes"
DEMO_ASSETS = ROOT / "演示用例"

# id → 分轨目录中文名（docs/03 §7：演示用例/<曲名>_分轨/）
SCENE_DIR = {"chuanqi": "传奇", "yinwei-aiqing": "因为爱情"}

# 路演两场固定顺序
DEFAULT_ORDER = ["chuanqi", "yinwei-aiqing"]

TRACK_KINDS = ("lyrics", "visemes", "actions")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _asset_url(path: str) -> str:
    """相对路径 → URL。演示用例/ 前缀走 /demo-assets/，其余走 /assets/。"""
    if not path:
        return ""
    if path.startswith("/"):
        return path
    if path.startswith("演示用例/"):
        return "/demo-assets/" + path[len("演示用例/"):]
    return "/assets/" + path


def _scene_dir_name(scene_id: str) -> str:
    return SCENE_DIR.get(scene_id, scene_id)


def _track_sample_file(scene_id: str, track: str) -> Path | None:
    specific = SAMPLES / f"{track}.{scene_id}.json"
    if specific.exists():
        return specific
    fallback = SAMPLES / f"{track}.sample.json"
    if fallback.exists():
        return fallback
    return None


def _scene_path(scene_id: str) -> Path | None:
    demo = DEMO_ASSETS / f"{_scene_dir_name(scene_id)}_分轨" / "scene.json"
    if demo.exists():
        return demo
    asset = SCENES_DIR / scene_id / "scene.json"
    if asset.exists():
        return asset
    sample = SAMPLES / f"scene.{scene_id}.json"
    if sample.exists():
        return sample
    return None


def list_scene_ids() -> list[str]:
    ids: set[str] = set()
    if SCENES_DIR.exists():
        ids.update(p.parent.name for p in SCENES_DIR.glob("*/scene.json"))
    ids.update(p.stem.removeprefix("scene.") for p in SAMPLES.glob("scene.*.json"))
    for sid, name in SCENE_DIR.items():
        if (DEMO_ASSETS / f"{name}_分轨" / "scene.json").exists():
            ids.add(sid)
    ordered = [s for s in DEFAULT_ORDER if s in ids]
    ordered += sorted(ids - set(ordered))
    return ordered


def load_scene(scene_id: str) -> dict[str, Any]:
    path = _scene_path(scene_id)
    if path is None:
        raise FileNotFoundError(scene_id)
    return read_json(path)


def public_manifest(scene_id: str) -> dict[str, Any]:
    manifest = deepcopy(load_scene(scene_id))
    audio = manifest.get("audio")
    if isinstance(audio, dict):
        for key, value in audio.items():
            if isinstance(value, str):
                audio[key] = _asset_url(value)
    for key in ("mv", "cover"):
        if isinstance(manifest.get(key), str):
            manifest[key] = _asset_url(manifest[key])
    return manifest


def scene_summary(scene_id: str) -> dict[str, Any]:
    m = public_manifest(scene_id)
    return {
        "id": m["id"],
        "title": m.get("title", m["id"]),
        "artist": m.get("artist", ""),
        "character": m.get("character", ""),
        "relation": m.get("relation", ""),
        "duration": m.get("duration", 0),
        "cover": m.get("cover", ""),
    }


def list_scenes() -> list[dict[str, Any]]:
    return [scene_summary(sid) for sid in list_scene_ids()]


def load_track(scene_id: str, track: str) -> dict[str, Any]:
    if track not in TRACK_KINDS:
        raise FileNotFoundError(f"{scene_id}:{track}")
    manifest = load_scene(scene_id)
    rel = manifest.get("tracks", {}).get(track)
    if isinstance(rel, str):
        candidate = ROOT / rel
        if candidate.exists():
            return read_json(candidate)
    sample = _track_sample_file(scene_id, track)
    if sample:
        return read_json(sample)
    raise FileNotFoundError(f"{scene_id}:{track}")


def load_encouragements(scene_id: str) -> dict[str, Any]:
    """鼓励语轨道：分轨目录真值 → assets/scenes/<id>/encouragements.json → data/samples/encouragements.<id>.json。"""
    demo = DEMO_ASSETS / f"{_scene_dir_name(scene_id)}_分轨" / "encouragements.json"
    if demo.exists():
        return read_json(demo)
    asset = SCENES_DIR / scene_id / "encouragements.json"
    if asset.exists():
        return read_json(asset)
    sample = SAMPLES / f"encouragements.{scene_id}.json"
    if sample.exists():
        return read_json(sample)
    return {"scene": scene_id, "cues": []}


def first_lyric_time(scene_id: str) -> float:
    try:
        lines = load_track(scene_id, "lyrics").get("lines", [])
    except FileNotFoundError:
        return 0.0
    ts = [float(ln.get("t", 0) or 0) for ln in lines if isinstance(ln, dict)]
    return min(ts) if ts else 0.0


def track_payload(scene_id: str) -> dict[str, Any]:
    """scene.tracks 下发：统一给 REST tracks URL，前端按 url 拉取（load_track 兜底）。"""
    return {track: {"url": f"/api/scenes/{scene_id}/tracks/{track}"} for track in TRACK_KINDS}


def character_of(scene_id: str) -> str:
    return str(load_scene(scene_id).get("character", "angela"))


def character_model(scene_id: str) -> str:
    m = load_scene(scene_id)
    return str(m.get("character_model") or f"models/{m.get('character', 'angela')}/model.model3.json")


def sing_action(scene_id: str) -> str:
    return "singing_low" if character_of(scene_id) == "neo" else "singing_high"


def backing_url(scene_id: str) -> str:
    """伴奏带 URL。backing.wav 未烘焙时回退 instrumental（纯伴奏、无数字人声）。"""
    m = load_scene(scene_id)
    audio = m.get("audio", {})
    backing = audio.get("backing")
    if isinstance(backing, str) and (ROOT / backing).exists():
        return _asset_url(backing)
    instrumental = audio.get("instrumental")
    if isinstance(instrumental, str):
        return _asset_url(instrumental)
    return _asset_url(backing or "")
