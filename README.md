# Angela · 沉浸式 KTV 数字人（合唱模式 · 路演版）

> 把虚拟数字人接进 KTV 的项目。本仓库是**路演版**：**两场合唱**，
> 数字人 + 真人队友C 同台，背景播 MV、分声部歌词、数字人带动作与口型。

## 1. 路演两场（核心范围）

| 场 | 曲目 | 数字人 | 真人 | 声部关系 |
|----|------|--------|------|----------|
| **场 1** | **传奇** | **Angela（女数字人）** | 队友C | **相同声部 / 齐唱 unison**：两人唱同一条旋律 |
| **场 2** | **因为爱情** | **Neo（男数字人）** | 队友C | **多声部对唱**：Neo 唱男声部（陈奕迅），队友C 现场唱女声部（王菲） |

每场流程：**开场对话(TTS) → 播伴奏带+MV、数字人对口型、队友C现场真唱 → 收尾对话(TTS)**。

> **关键设计**：数字人声**离线烤好**（RVC）预混进"伴奏带"现场播放；**队友C拿麦克风现场真唱**叠上去，
> 数字人对口型用预烘焙的 visemes。→ **不做实时变声**（避开延迟/翻车），声音可反复打磨。

## 2. 技术栈（已定）

| 层 | 选型 | 说明 |
|----|------|------|
| 舞台/前端 | **Web（HTML/CSS/JS）** | `video` 播 MV + overlay 歌词 + canvas 接数字人 |
| 数字人 | **Live2D Cubism（pixi-live2d-display）** | 两个模型：Angela(女)、Neo(男)，按场切换 |
| 通信 | **WebSocket** | 控制信令 + TTS/口型帧；合唱期前端以音频时钟为渲染权威 |
| 后端 | **Python（FastAPI + websockets）** | 烘焙伴奏带、WS 推流、TTS |
| **声音烤制** | **RVC（Applio）离线推理** | 用社区现成高质量角色模型；**不自训** |
| 算力 | **RTX 5070 Ti Laptop 12G** | 跑 RVC **推理**足够（不训练） |
| TTS | **edge-tts（+ 可选 RVC 上色）** | 开场/收尾对白 |
| 现场 | **调音台 + 麦克风（队友C）** | 队友C 真唱走 PA，数字人系统不必处理 |

## 3. 三人（+队友C）分工

| 角色 | 负责 | 必读 |
|------|------|------|
| **队友 A** | 两个数字人接进来（Angela/Neo Live2D 模型、口型/动作驱动、右侧渲染、场间切换） | `02` `03` `05` `08` |
| **队友 B** | 后端：分轨/RVC 烤声/预混伴奏带、烘焙口型与动作、WS 推流、TTS | `02` `03` `04` `09` `08` |
| **你（架构/整合）** | 架构、MV、舞台前端、整合 A/B、两曲分轨与歌词 | 全部，重点 `00` `02` `06` `07` `09` |
| **队友C** | 现场真唱（传奇齐唱 / 因为爱情女声部） | `演示用例/路演runbook.md` |

> **核心原则**：契约先冻结、对着 mock 并行开发、按 drop-in 顺序整合。见 `01`、`08`。

## 4. 仓库结构

```
Angela/
├─ README.md                       本文件
├─ MVP 文档.md / 视频概念文档.md    原始需求与设定（保留）
├─ .gitignore                      排除大体积音视频/模型/venv
├─ docs/                           ← 开发文档
│  ├─ 00-架构总览.md
│  ├─ 01-路演准备计划.md
│  ├─ 02-接口契约.md               ★ WS/REST/主时钟
│  ├─ 03-数据格式规范.md           scene.json/character/lyrics/visemes/actions
│  ├─ 04-后端音频管线（队友B）.md
│  ├─ 05-数字人接入（队友A）.md     两个模型 + 场间切换
│  ├─ 06-舞台前端（架构整合）.md
│  ├─ 07-演示曲目准备（传奇+因为爱情）.md
│  ├─ 08-集成与联调.md
│  └─ 09-声音烤制（RVC）.md        ★ 社区模型选型 / 5070Ti推理 / 合规 / 兜底
├─ 演示用例/                        ★ 路演素材（大文件 .gitignore 排除，本地保留）
│  ├─ 传奇 MV.mp4                  ✅已有
│  ├─ 传奇_分轨/                   ⬜待 Demucs
│  ├─ 因为爱情.mp4 / 因为爱情 只含男声.mp4   ✅已有
│  ├─ 因为爱情_分轨/               ✅已有（男声+伴奏已分）
│  │  ├─ 因为爱情 男声_vocals.wav       = Neo 男声部源人声
│  │  └─ 因为爱情 男声_instrumental.wav = 伴奏
│  ├─ 场1-传奇-分镜.md             两场分镜脚本（你/队友C/MC 用）
│  ├─ 场2-因为爱情-分镜.md
│  └─ 路演runbook.md               现场流程 + 兜底
├─ data/samples/                   可运行样例（合同真值）
├─ packages/                       代码区
│  ├─ stage/                       你：前端舞台
│  ├─ backend/                     队友 B：FastAPI + WS + 烤声脚本
│  ├─ character/                   队友 A：两个 Live2D 模型
│  └─ voice/                       RVC 烤声工作区（模型/产物，.gitignore 排除）
└─ assets/                         （兼容旧约定，大文件不入库）
```

## 5. 快速开始

```bash
# 后端（队友 B，含 mock，可独立联调前端）
cd packages/backend
python -m venv .venv && .venv\Scripts\activate
pip install fastapi "uvicorn[standard]" websockets pydub librosa soundfile edge-tts
python mock/mock_ws.py            # mock 三幕，前端/数字人先跑通

# 烤声（队友 B，离线，需要 5070Ti）
cd packages/voice
# 见 docs/09-声音烤制（RVC）.md：用社区模型把男声→Neo、传奇人声→Angela

# 前端（你）
cd packages/stage
python -m http.server 5173        # 浏览器开 http://localhost:5173

# 数字人（队友 A）：两个模型放 packages/character/models/{angela,neo}/
```

## 6. 状态

- [x] 文档与接口契约（v2：两曲/两数字人/队友C现场/RVC离线烤声）
- [ ] 因为爱情：男声 RVC→Neo、预混伴奏带、烘焙口型（队友 B）
- [ ] 传奇：分轨、人声 RVC→Angela、预混伴奏带、烘焙口型（你 + B）
- [ ] 两个 Live2D 模型 + 场间切换（队友 A）
- [ ] 舞台：两场切换、双声部歌词、主时钟（你）
- [ ] 现场麦调试（队友C + 调音）
- [ ] 路演联排（全员）

仓库：https://github.com/TeaFishMeow/Angela
