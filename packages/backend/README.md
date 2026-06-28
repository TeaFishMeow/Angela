# Angela Backend（路演版 · proto v0.2）

队友 B 的后端音频管线与运行时服务。以 **scene（场）** 为单位，对接路演两场：
**传奇（Angela 齐唱）** + **因为爱情（Neo 对唱）**。契约见 `docs/02`，数据见 `docs/03`，管线见 `docs/04`。

## Run

```bash
cd packages/backend
python -m venv .venv && .venv\Scripts\activate        # Windows；unix 用 source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

> 需要 **ffmpeg**（mix.py 预混用）。RVC 推理还需 `rvc` CLI（见 `docs/09`）。

## 接口

| 通道 | 地址 | 用途 |
|------|------|------|
| REST | `GET /api/scenes` | 两场清单 |
| REST | `GET /api/scenes/{id}` | 单场 manifest（id: `chuanqi` / `yinwei-aiqing`） |
| REST | `GET /api/scenes/{id}/tracks/{track}` | 轨道（lyrics/visemes/actions） |
| REST | `GET /demo-assets/{path}` | `演示用例/` 静态资源（分轨 wav、MV、lyrics.json） |
| REST | `GET /assets/{path}` | `assets/` 兼容静态资源 |
| REST | `POST /api/tts` | `{text, voice}` → 静音 wav（兜底） |
| WS | `ws://host/ws` | proto v0.2：控制/事件/TTS/口型帧 |

## 数据来源（自动兜底）

`scenes.py` 按优先级取数：

1. **真值**：`演示用例/<曲>_分轨/scene.json` 及同目录轨道文件（路演前放入）
2. **样例**：`data/samples/scene.<id>.json` + `data/samples/{lyrics,visemes,actions}.<id>.json`

当前 `data/samples/` 已含两场 manifest + **真实烘焙的 visemes**（RMS@30fps，由源人声烘焙）+
占位歌词/动作时间轴。`backing.wav` 未烘焙时，`scene.start` 的 `backingUrl` 自动回退到
`*_instrumental.wav`（纯伴奏、无数字人声）—— 待 RVC 烤声后放 `演示用例/<曲>_分轨/<曲>_backing.wav`
即自动启用真值。

## WS 协议（proto v0.2，摘自 docs/02）

```
hello           → hello{proto:"0.2"} + scene.list
scene.load{id}  → scene.loaded + character.set + intro TTS
scene.start{id} → scene.tracks + action.set(singing_high|singing_low) + scene.start{backingUrl} + scene.tick(~10Hz) → scene.end
scene.stop      → scene.end
outro.start{id} → outro TTS
next.scene      → 切另一场（= scene.load）
scene.jump_outro→ scene.end + phase{outro} + outro TTS
tts.request     → tts.*
```

> 合唱期走 `scene.tracks` 预烘焙轨道（前端音频时钟驱动）；仅 intro/outro 实时推 `tts.*` + `viseme.frame`。
> 行为与 `mock/mock_ws.py` 对齐，前端切 ws 地址即可在 mock/真后端间切换。

## 离线工具

```bash
# ① RVC 变声：传奇人声→Angela（模型见 docs/09，如 RVC/Azusa 阿梓女声）
python rvc.py "演示用例/传奇_分轨/传奇_vocals.wav" \
  "演示用例/传奇_分轨/传奇_vocals_angela_rvc.wav" \
  --model voice/models/angela_female.pth --index voice/models/angela_female.index

# ② 预混伴奏带：伴奏 + 数字人声（队友C 唱的不进带）
python mix.py "演示用例/传奇_分轨/传奇_instrumental.wav" \
  "演示用例/传奇_分轨/传奇_vocals_angela_rvc.wav" \
  "演示用例/传奇_分轨/传奇_backing.wav"

# ③ 烘焙口型（对 vocal_rvc；当前 visemes 是用源人声烘焙的近似）
python bake.py "演示用例/传奇_分轨/传奇_vocals_angela_rvc.wav" \
  "演示用例/传奇_分轨/visemes.json" --scene chuanqi
```

因为爱情（Neo 男声部）同理：源 `因为爱情 男声_vocals.wav` → RVC（neo 模型）→ 预混 backing → 烘焙。
