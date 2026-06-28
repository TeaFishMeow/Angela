/**
 * Angela · 数字人前端组件（队友 A）
 * ============================================================
 * 把两个 Live2D 数字人（Angela 女 / Neo 男）接进舞台：
 * 加载模型、按场切换、暴露稳定 JS API、用口型/动作数据驱动、在右侧透明叠层渲染。
 *
 * 依赖（无构建工具 · UMD 全局加载，见 docs/05 §1）：
 *   <script src="lib/live2dcubismcore.min.js"></script>   → window.Live2DCubismCore
 *   <script src="lib/pixi.min.js"></script>               → window.PIXI（pixi.js@7）
 *   <script src="lib/cubism4.min.js"></script>            → window.PIXI.live2d（pixi-live2d-display@0.5.0-beta）
 *
 * 接口契约见 docs/05-数字人接入（队友A）.md §2；舞台消费见 docs/06 §6。
 *
 * 关键设计点：
 *  - 一次只显示一个模型（按场切换），非当前模型 visible=false（性能）。
 *  - 口型写入放在 app.ticker 里、且用低优先级（UTILITY=-25）→ 在模型 autoUpdate 之后执行，
 *    否则 ParamMouthOpenY 会被模型 idle/motion 覆盖（pixi-live2d-display Issue #144）。
 *  - 缺动作组 silent fallback（→ Idle/idle/任意可用组），绝不抛错。
 *  - switchTo 时口型 current 不重置 → 新模型从同值继续 lerp，无跳变。
 */

const PIXI = window.PIXI || null;
const live2d = PIXI?.live2d || null;
const Live2DModel = live2d?.Live2DModel || null;
const MotionPriority = live2d?.MotionPriority || null;

// pixi UPDATE_PRIORITY.UTILITY（数值越小越后执行；确保口型写在模型 update 之后）
const TICK_PRIO_MOUTH = -25;

function clamp(v, lo, hi) {
  return v < lo ? lo : v > hi ? hi : v;
}

export class CharacterStage {
  /**
   * 挂载：创建 pixi 应用、注册口型 ticker 与 resize 监听，返回实例。
   * @param {HTMLCanvasElement} canvasEl 透明 canvas（叠在 MV 之上）
   * @param {{resolution?:number, resizeTo?:HTMLElement}} opts
   */
  static async mount(canvasEl, opts = {}) {
    if (!window.Live2DCubismCore || !Live2DModel) {
      throw new Error(
        "CharacterStage.mount: Live2D Cubism Core 或 pixi-live2d-display 未就绪。" +
        "确认 <script> 顺序为 cubism core → pixi.min.js → cubism4.min.js（见 docs/05 §1）。"
      );
    }

    // 不用 pixi resizeTo：它配合 autoDensity 会改写 canvas.style，与外部 CSS 定位冲突
    // （舞台 canvas 是右侧 min(44vw,620px)，parentElement 是全屏 body）。改由外部 CSS 控 style，
    // pixi 只管 device buffer，ResizeObserver 触发 renderer.resize 跟随 canvas 自身 CSS 尺寸。
    const res = opts.resolution ?? (window.devicePixelRatio || 1);
    const cw0 = opts.width || canvasEl.clientWidth || canvasEl.width || 800;
    const ch0 = opts.height || canvasEl.clientHeight || canvasEl.height || 600;
    const app = new PIXI.Application({
      view: canvasEl,
      backgroundAlpha: 0,           // pixi@7：transparent 已弃用，用 backgroundAlpha:0
      antialias: true,
      autoDensity: false,           // 外部 CSS 控 canvas style；pixi 仅管 device buffer
      resolution: res,
      width: Math.round(cw0 * res),
      height: Math.round(ch0 * res),
    });
    app.renderer.background.alpha = 0; // 双保险：透明

    const stage = new CharacterStage(app);

    // 口型写入：每帧 lerp，低优先级（在模型 update 之后覆盖嘴参数）
    app.ticker.add((delta) => stage._tickMouth(delta), undefined, TICK_PRIO_MOUTH);
    // 动作兜底：即使模型缺少同名 motion，也给容器加轻量身体摆动，避免路演时看起来完全静止
    app.ticker.add(() => stage._tickPose(), undefined, TICK_PRIO_MOUTH + 1);

    if (typeof ResizeObserver !== "undefined") {
      stage._ro = new ResizeObserver(() => stage._onResize());
      stage._ro.observe(canvasEl);
    }
    stage._onWinResize = () => stage._onResize();
    window.addEventListener("resize", stage._onWinResize);
    stage._onResize();   // 首次同步 device buffer

    return stage;
  }

