"""
Angela 合唱模式 — Mock WebSocket 服务（路演版 · 联调用）
=========================================================
纯 Python、仅依赖 `websockets`。让舞台前端与数字人模块不必等真后端即可跑通两场。
信封/字段与真后端完全一致（见 docs/02-接口契约.md，proto v0.2）。

两场：
  场1 传奇    chuanqi       数字人 Angela(女) + 队友C 齐唱
  场2 因为爱情 yinwei-aiqing  数字人 Neo(男)   + 队友C 对唱(女声部现场)

用法：
    pip install websockets
    python mock_ws.py                     # ws://0.0.0.0:8765
    python mock_ws.py --port 9000

前端发 scene.load → 自动走 intro 对白 → scene.start(合唱心跳) → scene.end → outro。
合唱期不下发逐帧口型（与真后端一致），轨道通过 scene.tracks 内联下发。
"""
from __future__ import annotations
import argparse
import asyncio
import json
import math
import sys

try:
    import websockets
except ImportError:
    sys.exit("缺少依赖：pip install websockets")

# ---------- 两场样例数据（与 data/samples/*.json 同构；内联以自包含）----------
SCENES = {
    "chuanqi": {
        "id": "chuanqi", "title": "传奇", "character": "angela", "relation": "unison",
        "duration": 90.0,
        "character_model": "models/angela/angela.model3.json",
        "backing": "/assets/演示用例/传奇_分轨/传奇_backing.wav",
        "dialogue": {
            "intro": ["这首《传奇》，我们一起唱吧。"],
            "outro": ["唱得真好，下一首换个人选？"],
        },
        "sing_action": "singing_high",   # Angela
    },
    "yinwei-aiqing": {
        "id": "yinwei-aiqing", "title": "因为爱情", "character": "neo", "relation": "duet",
        "duration": 90.0,
        "character_model": "models/neo/neo.model3.json",
        "backing": "/assets/演示用例/因为爱情_分轨/因为爱情_backing.wav",
        "dialogue": {
            "intro": ["因为爱情，不会轻易悲伤。我们一起，好吗？"],
            "outro": ["唱得真好，这就是爱情的样子吧。"],
        },
        "sing_action": "singing_low",    # Neo
    },
}

# 内联轨道（自包含；真实数据见 data/samples 与 演示用例/*_分轨/）
def _lyrics(scene_id):
    if scene_id == "chuanqi":  # 齐唱：duet 两栏同显
        return {"scene": "chuanqi", "fps": 30, "lines": [
            {"t": 2.0, "d": 4.2, "part": "duet", "performer": "Angela+队友C", "text": "只是因为在人群中多看了你一眼"},
            {"t": 6.4, "d": 4.0, "part": "duet", "performer": "Angela+队友C", "text": "再也没能忘掉你容颜"},
            {"t": 10.6,"d": 4.2, "part": "duet", "performer": "Angela+队友C", "text": "梦想着偶然能有一天再相见"},
        ]}
    # 因为爱情：男女对唱
    return {"scene": "yinwei-aiqing", "fps": 30, "lines": [
        {"t": 2.0, "d": 4.0, "part": "digital",   "performer": "Neo",       "text": "给你一张过去的CD"},
        {"t": 6.2, "d": 4.0, "part": "teammateC", "performer": "队友C",     "text": "听听那时我们的爱情"},
        {"t": 10.4,"d": 3.8, "part": "digital",   "performer": "Neo",       "text": "有时会突然忘了"},
        {"t": 14.4,"d": 4.2, "part": "teammateC", "performer": "队友C",     "text": "我还在爱着你"},
        {"t": 20.0,"d": 4.6, "part": "duet",      "performer": "Neo+队友C", "text": "因为爱情 不会轻易悲伤"},
    ]}

VISEMES = {  # 循环幅度，模拟唱歌张嘴；前端按 t 插值
    "fps": 30, "params": ["ParamMouthOpenY"], "start": 0.0,
    "frames": [[round(0.5 + 0.4 * (((i * 7) % 30) / 30 - 0.5) * 2, 3)] for i in range(30)],
}
ACTIONS = {  # 通用；真实按场区分 singing_high/singing_low
    "timeline": [
        {"t": 0.0,  "action": "idle",         "loop": True},
        {"t": 1.8,  "action": "singing_high", "loop": True},
        {"t": 25.0, "action": "sway",         "loop": True},
        {"t": 88.0, "action": "bow",          "loop": False, "blend": 0.4, "dur": 4.0, "then": "idle"},
    ]
}


# ---------- 信封 ----------
class Bus:
    def __init__(self, ws):
        self.ws = ws
        self.seq = 0

    async def send(self, type_: str, data: dict | None = None, ts: float = 0.0):
        self.seq += 1
        env = {"type": type_, "seq": self.seq, "ts": round(ts, 3), "data": data or {}}
        await self.ws.send(json.dumps(env, ensure_ascii=False))
        print(f"  → {type_:14} seq={self.seq} ts={env['ts']}")


