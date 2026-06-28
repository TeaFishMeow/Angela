from __future__ import annotations

import asyncio
import base64
import io
import math
import wave
from typing import Any

from protocol import Bus


VOICE_MAP = {
    "angela": "zh-CN-XiaoyiNeural",
    "neo": "zh-CN-YunxiNeural",
}


def _silence_wav(duration: float = 0.35, sample_rate: int = 24000) -> bytes:
    frames = int(duration * sample_rate)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x00\x00" * frames)
    return buf.getvalue()


async def _send_synthetic_tts(bus: Bus, seq: int, text: str, voice: str) -> None:
    await bus.send("tts.start", {"seq": seq, "text": text, "voice": voice})
    duration = max(1.0, min(6.0, len(text) * 0.16))
    steps = max(1, int(duration * 30))
    for i in range(steps):
        t = i / 30
        amp = max(0.0, 0.45 + 0.45 * math.sin(t * 15))
        await bus.send(
            "viseme.frame",
            {"t": round(t, 3), "params": {"ParamMouthOpenY": round(amp, 3), "ParamMouthForm": 0.2}},
            ts=t,
        )
        if i % 12 == 0:
            chunk = _silence_wav(0.35)
            await bus.send(
                "tts.audio",
                {"seq": seq, "mime": "audio/wav", "b64": base64.b64encode(chunk).decode("ascii")},
            )
        await asyncio.sleep(1 / 30)
    await bus.send("tts.end", {"seq": seq})


async def _send_edge_tts(bus: Bus, seq: int, text: str, voice: str) -> None:
    import edge_tts  # type: ignore

    edge_voice = VOICE_MAP.get(voice, voice)
    await bus.send("tts.start", {"seq": seq, "text": text, "voice": voice})
    communicate = edge_tts.Communicate(text, edge_voice)
    started = asyncio.get_running_loop().time()
    frame_i = 0
    async for chunk in communicate.stream():
        if chunk["type"] != "audio":
            continue
        elapsed = asyncio.get_running_loop().time() - started
        while frame_i / 30 <= elapsed + 0.1:
            t = frame_i / 30
            amp = max(0.0, 0.42 + 0.42 * math.sin(t * 15))
            await bus.send(
                "viseme.frame",
                {"t": round(t, 3), "params": {"ParamMouthOpenY": round(amp, 3), "ParamMouthForm": 0.2}},
                ts=t,
            )
            frame_i += 1
        await bus.send(
            "tts.audio",
            {"seq": seq, "mime": "audio/mpeg", "b64": base64.b64encode(chunk["data"]).decode("ascii")},
        )
    await bus.send("tts.end", {"seq": seq})


async def run_tts(bus: Bus, lines: str | list[str], voice: str = "angela") -> None:
    if isinstance(lines, str):
        lines = [lines]

    await bus.send("action.set", {"name": "talk", "loop": True})
    for seq, text in enumerate(lines, start=1):
        await bus.send("subtitle", {"speaker": "Angela", "text": text})
        try:
            await asyncio.wait_for(_send_edge_tts(bus, seq, text, voice), timeout=8.0)
        except Exception as exc:
            await bus.send("error", {"code": "TTS_FAILED", "message": f"edge-tts unavailable: {exc}"})
            await _send_synthetic_tts(bus, seq, text, voice)
    await bus.send("action.set", {"name": "idle", "loop": True})