  constructor(app) {
    this.app = app;
    this.models = new Map();        // name -> { model, name, error, gain, baseW, baseH }
    this._current = null;
    this._mouth = { target: 0, current: 0, form: null, gain: 1.0 };
    this._motion = { name: "idle", start: performance.now(), opts: {}, matched: false };
    this._ro = null;
    this._onWinResize = null;
    this._fadeRaf = null;
  }

  /**
   * 预载一个模型。可重复调用（已预载则直接返回）。
   * @param {string} name angela | neo
   * @param {{model:string, gain?:number}} param  model 为 .model3.json 路径/URL；gain 按模型嘴大小调
   */
  async preload(name, { model, gain = 1.0 } = {}) {
    if (!model) throw new Error(`CharacterStage.preload(${name}): 缺少 model 路径`);
    const exist = this.models.get(name);
    if (exist) return exist.model;

    try {
      const m = await Live2DModel.from(model, {
        autoInteract: false,         // 路演不需鼠标聚焦
        autoUpdate: true,            // 自动推进 idle 呼吸/眨眼/动作
        motionPreload: "all",        // 预载所有动作 → 切换不掉帧（docs/05 §5）
      });
      m.visible = false;
      m.alpha = 0;
      this.app.stage.addChild(m);
      // 记录原始尺寸（scale=1 时读一次，后续 layout 不受 transform 影响）
      const entry = { model: m, name, error: null, gain, baseW: m.width, baseH: m.height };
      this.models.set(name, entry);
      this._layout(entry);
      return m;
    } catch (err) {
      // 加载失败：记 error，后续 switchTo/setViseme 遇到走 no-op（流程不中断，docs/06 §6 兜底）
      console.error(`[CharacterStage] preload(${name}) 失败:`, err);
      this.models.set(name, { model: null, name, error: err, gain, baseW: 0, baseH: 0 });
      return null;
    }
  }

  /** 运行时调整某模型的口型增益（按模型嘴大小校准 0..1 归一值）。 */
  setGain(name, gain) {
    const e = this.models.get(name);
    if (e) e.gain = gain;
  }

  /**
   * 切到某模型（淡入淡出）。口型 current 不重置 → 新模型平滑衔接。
   * @param {string} name
   * @param {{blend?:number}} param  blend 秒，默认 0.3
   */
  async switchTo(name, { blend = 0.3 } = {}) {
    const entry = this.models.get(name);
    if (!entry || entry.error || !entry.model) return false;
    if (this._current === name) return true;

    const prevEntry = this._current ? this.models.get(this._current) : null;
    const prev = prevEntry?.model || null;
    this._current = name;

    const next = entry.model;
    next.visible = true;
    this._layout(entry);

    const dur = Math.max(0.05, blend) * 1000;   // ms
    const t0 = performance.now();
    const prevA0 = prev ? prev.alpha : 0;
    const nextA0 = next.alpha;

    const fade = () => {
      const k = Math.min(1, (performance.now() - t0) / dur);
      if (prev) {
        prev.alpha = prevA0 + (0 - prevA0) * k;   // 旧模型淡出
        if (k >= 1) prev.visible = false;         // 非当前隐藏（性能）
      }
      next.alpha = nextA0 + (1 - nextA0) * k;     // 新模型淡入
      if (k < 1) this._fadeRaf = requestAnimationFrame(fade);
      else this._fadeRaf = null;
    };
    if (this._fadeRaf) cancelAnimationFrame(this._fadeRaf);
    fade();
    return true;
  }

  /**
   * 设当前模型口型（合唱期主循环 / 对白期 viseme.frame 均调用此）。
   * @param {{ParamMouthOpenY?:number, ParamMouthForm?:number}} params
   */
  setViseme(params) {
    if (!params) return;
    const { ParamMouthOpenY, ParamMouthForm } = params;
    if (typeof ParamMouthOpenY === "number") this._mouth.target = clamp(ParamMouthOpenY, 0, 1);
    if (typeof ParamMouthForm === "number") this._mouth.form = clamp(ParamMouthForm, -1, 1);
  }

