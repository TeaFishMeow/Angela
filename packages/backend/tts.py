from __future__ import annotations

import asyncio
import base64
import io
import math
from pathlib import Path
import struct
import wave
from typing import Any

from protocol import Bus


VOICE_MAP = {
    "angela": "zh-CN-XiaoyiNeural",
    "neo": "zh-CN-YunxiNeural",
}

ROOT = Path(__file__).resolve().parents[2]


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


def _resolve_asset_path(path: str | None) -> Path | None:
    if not path:
        return None
    p = Path(path)
    if p.is_absolute():
        return p
    return ROOT / path


def _wav_duration_and_rms_frames(audio: bytes, fps: int = 30) -> tuple[float, list[float]]:
    with wave.open(io.BytesIO(audio), "rb") as wf:
        channels = wf.getnchannels()
        sample_width = wf.getsampwidth()
        sample_rate = wf.getframerate()
        raw = wf.readframes(wf.getnframes())
    if sample_width != 2 or not raw:
        duration = 0.8
        return duration, [0.0] * max(1, int(duration * fps))

    samples = list(struct.iter_unpack("<h", raw))
    if channels > 1:
        mono_values = []
        for i in range(0, len(samples), channels):
            group = samples[i : i + channels]
            if group:
                mono_values.append(sum(v[0] for v in group) / len(group))
    else:
        mono_values = [v[0] for v in samples]
    hop = max(1, sample_rate // fps)
    frames: list[float] = []
    for i in range(0, len(mono_values), hop):
        chunk = mono_values[i : i + hop]
        if not chunk:
            continue
        frames.append(math.sqrt(sum(v * v for v in chunk) / len(chunk)))
    peak = max(max(frames, default=1.0), 1.0)
    norm = [min(1.0, v / peak) for v in frames] or [0.0]
    smooth: list[float] = []
    for i, v in enumerate(norm):
        smooth.append((norm[max(0, i - 1)] + v + norm[min(len(norm) - 1, i + 1)]) / 3)
    duration = len(mono_values) / max(1, sample_rate)
    return duration, smooth


async def _send_prebaked_tts(bus: Bus, seq: int, text: str, voice: str, audio_path: Path) -> bool:
    if not audio_path.exists():
        return False
    audio = audio_path.read_bytes()
    await bus.send("tts.start", {"seq": seq, "text": text, "voice": voice, "prebaked": True})
    try:
        _, frames = _wav_duration_and_rms_frames(audio)
    except wave.Error:
        frames = [0.5] * max(1, int(max(1.0, len(text) * 0.16) * 30))
    for i, amp in enumerate(frames):
        t = i / 30
        await bus.send(
            "viseme.frame",
            {"t": round(t, 3), "params": {"ParamMouthOpenY": round(max(0.0, amp), 3), "ParamMouthForm": 0.2}},
            ts=t,
        )
    await bus.send(
        "tts.audio",
        {"seq": seq, "mime": "audio/wav", "b64": base64.b64encode(audio).decode("ascii"), "prebaked": True},
    )
    await bus.send("tts.end", {"seq": seq, "prebaked": True})
    return True


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


async def run_tts(
    bus: Bus, lines: str | dict[str, Any] | list[str | dict[str, Any]], voice: str = "angela", speaker: str | None = None
) -> None:
    if isinstance(lines, str):
        lines = [lines]
    elif isinstance(lines, dict):
        lines = [lines]
    if speaker is None:
        speaker = "Neo" if voice == "neo" else "Angela"

    await bus.send("action.set", {"name": "talk", "loop": True})
    for seq, item in enumerate(lines, start=1):
        if isinstance(item, dict):
            text = str(item.get("text", ""))
            cue_voice = str(item.get("voice") or voice)
            cue_speaker = str(item.get("speaker") or speaker)
            prebaked = _resolve_asset_path(item.get("prebaked") or item.get("audio"))
        else:
            text = str(item)
            cue_voice = voice
            cue_speaker = speaker
            prebaked = None
        await bus.send("subtitle", {"speaker": cue_speaker, "text": text})
        if prebaked and await _send_prebaked_tts(bus, seq, text, cue_voice, prebaked):
            continue
        try:
            await asyncio.wait_for(_send_edge_tts(bus, seq, text, cue_voice), timeout=8.0)
        except Exception as exc:
            await bus.send("error", {"code": "TTS_FAILED", "message": f"edge-tts unavailable: {exc}"})
            await _send_synthetic_tts(bus, seq, text, cue_voice)
    await bus.send("action.set", {"name": "idle", "loop": True})
