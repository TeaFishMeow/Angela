# packages/stage — 舞台前端

合唱模式路演版舞台。原生 ES Modules，无构建步骤。
**先连 mock_ws 就能跑通两场**（队友 A 的真 Live2D 没好→内置 mock 数字人；队友 B 的 backing.wav 没好→主时钟自动回退 WS tick 推进歌词/口型）。

## 跑起来

```bash
# 终端1：mock WS（让两场可走通）
cd ../backend/mock && pip install websockets && python mock_ws.py

# 终端2：静态托管舞台（必须 http，不能用 file://）
cd packages/stage && python -m http.server 5173

# 浏览器：http://localhost:5173/
```
点 **▶ 开始场1（传奇）**：Angela 出场 → intro 对口型 → 合唱（歌词随 tick 滚、嘴随幅度动）→ 收尾。
点 **下一场**：切 Neo → 因为爱情。

> mock 模式没有真 backing.wav，`<audio>` 会 404，**主时钟自动回退到 `scene.tick`**，歌词/口型照常推进。
> 没有 Live2D 模块时，右侧画 **mock 占位脸**（嘴随口型张合、Angela 粉/Neo 蓝），验证走线。

## 连真后端 / 真数字人

- 真后端：`http://localhost:5173/?ws=ws://localhost:8000/ws`
- 真 Live2D：队友 A 把 `packages/character/character.js`（导出 `CharacterStage`）+ 模型放好，舞台自动加载（`character-client.js` 动态 import，失败回退 mock）。
- 真伴奏带：后端 `/assets` 托管 `演示用例/*_分轨/*_backing.wav`，舞台 `<audio>` 播它 → 主时钟切回音频时钟（零漂移）。

## 文件

| 文件 | 职责 |
|------|------|
| `index.html` | 布局：MV / 双栏歌词 / 右侧 canvas / 字幕 / 控制 |
| `css/style.css` | 样式（透明叠层、双栏着色） |
| `js/config.js` | WS 地址、场景顺序、URL 参数覆盖 |
| `js/ws-client.js` | 信封 + 事件总线 + 重连 |
| `js/character-client.js` | 真 Live2D / mock 兜底，统一 API |
| `js/lyrics.js` | 双声部歌词高亮（digital / teammateC / duet） |
| `js/clock.js` | 主时钟（音频→tick→虚拟）+ 口型/动作查表 |
| `js/orchestrator.js` | 两场状态机 + 主循环 + 离线兜底 |

## 三时钟模型（clock.js）

1. **音频时钟**（首选）：`<audio>.currentTime`，嘴音零漂。
2. **tick 回退**：音频不可用时用 `scene.tick` 的时间。
3. **虚拟时钟**（离线）：无 WS 时用真实经过时间。

见 `docs/02 §5`、`docs/06 §4`。

## 离线模式

WS 连不上时点"开始"→ 自动吃 `data/samples/` + 虚拟时钟跑两场（无声音、无真 MV），验证编排走线。真后端/真素材就位后自然切回。