  /** 每帧口型 lerp + 写参数（在模型 update 之后执行，覆盖嘴参数）。 */
  _tickMouth(delta) {
    const e = this._current ? this.models.get(this._current) : null;
    if (!e || e.error || !e.model) return;
    const cm = e.model.internalModel?.coreModel;
    if (!cm) return;

    const M = this._mouth;
    const gain = e.gain ?? 1.0;
    // 帧率无关 lerp：k≈0.11@60fps，平滑且跟手
    const k = 1 - Math.pow(0.001, delta / 60);
    let target = clamp(M.target, 0, 1) * gain;
    // 爆破音过冲：目标陡升时加一点再回弹
    if (target - M.current > 0.25) target = Math.min(1, target + 0.08);
    M.current += (target - M.current) * k;   // target≈0 时 current 自然收敛到 0 → 静音闭嘴

    try {
      cm.setParameterValueById("ParamMouthOpenY", M.current);
      if (M.form !== null && M.form !== undefined) {
        cm.setParameterValueById("ParamMouthForm", M.form);
      }
    } catch (_) { /* 参数不存在则忽略 */ }
  }

  /**
   * 播动作（作用于当前模型）。缺动作组 silent fallback，绝不抛错（docs/05 §4）。
   * @param {string} name 动作词表名（idle/talk/singing_high/singing_low/sway/wave/bow/point）
   * @param {{priority?:number, index?:number}} opts
   * @returns {Promise<boolean>} 是否成功触发
   */
  async playMotion(name, opts = {}) {
    const e = this._current ? this.models.get(this._current) : null;
    if (!e || e.error || !e.model) return false;
    const m = e.model;
    const mm = m.internalModel?.motionManager;
    if (!mm) return false;

    // 先大小写不敏感匹配请求名；命中不了再 fallback 到 Idle/idle/任意可用组
    const matched = this._matchGroup(mm, name);
    const group = matched || this._fallbackGroup(mm);
    this._motion = { name: name || "idle", start: performance.now(), opts, matched: !!matched };
    if (!group) return false;   // 无任何可用动作组 → no-op

    const priority = opts.priority ?? MotionPriority?.NORMAL ?? 2;
    try {
      await m.motion(group, opts.index ?? undefined, priority); // undefined index → 同组随机
      return !!matched;   // 仅当请求名（大小写不敏感）真实存在返回 true；纯 fallback 返回 false
    } catch (_) { return false; }
  }

  /** 大小写不敏感匹配动作组（文档词表小写 idle/talk vs 模型大写 Idle）。返回真实组名或 null。 */
  _matchGroup(mm, name) {
    const defs = mm.definitions || {};
    const has = (g) => !!(defs[g] && defs[g].length > 0);
    if (has(name)) return name;
    const lower = String(name).toLowerCase();
    for (const k of Object.keys(defs)) {
      if (k.toLowerCase() === lower && has(k)) return k;
    }
    return null;
  }

  /** fallback 组：Idle → idle → 任意可用组（如 TapBody/Tap）。 */
  _fallbackGroup(mm) {
    const defs = mm.definitions || {};
    const has = (g) => !!(defs[g] && defs[g].length > 0);
    if (has("Idle")) return "Idle";
    if (has("idle")) return "idle";
    const first = Object.keys(defs).find(has);
    return first === undefined ? null : first;
  }

  /** 切到 idle 动作（内部已 fallback）。 */
  idle() { return this.playMotion("idle"); }

  /** 设表情（无 expressionManager 时 no-op）。 */
  setExpression(name) {
    const e = this._current ? this.models.get(this._current) : null;
    if (!e || e.error || !e.model) return false;
    const em = e.model.internalModel?.motionManager?.expressionManager;
    if (!em) return false;
    try { return e.model.expression(name); } catch (_) { return false; }
  }

  /** 当前模型名。 */
  get current() { return this._current; }

