"""Angela 后端（路演版 · proto v0.2）。

FastAPI + WebSocket。以 **scene（场）** 为单位：两场（传奇/Angela、因为爱情/Neo），
按 docs/02 proto v0.2 推流。契约见 docs/02，数据见 docs/03，管线见 docs/04。

REST:  GET /api/scenes、GET /api/scenes/{id}、GET /api/scenes/{id}/tracks/{track}
       GET /demo-assets/..、GET /assets/..   POST /api/tts
WS:    hello / scene.load / scene.start / scene.stop / outro.start / next.scene
       / scene.jump_outro / tts.request
"""
from __future__ import annotations

import asyncio
import json
from contextlib import suppress
from pathlib import Path
from typing import Any
import wave

from fastapi import FastAPI, HTTPException, Response, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

import scenes as scene_store
from protocol import Bus
from tts import run_tts


app = FastAPI(title="Angela Backend", version="0.2-roadshow")
app.mount("/demo-assets", StaticFiles(directory=scene_store.DEMO_ASSETS, check_dir=False), name="demo-assets")
app.mount("/assets", StaticFiles(directory=scene_store.ASSETS, check_dir=False), name="assets")
# 整合者加：后端单源托管前端（docs/04 §4），免 CORS。舞台开 /stage/index.html，WS 走同源 /ws。
app.mount("/stage", StaticFiles(directory=scene_store.ROOT / "packages" / "stage", check_dir=False), name="stage")
app.mount("/character", StaticFiles(directory=scene_store.ROOT / "packages" / "character", check_dir=False), name="character")


# ---------------- REST ----------------

@app.get("/api/scenes")
def api_scenes() -> list[dict[str, Any]]:
    return scene_store.list_scenes()


@app.get("/api/scenes/{scene_id}")
def api_scene(scene_id: str) -> dict[str, Any]:
    try:
        return scene_store.public_manifest(scene_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail={"code": "SCENE_NOT_FOUND", "message": scene_id})


@app.get("/api/scenes/{scene_id}/tracks/{track}")
def api_track(scene_id: str, track: str) -> dict[str, Any]:
    try:
        return scene_store.load_track(scene_id, track)
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail={"code": "TRACKS_MISSING", "message": f"{scene_id}:{track}"},
        )


@app.post("/api/tts")
async def api_tts(payload: dict[str, Any]) -> Response:
    # REST 兜底：无 edge-tts 流式上下文时返回一段可播放静音 wav。
    from tts import _silence_wav

    text = str(payload.get("text", ""))
    duration = max(0.4, min(4.0, len(text) * 0.08))
    return Response(content=_silence_wav(duration), media_type="audio/wav")


# ---------------- WS helpers ----------------

async def _tick_loop(bus: Bus, duration: float, stop: asyncio.Event) -> None:
    start = asyncio.get_running_loop().time()
    while not stop.is_set():
        t = asyncio.get_running_loop().time() - start
        if t > duration:
            break
        await bus.send("scene.tick", {"t": round(t, 3)}, ts=t)
        await asyncio.sleep(0.1)


def _cue_duration_seconds(cue: dict[str, Any]) -> float:
    prebaked = cue.get("prebaked") or cue.get("audio")
    if isinstance(prebaked, str) and prebaked:
        path = Path(prebaked)
        if not path.is_absolute():
            path = scene_store.ROOT / prebaked
        if path.exists() and path.suffix.lower() == ".wav":
            try:
                with wave.open(str(path), "rb") as wf:
                    return wf.getnframes() / max(1, wf.getframerate())
            except wave.Error:
                pass
    text = str(cue.get("text", ""))
    return max(1.0, min(6.0, len(text) * 0.16))


