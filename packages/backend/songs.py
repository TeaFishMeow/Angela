from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "assets"
SAMPLES = ROOT / "data" / "samples"
SONGS_DIR = ASSETS / "songs"


SAMPLE_TRACK_FILES = {
    "lyrics": SAMPLES / "lyrics.daoxiang.json",
    "visemes": SAMPLES / "visemes.sample.json",
    "actions": SAMPLES / "actions.sample.json",
}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _asset_url(path: str) -> str:
    return path if path.startswith("/") else f"/assets/{path}"


def _song_path(song_id: str) -> Path | None:
    asset_path = SONGS_DIR / song_id / "song.json"
    if asset_path.exists():
        return asset_path

    sample_path = SAMPLES / f"song.{song_id}.json"
    if sample_path.exists():
        return sample_path

    return None


def list_song_ids() -> list[str]:
    ids: set[str] = set()
    if SONGS_DIR.exists():
        ids.update(path.parent.name for path in SONGS_DIR.glob("*/song.json"))
    ids.update(path.stem.removeprefix("song.") for path in SAMPLES.glob("song.*.json"))
    return sorted(ids)


def load_song(song_id: str) -> dict[str, Any]:
    path = _song_path(song_id)
    if path is None:
        raise FileNotFoundError(song_id)
    return read_json(path)


def public_manifest(song_id: str) -> dict[str, Any]:
    manifest = deepcopy(load_song(song_id))
    for section in ("audio", "tracks"):
        values = manifest.get(section)
        if isinstance(values, dict):
            for key, value in values.items():
                if isinstance(value, str):
                    values[key] = _asset_url(value)
    for key in ("mv", "cover"):
        if isinstance(manifest.get(key), str):
            manifest[key] = _asset_url(manifest[key])
    return manifest


def song_summary(song_id: str) -> dict[str, Any]:
    manifest = public_manifest(song_id)
    return {
        "id": manifest["id"],
        "title": manifest.get("title", manifest["id"]),
        "artist": manifest.get("artist", ""),
        "duration": manifest.get("duration", 0),
        "duet": manifest.get("duet", False),
        "cover": manifest.get("cover", ""),
    }


def list_songs() -> list[dict[str, Any]]:
    return [song_summary(song_id) for song_id in list_song_ids()]


def load_track(song_id: str, track: str) -> dict[str, Any]:
    manifest = load_song(song_id)
    rel = manifest.get("tracks", {}).get(track)
    if isinstance(rel, str):
        asset_path = ASSETS / rel
        if asset_path.exists():
            return read_json(asset_path)

    sample = SAMPLE_TRACK_FILES.get(track)
    if sample and sample.exists():
        return read_json(sample)

    raise FileNotFoundError(f"{song_id}:{track}")


def track_payload(song_id: str, inline_fallback: bool = True) -> dict[str, Any]:
    manifest = load_song(song_id)
    payload: dict[str, Any] = {}
    for track in ("lyrics", "visemes", "actions"):
        rel = manifest.get("tracks", {}).get(track)
        asset_path = ASSETS / rel if isinstance(rel, str) else None
        if asset_path and asset_path.exists():
            payload[track] = {"url": _asset_url(rel)}
        elif inline_fallback:
            payload[track] = load_track(song_id, track)
        elif isinstance(rel, str):
            payload[track] = {"url": _asset_url(rel)}
    return payload


def mix_url(song_id: str) -> str:
    manifest = load_song(song_id)
    mix = manifest.get("audio", {}).get("mix")
    if isinstance(mix, str):
        return _asset_url(mix)
    return f"/assets/songs/{song_id}/mix.wav"
