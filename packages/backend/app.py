from __future__ import annotations

import asyncio
import json
from contextlib import suppress
from typing import Any

from fastapi import FastAPI, HTTPException, Response, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

import songs as song_store
from protocol import Bus
from tts import run_tts


app = FastAPI(title="Angela Backend", version="0.1")
app.mount("/assets", StaticFiles(directory=song_store.ASSETS, check_dir=False), name="assets")
app.mount("/demo-assets", StaticFiles(directory=song_store.DEMO_ASSETS, check_dir=False), name="demo-assets")


@app.get("/api/songs")
def api_songs() -> list[dict[str, Any]]:
    return song_store.list_songs()


@app.get("/api/songs/{song_id}")
def api_song(song_id: str) -> dict[str, Any]:
    try:
        return song_store.public_manifest(song_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail={"code": "SONG_NOT_FOUND", "message": song_id})


@app.get("/api/songs/{song_id}/tracks/{track}")
def api_track(song_id: str, track: str) -> dict[str, Any]:
    if track not in {"lyrics", "visemes", "actions"}:
        raise HTTPException(status_code=404, detail={"code": "TRACK_NOT_FOUND", "message": track})
    try:
        return song_store.load_track(song_id, track)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail={"code": "TRACKS_MISSING", "message": f"{song_id}:{track}"})


@app.post("/api/tts")
async def api_tts(payload: dict[str, Any]) -> Response:
    # REST 兜底接口保持简单：无 edge-tts 流式上下文时返回一段可播放静音 wav。
    from tts import _silence_wav

    text = str(payload.get("text", ""))
    duration = max(0.4, min(4.0, len(text) * 0.08))
    return Response(content=_silence_wav(duration), media_type="audio/wav")


async def _tick_loop(bus: Bus, duration: float, stop: asyncio.Event) -> None:
    start = asyncio.get_running_loop().time()
    while not stop.is_set():
        t = asyncio.get_running_loop().time() - start
        if t > duration:
            break
        await bus.send("song.tick", {"t": round(t, 3)}, ts=t)
        await asyncio.sleep(0.1)


async def _start_song(bus: Bus, song_id: str, stop: asyncio.Event) -> None:
    manifest = song_store.public_manifest(song_id)
    duration = float(manifest.get("duration", 0) or 0)
    start_action = manifest.get("stage", {}).get("startAction", "singing_high")
    await bus.send("song.tracks", song_store.track_payload(song_id))
    await bus.send("phase.change", {"phase": "singing"})
    await bus.send("action.set", {"name": start_action, "loop": True})
    await bus.send("song.start", {"id": song_id, "mixUrl": song_store.mix_url(song_id), "t0": 0})

    ticker = asyncio.create_task(_tick_loop(bus, duration, stop))
    try:
        with suppress(asyncio.TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=duration)
    except asyncio.CancelledError:
        stop.set()
        ticker.cancel()
        with suppress(asyncio.CancelledError):
            await ticker
        return
    finally:
        stop.set()
        ticker.cancel()
        with suppress(asyncio.CancelledError):
            await ticker

    await bus.send("song.end", {"id": song_id})
    await bus.send("phase.change", {"phase": "finale"})
    finale = manifest.get("dialogue", {}).get("finale", [])
    if finale:
        await run_tts(bus, finale)


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    bus = Bus(ws)
    stop = asyncio.Event()
    current_task: asyncio.Task[None] | None = None

    async def cancel_song() -> None:
        nonlocal current_task
        stop.set()
        if current_task:
            current_task.cancel()
            with suppress(asyncio.CancelledError):
                await current_task
            current_task = None

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
                await bus.send(
                    "hello",
                    {"role": "backend", "proto": "0.1", "songs": [s["id"] for s in song_store.list_songs()]},
                )

            elif msg_type == "song.select":
                song_id = data.get("id", "daoxiang")
                try:
                    manifest = song_store.public_manifest(song_id)
                except FileNotFoundError:
                    await bus.send("error", {"code": "SONG_NOT_FOUND", "message": song_id})
                    continue
                await cancel_song()
                stop = asyncio.Event()
                await bus.send("phase.change", {"phase": "select"})
                await bus.send("song.loaded", {"id": song_id, "title": manifest.get("title"), "manifest": manifest})
                selected = manifest.get("dialogue", {}).get("selected", [])
                if selected:
                    await run_tts(bus, selected)

            elif msg_type == "song.start":
                song_id = data.get("id", "daoxiang")
                try:
                    song_store.load_song(song_id)
                except FileNotFoundError:
                    await bus.send("error", {"code": "SONG_NOT_FOUND", "message": song_id})
                    continue
                await cancel_song()
                stop = asyncio.Event()
                current_task = asyncio.create_task(_start_song(bus, song_id, stop))

            elif msg_type == "song.stop":
                await cancel_song()
                await bus.send("song.end", {"id": data.get("id", "daoxiang")})
                await bus.send("phase.change", {"phase": "select"})

            elif msg_type == "finale.start":
                await cancel_song()
                await bus.send("phase.change", {"phase": "finale"})
                await run_tts(bus, ["今天唱得真不错呢，下次我们再一起练好不好？"])

            elif msg_type == "tts.request":
                await run_tts(bus, str(data.get("text", "")))

            else:
                await bus.send("error", {"code": "WS_PROTOCOL", "message": f"unknown type {msg_type}"})

    except WebSocketDisconnect:
        await cancel_song()
