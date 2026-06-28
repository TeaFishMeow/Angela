# packages/character · 数字人前端组件（队友 A）

把两个 Live2D 数字人（Angela 女 / Neo 男）接进舞台：加载、按场切换、口型/动作驱动、右侧透明叠层渲染。
接口契约见 [`docs/05-数字人接入（队友A）.md`](../../docs/05-数字人接入（队友A）.md)；舞台消费见 `docs/06 §6`。

## 依赖

- **pixi.js@7 + pixi-live2d-display@0.5.0-beta**（⚠️ `0.4` 与 pixi@7 不兼容，见 docs/05 §1）
- 无构建工具，UMD 三 `<script>` 加载（顺序固定）：
  - `live2dcubismcore.min.js` → `window.Live2DCubismCore`
  - `pixi.min.js` → `window.PIXI`
  - `cubism4.min.js` → `window.PIXI.live2d`
- ⚠️ pixi@7 的 UMD 引用 `process.env`，加载前必须先 polyfill，否则 `ReferenceError: process is not defined`：
  ```html
  <script>window.process = window.process || { env: {} };</script>
  ```
  （demo.html 已加。漏掉这一行 = 整个 demo 白屏挂掉。）

## 快速开始

demo 默认用 Live2D 官方 `CubismWebSamples` 占位模型（Hiyori=Angela、Mark=Neo，jsdelivr CDN），
不需自备模型即可跑通 API。

```bash
# 在【仓库根】起服务（demo 需跨目录读 data/samples/visemes.sample.json，root 必须是仓库根）
python -m http.server 5173
# 浏览器开 http://localhost:5173/packages/character/demo.html
```

## demo 自检（对照 docs/05 §8）

- [x] 两模型加载、右侧透明叠在背景上、不挡画面
- [x] 切 Angela↔Neo 淡入淡出顺滑、无白屏；DevTools fps ≥ 55
- [x] 滑块调 `ParamMouthOpenY` → 嘴随幅度开合；滑到 0 → 闭嘴
- [x] 点全部动作按钮都不报错；非 idle 的（占位模型只有 Idle）silent fallback
- [x] 「播放 visemes.sample.json」→ 嘴随 frames 幅度起伏、静音闭嘴

> 上述项已用 headless Edge 自动化验证通过（加载 / 口型写入 coreModel / 切换 / fallback / 无控制台错误）。

## 换成真模型

1. 把 Angela/Neo 真模型放进 `models/angela/`、`models/neo/`（各含 `.model3.json` / `.moc3` / 贴图 / 动作）。
2. 改 `demo.html` 顶部 `MODELS`：
   ```js
   const MODELS = {
     angela: "models/angela/angela.model3.json",
     neo:    "models/neo/neo.model3.json",
   };
   ```
3. 真模型须在 `model3.json` 的 `FileReferences.Motions` 建**同名动作组**：
   `Idle, talk, singing_high(Angela) / singing_low(Neo), sway, wave, bow, point`
   （与 `actions.json` / `action.set` 的 `name` 一一对应，见 docs/03 §4、docs/05 §4）。
   - 口型：确保模型 LipSync 组含 `ParamMouthOpenY`。
   - 缺动作组时自动 fallback 到 Idle（不报错）。
   - 男 Live2D 模型少；Neo 若无合适男模，可继续用占位或转 PNG 立绘兜底（docs/08 §6/§7）。

## 路演前本地化（断网兜底）

CDN 在现场不可靠，路演前把三个 JS 下到 `lib/`，并把 `demo.html` 三个 `<script src=...>` 改为本地路径：

```bash
cd packages/character
mkdir lib
curl -L -o lib/live2dcubismcore.min.js https://cubism.live2d.com/sdk-web/cubismcore/live2dcubismcore.min.js
curl -L -o lib/pixi.min.js            https://cdn.jsdelivr.net/npm/pixi.js@7.4.0/dist/pixi.min.js
curl -L -o lib/cubism4.min.js         https://cdn.jsdelivr.net/npm/pixi-live2d-display@0.5.0-beta/dist/cubism4.min.js
```

真模型同样放本地 `models/`。

## CharacterStage API

```js
import { CharacterStage } from "./character.js";

const stage = await CharacterStage.mount(canvasEl);        // 透明 pixi 应用，返回实例
await stage.preload("angela", { model, gain });             // 预载（gain 按模型嘴大小校准）
await stage.switchTo("angela", { blend: 0.3 });             // 淡入淡出切换（默认 0.3s）
stage.setViseme({ ParamMouthOpenY, ParamMouthForm? });      // 口型（合唱主循环 / 对白 viseme.frame）
await stage.playMotion("singing_high", opts?);              // 动作（缺则 fallback Idle，绝不抛错）
stage.setExpression(name); stage.idle(); stage.destroy();
stage.current;                                             // 当前模型名
```

> 口型写入挂在**低优先级 ticker**（在模型 `autoUpdate` 之后执行），否则 `ParamMouthOpenY` 会被
> 模型 idle/motion 覆盖（pixi-live2d-display Issue #144）。

## 联调

`packages/backend/mock/mock_ws.py` 起在 `ws://0.0.0.0:8765`；在 demo 页控制台手动验证转发：
```js
stage.switchTo("angela");
stage.setViseme({ ParamMouthOpenY: 0.6 });
stage.playMotion("singing_high");
```
正式 WS→API 转发由舞台 `character-client.js` 实现（docs/06 §6）。
