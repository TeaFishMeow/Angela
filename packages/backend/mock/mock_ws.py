"""
Angela 合唱模式 — Mock WebSocket 服务（联调用）
================================================
纯 Python、仅依赖 `websockets`。让舞台前端与数字人模块不必等真后端即可跑通三幕。
信封/字段与真后端完全一致（见 docs/02-接口契约.md）。

用法：
    pip install websockets
    python mock_ws.py            # 监听 ws://0.0.0.0:8765
    python mock_ws.py --port 9000 --host 127.0.0.1

前端把 ws 地址指过来即可；切真后端只需改地址。
合唱期不下发逐帧口型（与真后端一致），轨道通过 song.tracks 一次性下发（内联，免静态服务）。
"""
from __future__ import annotations
import argparse
import asyncio
import json
import os
import sys

try:
    import websockets
except ImportError:
    sys.exit("缺少依赖：pip install websockets")

# ---------- 样例数据（与 data/samples/*.json 同构；内联以做到自包含）----------
SONGS = [
    {"id": "daoxiang", "title": "稻香", "artist": "周杰伦", "duration": 90.0,
     "duet": True, "cover": "/assets/songs/daoxiang/cover.jpg"}
]

SONG_MANIFEST = {
    "id": "daoxiang", "title": "稻香", "duration": 90.0,
    "parts": {"high": {"speaker": "Angela"}, "low": {"speaker": "Neo"}},
    "audio": {"mix": "/assets/songs/daoxiang/mix.wav"},   # mock 模式可不存在
    "tracks": {"lyrics": "lyrics", "visemes": "visemes", "actions": "actions"},
    "dialogue": {
        "intro":    "今天，你想唱什么歌呢？",
        "selected": ["就让我们一起来唱《稻香》吧！", "记得跟着我的高声部哦。"],
        "finale":   ["今天唱得真不错呢，下次我们再一起练好不好？"],
    },
}

LYRICS = {
    "song": "daoxiang", "fps": 30,
    "lines": [
        {"t": 2.0,  "d": 4.2, "part": "duet", "speaker": "Angela+Neo", "text": "对这个世界如果你有太多的抱怨"},
        {"t": 6.4,  "d": 3.8, "part": "duet", "speaker": "Angela+Neo", "text": "跌倒了就不敢继续往前走"},
        {"t": 10.4, "d": 4.0, "part": "high", "speaker": "Angela",     "text": "为什么人要这么的脆弱 堕落"},
        {"t": 14.6, "d": 3.6, "part": "low",  "speaker": "Neo",        "text": "请你打开电视看看"},
        {"t": 18.4, "d": 4.4, "part": "high", "speaker": "Angela",     "text": "多少人为生命在努力勇敢的走下去"},
        {"t": 26.4, "d": 4.0, "part": "duet", "speaker": "Angela+Neo", "text": "珍惜一切 就算没有拥有"},
    ],
}

VISEMES = {
    "song": "daoxiang", "fps": 30, "params": ["ParamMouthOpenY"], "start": 0.0,
    # 用一段循环幅度模拟"唱歌张嘴"；前端按 t 在 frames 插值
    "frames": [[round(0.5 + 0.4 * (((i * 7) % 30) / 30 - 0.5) * 2, 3)] for i in range(30)],
}

ACTIONS = {
    "song": "daoxiang",
    "timeline": [
        {"t": 0.0,  "action": "idle",         "loop": True},
        {"t": 1.8,  "action": "singing_high", "loop": True},
        {"t": 25.0, "action": "sway",         "loop": True},
        {"t": 88.0, "action": "bow",          "loop": False, "blend": 0.4, "dur": 4.0, "then": "idle"},
    ],
}


# ---------- 信封 ----------
class Bus:
    """每连接一个 seq 计数 + 发送封装。"""
    def __init__(self, ws):
        self.ws = ws
        self.seq = 0

    async def send(self, type_: str, data: dict | None = None, ts: float = 0.0):
        self.seq += 1
        env = {"type": type_, "seq": self.seq, "ts": round(ts, 3), "data": data or {}}
        await self.ws.send(json.dumps(env, ensure_ascii=False))
        print(f"  → {type_:14} seq={self.seq} ts={env['ts']}")