# ---------- 假 TTS + 实时口型（对白期实时推流）----------
async def fake_tts(bus: Bus, lines: list[str], voice="angela"):
    for i, text in enumerate(lines):
        tts_seq = i + 1
        await bus.send("subtitle", {"speaker": "Angela" if voice == "angela" else "Neo", "text": text})
        await bus.send("action.set", {"name": "talk", "loop": True})
        await bus.send("tts.start", {"seq": tts_seq, "voice": voice})
        dur = max(1.2, len(text) * 0.18)
        for k in range(int(dur * 30)):
            t = k / 30.0
            v = round(0.5 + 0.45 * math.sin(t * 14), 3)
            await bus.send("viseme.frame",
                           {"t": round(t, 3), "params": {"ParamMouthOpenY": max(0.0, v)}}, ts=t)
            await asyncio.sleep(1 / 30)
        await bus.send("tts.end", {"seq": tts_seq})
    await bus.send("action.set", {"name": "idle", "loop": True})


# ---------- 合唱期心跳 ----------
async def tick_loop(bus: Bus, duration: float, stop_evt: asyncio.Event):
    t = 0.0
    while not stop_evt.is_set() and t < duration:
        await bus.send("scene.tick", {"t": round(t, 3)}, ts=t)
        await asyncio.sleep(0.1)
        t += 0.1


# ---------- 走一场 ----------
async def run_scene(bus: Bus, sid: str, stop_evt: asyncio.Event):
    s = SCENES[sid]
    voice = s["character"]  # angela / neo
    await bus.send("scene.loaded", {"id": sid, "title": s["title"],
                                    "character": s["character"], "manifest": s})
    await bus.send("character.set", {"name": s["character"], "model": s["character_model"]})
    await fake_tts(bus, s["dialogue"]["intro"], voice)          # intro 对白

    stop_evt.clear()
    await bus.send("scene.tracks", {"lyrics": _lyrics(sid), "visemes": VISEMES, "actions": ACTIONS})
    await bus.send("phase.change", {"phase": "singing"})
    await bus.send("action.set", {"name": s["sing_action"], "loop": True})
    await bus.send("scene.start", {"id": sid, "backingUrl": s["backing"], "t0": 0})
    asyncio.create_task(tick_loop(bus, s["duration"], stop_evt))
    await asyncio.sleep(s["duration"])
    stop_evt.set()
    await bus.send("scene.end", {"id": sid})
    await fake_tts(bus, s["dialogue"]["outro"], voice)          # outro 对白


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
                await bus.send("hello", {"role": "backend", "proto": "0.2"})
                await bus.send("scene.list", {"scenes": [
                    {"id": k, "title": v["title"], "character": v["character"],
                     "relation": v["relation"], "duration": v["duration"]} for k, v in SCENES.items()]})

            elif mtype == "scene.load":
                sid = data.get("id", "chuanqi")
                if sid not in SCENES:
                    await bus.send("error", {"code": "SCENE_NOT_FOUND", "message": sid})
                    continue
                await run_scene(bus, sid, stop_evt)

            elif mtype == "next.scene":
                # 简单串行：传奇 → 因为爱情
                nxt = "yinwei-aiqing" if data.get("id", "chuanqi") == "chuanqi" else "chuanqi"
                await run_scene(bus, nxt, stop_evt)

            elif mtype == "scene.stop":
                stop_evt.set()
                await bus.send("scene.end", {"id": data.get("id", "")})

            elif mtype == "outro.start":
                s = SCENES.get(data.get("id", "chuanqi"))
                if s:
                    await fake_tts(bus, s["dialogue"]["outro"], s["character"])

            elif mtype == "tts.request":
                await fake_tts(bus, [data.get("text", "")])

            else:
                await bus.send("error", {"code": "WS_PROTOCOL", "message": f"unknown type {mtype}"})
    except websockets.ConnectionClosed:
        pass
    finally:
        stop_evt.set()
        print(f"[disconnect] {peer}")


async def main(host: str, port: int):
    async with websockets.serve(handler, host, port):
        print(f"Angela mock WS (路演版) ready: ws://{host}:{port}")
        print("两场：chuanqi(传奇/Angela) → yinwei-aiqing(因为爱情/Neo)")
        print("流程：hello → scene.load{id} → (intro) → scene.start(合唱) → scene.end → (outro)")
        print("     next.scene → 自动串到下一场；Ctrl+C 退出")
        await asyncio.Future()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8765)
    a = ap.parse_args()
    try:
        asyncio.run(main(a.host, a.port))
    except KeyboardInterrupt:
        print("\nbye")