  /** 右侧、垂直居中、底部对齐；按 canvas 高度缩放。 */
  _layout(entry) {
    const m = entry?.model;
    if (!m || !m.internalModel) return;
    const cw = this.app.renderer.width / this.app.renderer.resolution;
    const ch = this.app.renderer.height / this.app.renderer.resolution;
    const baseH = entry.baseH || m.height || 1;
    const scale = (ch * 0.95) / baseH;     // 以高度为准缩放（留 5% 边距）
    m.scale.set(scale);
    m.anchor.set(0.5, 1.0);                // 水平居中、底部对齐
    entry.layoutX = cw * 0.72;             // 右侧区
    entry.layoutY = ch * 0.98;             // 贴近底部
    entry.layoutScale = scale;
    m.x = entry.layoutX;
    m.y = entry.layoutY;
  }

  /** 缺 motion 或 motion 很弱时的程序化表演兜底，只改容器 transform，不碰模型参数。 */
  _tickPose() {
    const e = this._current ? this.models.get(this._current) : null;
    if (!e || e.error || !e.model || e.layoutX == null) return;
    const m = e.model;
    const state = this._motion || { name: "idle", start: performance.now(), opts: {} };
    const opts = state.opts || {};
    let name = state.name || "idle";
    const t = (performance.now() - state.start) / 1000;
    const dur = Math.max(0.1, Number(opts.dur) || (name === "bow" ? 1.2 : 2.0));
    if (opts.loop === false && t >= dur) {
      if (opts.then && opts.then !== name) {
        this.playMotion(opts.then, { loop: true });
        return;
      }
      name = "idle";
    }

    let dx = 0, dy = 0, rot = 0, scaleMul = 1;
    if (name === "talk") {
      dx = Math.sin(t * 4.0) * 3;
      dy = Math.sin(t * 8.0) * 4;
      rot = Math.sin(t * 4.6) * 0.012;
    } else if (name === "singing_high" || name === "singing_low") {
      dx = Math.sin(t * 2.3) * 10;
      dy = Math.sin(t * 5.2) * 7;
      rot = Math.sin(t * 2.5) * 0.025;
      scaleMul = 1 + Math.sin(t * 5.2) * 0.006;
    } else if (name === "sway") {
      dx = Math.sin(t * 1.9) * 20;
      dy = Math.sin(t * 3.8) * 5;
      rot = Math.sin(t * 1.9) * 0.045;
    } else if (name === "wave" || name === "point") {
      dx = Math.sin(t * 5.0) * 6 + 10;
      dy = Math.sin(t * 6.5) * 4;
      rot = 0.035 + Math.sin(t * 8.0) * 0.02;
    } else if (name === "bow") {
      const k = Math.min(1, t / Math.min(0.8, dur));
      dy = 22 * Math.sin(k * Math.PI);
      rot = 0.09 * Math.sin(k * Math.PI);
      scaleMul = 1 - 0.018 * Math.sin(k * Math.PI);
    } else {
      dx = Math.sin(t * 1.3) * 4;
      dy = Math.sin(t * 2.1) * 3;
      rot = Math.sin(t * 1.5) * 0.01;
    }

    m.x = e.layoutX + dx;
    m.y = e.layoutY + dy;
    m.rotation = rot;
    m.scale.set((e.layoutScale || 1) * scaleMul);
  }

  /** resize 时重算所有已加载模型的 scale/position。 */
  reposition() {
    for (const e of this.models.values()) if (e.model) this._layout(e);
  }

  /** canvas CSS 尺寸变化：同步 renderer device buffer + 重算模型 layout。 */
  _onResize() {
    const view = this.app.view;
    const cw = view.clientWidth, ch = view.clientHeight;
    if (cw > 0 && ch > 0) {
      const res = this.app.renderer.resolution || 1;
      try { this.app.renderer.resize(Math.round(cw * res), Math.round(ch * res)); } catch (_) {}
    }
    this.reposition();
  }

  /** 销毁：释放模型纹理 + pixi 应用 + 监听。 */
  destroy() {
    if (this._fadeRaf) cancelAnimationFrame(this._fadeRaf);
    if (this._ro) { try { this._ro.disconnect(); } catch (_) {} }
    if (this._onWinResize) { try { window.removeEventListener("resize", this._onWinResize); } catch (_) {} }
    for (const e of this.models.values()) {
      if (e.model) {
        try { e.model.destroy({ children: true, texture: true, baseTexture: true }); } catch (_) {}
      }
    }
    this.models.clear();
    try { this.app.destroy(false); } catch (_) {}
    this._current = null;
  }
}
