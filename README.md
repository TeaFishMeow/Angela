# Angela · 沉浸式 KTV 数字人（合唱模式 MVP）

> 一个把虚拟少女 **Angela** 接进 KTV 的项目。本仓库是 **3 小时敏捷冲刺** 的第一个可演示版本：
> **只做「合唱模式」** —— 背景播 MV、左右分声部显示歌词、右侧数字人带动作与口型，按
> **选歌对话 → 合唱 → 收尾** 三幕推进。

人物：**Neo**（年轻男性，真人/用户侧）× **Angela**（虚拟少女，数字人）。
合唱约定：**Angela 唱高声部（high），Neo 唱低声部（low）**。

---

## 1. 演示流程（三幕）

| 阶段 | phase | 谁在动 | 内容 |
|------|-------|--------|------|
| ① 选歌 | `select` | Angela 说话（TTS）+ 口型 | Angela 问"今天想唱什么"，用户选歌，Angela 确认 |
| ② 合唱 | `singing` | MV + 双声部歌词 + Angela 口型/动作 | 背景播 MV，左右两栏歌词随时间高亮，Angela 跟着高声部对口型 |
| ③ 收尾 | `finale` | Angela 说话（TTS）+ 口型 | 唱完 Angela 主动开口点评/告别 |

## 2. 技术栈（已定）

| 层 | 选型 | 说明 |
|----|------|------|
| 舞台/前端 | **Web（HTML/CSS/JS）** | `video` 播 MV + overlay 歌词 + canvas 接数字人 |
| 数字人 | **Live2D Cubism（pixi-live2d-display）** | viseme 驱动 `ParamMouthOpenY`，motion 驱动动作 |
| 通信 | **WebSocket 实时推流** | 控制信令 + TTS/口型帧；合唱期前端以音频时钟为渲染权威 |
| 后端 | **Python（FastAPI + websockets）** | 分轨/RVC/混音/口型/动作/TTS 全在 Python 生态 |
| 变声 | **Applio / RVC** | 把高声部人声转成 Angela 音色 |
| TTS | **edge-tts（+ 可选 RVC 上色）** | 选歌/收尾对白；可叠加 RVC 让声音更像 Angela |
| 演示曲目 | **稻香（周杰伦）** | 用户负责切分轨、人工编排高/低声部 |

## 3. 三人分工

| 角色 | 负责 | 必读文档 |
|------|------|----------|
| **队友 A** | 把数字人接进来（Live2D 模块：模型加载、口型/动作驱动、右侧渲染） | `02` `03` `05` `08` |
| **队友 B** | 后端：分轨/RVC 变声/混音/播放、生成口型与动作、WS 推流、TTS | `02` `03` `04` `08` |
| **你（架构/整合）** | 背景 MV、整体架构、整合 A/B 代码、稻香分轨 | 全部，重点是 `00` `01` `02` `06` `07` `08` |

> **核心原则：契约先冻结、各自对着 mock 开发、按 drop-in 顺序整合。** 详见 `docs/01`、`docs/08`。

## 4. 仓库结构

```
Angela/
├─ README.md                      本文件（导航枢纽）
├─ MVP 文档.md                    原始需求（保留）
├─ 视频概念文档.md                概念宣传片设定（保留）
├─ .gitignore                     排除大体积音视频/模型/venv
├─ docs/                          ← 开发文档（这次交付的核心）
│  ├─ 00-架构总览.md             模块地图 / 数据流 / 文件结构 / 技术决策
│  ├─ 01-三小时开发计划.md       时间线 + 同步检查点 + mock-first
│  ├─ 02-接口契约.md             ★ WS 消息 / REST / 主时钟驱动模型
│  ├─ 03-数据格式规范.md         song.json / lyrics / visemes / actions / TTS
│  ├─ 04-后端音频管线（队友B）.md 分轨→RVC→混音→口型→WS
│  ├─ 05-数字人接入（队友A）.md   Live2D 模块 API / 口型与动作驱动
│  ├─ 06-舞台前端（架构整合）.md  MV / 歌词双栏 / 编排状态机 / 主时钟
│  ├─ 07-演示曲目分轨（稻香）.md  Demucs 切分 / 高低声部编排 / RVC 目标
│  └─ 08-集成与联调.md           drop-in 顺序 / mock 数据 / 常见坑
├─ data/samples/                  可直接跑的样例数据（合同真值）
│  ├─ song.daoxiang.json
│  ├─ lyrics.daoxiang.json
│  ├─ visemes.sample.json
│  └─ actions.sample.json
├─ packages/                      代码区（按文档搭建，先建空目录+占位）
│  ├─ stage/                      你：前端舞台
│  ├─ backend/                    队友 B：FastAPI + WS
│  └─ character/                  队友 A：Live2D 模块
└─ assets/                        大文件（.gitignore 排除）：MV、stems、模型
   └─ songs/daoxiang/
```

> `assets/` 与任何 `*.wav *.mp4 *.model3.json` 等大文件**不入 git**，靠各自本地/网盘同步。

## 5. 快速开始（30 秒）

```bash
# 1) 后端（队友 B 区，含 mock 模式，可独立联调前端）
cd packages/backend
python -m venv .venv && .venv\Scripts\activate
pip install fastapi "uvicorn[standard]" websockets pydub librosa soundfile edge-tts
python mock/mock_ws.py            # 纯 mock，先让前端/数字人跑通三幕

# 2) 前端（你）
cd packages/stage
python -m http.server 5173        # 或 npx serve .
# 浏览器打开 http://localhost:5173

# 3) 数字人（队友 A）：把 Live2D 模型放进 packages/character/models/
```

## 6. 状态

- [x] 文档与接口契约（本次提交）
- [ ] 稻香分轨 + 高/低声部编排（你）
- [ ] 后端 WS + TTS + mock 数据（队友 B）
- [ ] Live2D 数字人模块（队友 A）
- [ ] 舞台前端三幕 + 主时钟（你）
- [ ] 端到端联调（全员）

仓库：https://github.com/TeaFishMeow/Angela