def _cue_fits_lyric_gap(scene_id: str, cue: dict[str, Any], guard: float = 0.45) -> bool:
    cue_t = float(cue.get("t", 0) or 0)
    cue_end = cue_t + _cue_duration_seconds(cue)
    try:
        lyrics = scene_store.load_track(scene_id, "lyrics").get("lines", [])
        manifest = scene_store.public_manifest(scene_id)
    except FileNotFoundError:
        return True

    intervals: list[tuple[float, float]] = []
    for line in lyrics:
        if not isinstance(line, dict):
            continue
        start = float(line.get("t", 0) or 0)
        dur = float(line.get("d", 0) or 0)
        if dur <= 0:
            continue
        intervals.append((start, start + dur))
    if not intervals:
        return True

    intervals.sort()
    prev_end = 0.0
    for start, end in intervals:
        if cue_t < start:
            return cue_t >= prev_end + guard and cue_end <= start - guard
        prev_end = max(prev_end, end)

    duration = float(manifest.get("duration", 0) or 0)
    return duration <= 0 or (cue_t >= prev_end + guard and cue_end <= duration - guard)


def _singing_start_time(scene_id: str) -> float:
    return 0.0


async def _encouragement_loop(bus: Bus, scene_id: str, stop: asyncio.Event, start_t: float) -> None:
    payload = scene_store.load_encouragements(scene_id)
    cues = [
        c
        for c in payload.get("cues", [])
        if isinstance(c, dict) and c.get("phase") != "prestart"
    ]
    if not cues:
        return
    start = asyncio.get_running_loop().time()
    for cue in sorted(cues, key=lambda c: float(c.get("t", 0) or 0)):
        cue_t = float(cue.get("t", 0) or 0)
        if cue_t < start_t - 0.05:
            continue
        wait = max(0.0, cue_t - start_t - (asyncio.get_running_loop().time() - start))
        try:
            await asyncio.wait_for(stop.wait(), timeout=wait)
            return
        except asyncio.TimeoutError:
            pass
        if stop.is_set():
            return
        if not _cue_fits_lyric_gap(scene_id, cue):
            continue
        await run_tts(bus, cue, voice=cue.get("voice") or scene_store.character_of(scene_id), speaker=cue.get("speaker"))


async def _run_prestart_encouragements(bus: Bus, scene_id: str, stop: asyncio.Event) -> None:
    payload = scene_store.load_encouragements(scene_id)
    cues = [
        c
        for c in payload.get("cues", [])
        if isinstance(c, dict) and c.get("phase") == "prestart"
    ]
    for cue in cues:
        if stop.is_set():
            return
        await run_tts(bus, cue, voice=cue.get("voice") or scene_store.character_of(scene_id), speaker=cue.get("speaker"))


def _speaker(character: str) -> str:
    return "Neo" if character == "neo" else "Angela"


async def _run_intro(bus: Bus, scene_id: str) -> None:
    stop = asyncio.Event()  # intro 不计时，仅占位以满足 _spawn 约定
    manifest = scene_store.public_manifest(scene_id)
    character = scene_store.character_of(scene_id)
    await bus.send(
        "scene.loaded",
        {"id": scene_id, "title": manifest.get("title"), "character": character, "manifest": manifest},
    )
    await bus.send("character.set", {"name": character, "model": scene_store.character_model(scene_id)})
    intro = manifest.get("dialogue", {}).get("intro", [])
    if intro:
        await run_tts(bus, intro, voice=character, speaker=_speaker(character))


async def _run_singing(bus: Bus, scene_id: str, stop: asyncio.Event) -> None:
    manifest = scene_store.public_manifest(scene_id)
    duration = float(manifest.get("duration", 0) or 0)
    await _run_prestart_encouragements(bus, scene_id, stop)
    if stop.is_set():
        return
    start_t = _singing_start_time(scene_id)
    remaining = max(0.0, duration - start_t)
    await bus.send("scene.tracks", scene_store.track_payload(scene_id))
    await bus.send("action.set", {"name": scene_store.sing_action(scene_id), "loop": True})
    await bus.send(
        "scene.start",
        {"id": scene_id, "backingUrl": scene_store.backing_url(scene_id), "t0": round(start_t, 3)},
    )
    ticker = asyncio.create_task(_tick_loop(bus, remaining, stop))
    encouragements = asyncio.create_task(_encouragement_loop(bus, scene_id, stop, start_t))
    try:
        with suppress(asyncio.TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=remaining)
    except asyncio.CancelledError:
        stop.set()
        ticker.cancel()
        encouragements.cancel()
        with suppress(asyncio.CancelledError):
            await ticker
        with suppress(asyncio.CancelledError):
            await encouragements
        raise
    finally:
        stop.set()
        ticker.cancel()
        encouragements.cancel()
        with suppress(asyncio.CancelledError):
            await ticker
        with suppress(asyncio.CancelledError):
            await encouragements
    await bus.send("scene.end", {"id": scene_id})