# ---------- 假 TTS + 实时口型（模拟 docs/02 对白期实时推流）----------
async def fake_tts(bus: Bus, lines: list[str], voice="angela"):
    for i, text in enumerate(lines):
        tts_seq = i + 1
        await bus.send("subtitle", {"speaker": "Angela", "text": text})
        await bus.send("action.set", {"name": "talk", "loop": True})
        await bus.send("tts.start", {"seq": tts_seq, "voice": voice})
        # 按文字长度估计时长，30fps 推假口型帧
        dur = max(1.2, len(text) * 0.18)
        steps = int(dur * 30)
        import math
        for k in range(steps):
            t = k / 30.0
            # 用正弦模拟说话起伏
            v = round(0.5 + 0.45 * math.sin(t * 14), 3)
            await bus.send("viseme.frame",
                           {"t": round(t, 3), "params": {"ParamMouthOpenY": max(0.0, v)}},
                           ts=t)
            await asyncio.sleep(1 / 30)
        await bus.send("tts.end", {"seq": tts_seq})
    await bus.send("action.set", {"name": "idle", "loop": True})


# ---------- 合唱期心跳 ----------
async def tick_loop(bus: Bus, duration: float, stop_evt: asyncio.Event):
    t = 0.0
    while not stop_evt.is_set() and t < duration:
        await bus.send("song.tick", {"t": round(t, 3)}, ts=t)
        await asyncio.sleep(0.1)   # 10Hz
        t += 0.1


# ---------- 主连接处理 ----------
async def handler(ws):
    peer = ws.remote_address
    bus = Bus(ws)
    stop_evt = asyncio.Event()
    print(f"[connect] {peer}")
    try:
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await bus.send("error", {"code": "WS_PROTOCOL", "message": "bad json"})
                continue
            mtype = msg.get("type")
            data = msg.get("data", {}) or {}
            print(f"[recv] {mtype} {data}")

            if mtype == "hello":
                await bus.send("hello", {"role": "backend", "proto": "0.1",
                                         "songs": [s["id"] for s in SONGS]})

            elif mtype == "song.select":
                sid = data.get("id", "daoxiang")
                await bus.send("phase.change", {"phase": "select"})
                await bus.send("song.loaded", {"id": sid, **SONG_MANIFEST})
                # 选歌开场对白
                await fake_tts(bus, [SONG_MANIFEST["dialogue"]["intro"]])
                await fake_tts(bus, SONG_MANIFEST["dialogue"]["selected"])

            elif mtype == "song.start":
                stop_evt.clear()
                duration = SONG_MANIFEST["duration"]
                # 一次性下发三条轨道（内联，前端无需静态服务）
                await bus.send("song.tracks",
                               {"lyrics": LYRICS, "visemes": VISEMES, "actions": ACTIONS})
                await bus.send("phase.change", {"phase": "singing"})
                await bus.send("action.set", {"name": "singing_high", "loop": True})
                await bus.send("song.start",
                               {"id": "daoxiang",
                                "mixUrl": "/assets/songs/daoxiang/mix.wav", "t0": 0})
                asyncio.create_task(tick_loop(bus, duration, stop_evt))
                # 到点结束
                await asyncio.sleep(duration)
                stop_evt.set()
                await bus.send("song.end", {"id": "daoxiang"})
                await bus.send("phase.change", {"phase": "finale"})
                await fake_tts(bus, SONG_MANIFEST["dialogue"]["finale"])

            elif mtype == "song.stop":
                stop_evt.set()
                await bus.send("song.end", {"id": data.get("id", "daoxiang")})
                await bus.send("phase.change", {"phase": "select"})

            elif mtype == "finale.start":
                await bus.send("phase.change", {"phase": "finale"})
                await fake_tts(bus, SONG_MANIFEST["dialogue"]["finale"])

            elif mtype == "tts.request":
                await fake_tts(bus, [data.get("text", "")])

            else:
                await bus.send("error", {"code": "WS_PROTOCOL",
                                         "message": f"unknown type {mtype}"})
    except websockets.ConnectionClosed:
        pass
    finally:
        stop_evt.set()
        print(f"[disconnect] {peer}")


async def main(host: str, port: int):
    async with websockets.serve(handler, host, port):
        print(f"Angela mock WS ready: ws://{host}:{port}")
        print("流程：hello → song.select → (对白) → song.start → (合唱心跳) → song.end → (收尾)")
        print("Ctrl+C 退出")
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8765)
    a = ap.parse_args()
    try:
        asyncio.run(main(a.host, a.port))
    except KeyboardInterrupt:
        print("\nbye")