async def _run_outro(bus: Bus, scene_id: str) -> None:
    character = scene_store.character_of(scene_id)
    outro = scene_store.public_manifest(scene_id).get("dialogue", {}).get("outro", [])
    if outro:
        await run_tts(bus, outro, voice=character, speaker=_speaker(character))


# ---------------- WS endpoint ----------------

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    bus = Bus(ws)
    state: dict[str, Any] = {"task": None, "stop": asyncio.Event(), "scene": None}

    async def _cancel() -> None:
        state["stop"].set()
        task = state["task"]
        if task and not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await task
        state["task"] = None

    async def _safe(coro: Any) -> None:
        try:
            await coro
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await bus.send("error", {"code": "SCENE_RUN_FAIL", "message": str(exc)})

    async def _spawn_singing(scene_id: str) -> None:
        await _cancel()
        state["stop"] = asyncio.Event()
        state["scene"] = scene_id
        state["task"] = asyncio.create_task(_safe(_run_singing(bus, scene_id, state["stop"])))

    async def _spawn(coro: Any, scene_id: str | None = None) -> None:
        await _cancel()
        state["stop"] = asyncio.Event()
        if scene_id:
            state["scene"] = scene_id
        state["task"] = asyncio.create_task(_safe(coro))

    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await bus.send("error", {"code": "WS_PROTOCOL", "message": "bad json"})
                continue

            msg_type = msg.get("type")
            data = msg.get("data") or {}

            if msg_type == "hello":
                await bus.send("hello", {"role": "backend", "proto": "0.2"})
                await bus.send("scene.list", {"scenes": scene_store.list_scenes()})

            elif msg_type == "scene.load":
                scene_id = data.get("id", "chuanqi")
                try:
                    scene_store.load_scene(scene_id)
                except FileNotFoundError:
                    await bus.send("error", {"code": "SCENE_NOT_FOUND", "message": scene_id})
                    continue
                await _spawn(_run_intro(bus, scene_id), scene_id)

            elif msg_type == "scene.start":
                scene_id = data.get("id") or state["scene"] or "chuanqi"
                try:
                    scene_store.load_scene(scene_id)
                except FileNotFoundError:
                    await bus.send("error", {"code": "SCENE_NOT_FOUND", "message": scene_id})
                    continue
                await _spawn_singing(scene_id)

            elif msg_type == "scene.stop":
                scene_id = data.get("id") or state["scene"]
                await _cancel()
                if scene_id:
                    await bus.send("scene.end", {"id": scene_id})

            elif msg_type == "scene.jump_outro":
                scene_id = data.get("id") or state["scene"]
                await _cancel()
                if scene_id:
                    await bus.send("scene.end", {"id": scene_id})
                await bus.send("phase.change", {"phase": "outro"})
                if scene_id:
                    await _spawn(_run_outro(bus, scene_id), scene_id)

            elif msg_type == "outro.start":
                scene_id = data.get("id") or state["scene"]
                if scene_id:
                    try:
                        scene_store.load_scene(scene_id)
                    except FileNotFoundError:
                        await bus.send("error", {"code": "SCENE_NOT_FOUND", "message": scene_id})
                        continue
                    await _spawn(_run_outro(bus, scene_id), scene_id)

            elif msg_type == "next.scene":
                cur = data.get("id") or state["scene"] or "chuanqi"
                nxt = "yinwei-aiqing" if cur == "chuanqi" else "chuanqi"
                try:
                    scene_store.load_scene(nxt)
                except FileNotFoundError:
                    await bus.send("error", {"code": "SCENE_NOT_FOUND", "message": nxt})
                    continue
                await _spawn(_run_intro(bus, nxt), nxt)

            elif msg_type == "tts.request":
                text = str(data.get("text", ""))
                voice = data.get("voice", "angela")
                await _spawn(run_tts(bus, [text], voice=voice))

            else:
                await bus.send("error", {"code": "WS_PROTOCOL", "message": f"unknown type {msg_type}"})

    except WebSocketDisconnect:
        await _cancel()
