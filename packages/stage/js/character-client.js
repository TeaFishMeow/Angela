// 数字人桥接：优先用队友A 的真 Live2D 模块（packages/character/character.js），
// 加载不到时用内置 MockCharacter（canvas 画占位脸 + 幅度驱动嘴），保证舞台可独立运行。
// 对外统一 API：init / preload / switchTo / setViseme / playMotion / idle。
// 见 docs/05-数字人接入（队友A）.md

const COLORS = { angela: '#ff9ec4', neo: '#8fd0ff' };
const LABELS = { angela: 'Angela（女）', neo: 'Neo（男）' };

// ---- 内置 mock：canvas 占位脸，嘴随 ParamMouthOpenY 张合 ----
function makeMock(canvas) {
  const ctx = canvas.getContext('2d');
  const fit = () => { canvas.width = canvas.clientWidth; canvas.height = canvas.clientHeight; };
  fit(); window.addEventListener('resize', fit);
  const st = { name: 'angela', mouth: 0, targetMouth: 0, motion: 'idle', motionStart: performance.now() };
  const setMotion = (name) => { st.motion = name || 'idle'; st.motionStart = performance.now(); };
  const pose = (name, t) => {
    if (name === 'talk') return { bob: Math.sin(t * 9) * 5, sway: Math.sin(t * 4) * 6, hand: Math.sin(t * 12) * 14 };
    if (name === 'singing_high' || name === 'singing_low') return { bob: Math.sin(t * 5.5) * 8, sway: Math.sin(t * 2.6) * 12, hand: Math.sin(t * 7) * 18 };
    if (name === 'sway') return { bob: Math.sin(t * 3) * 6, sway: Math.sin(t * 2.2) * 22, hand: Math.sin(t * 4) * 10 };
    if (name === 'wave') return { bob: Math.sin(t * 5) * 4, sway: 10, hand: 36 + Math.sin(t * 12) * 18 };
    if (name === 'bow') return { bob: Math.min(1, t / 0.8) * 26, sway: 0, hand: 0 };
    return { bob: Math.sin(t * 2.2) * 3, sway: Math.sin(t * 1.4) * 4, hand: 0 };
  };
  function loop() {
    const w = canvas.width, h = canvas.height, cx = w / 2, cy = h * 0.46;
    ctx.clearRect(0, 0, w, h);
    st.mouth += (st.targetMouth - st.mouth) * 0.35;
    const t = (performance.now() - st.motionStart) / 1000;
    const p = pose(st.motion, t);
    ctx.save();
    ctx.translate(p.sway, p.bob);
    // 身体/头部圆
    const r = Math.min(w, h) * 0.22;
    ctx.strokeStyle = COLORS[st.name] + 'cc';
    ctx.lineWidth = 7;
    ctx.lineCap = 'round';
    ctx.beginPath();
    ctx.moveTo(cx - r * 0.72, cy + r * 0.42);
    ctx.lineTo(cx - r * 1.08, cy + r * 0.72 + p.hand * 0.25);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(cx + r * 0.72, cy + r * 0.42);
    ctx.lineTo(cx + r * 1.05, cy + r * 0.62 - p.hand);
    ctx.stroke();
    ctx.fillStyle = COLORS[st.name] + '33';
    ctx.strokeStyle = COLORS[st.name];
    ctx.lineWidth = 4;
    ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
    // 眼睛
    ctx.fillStyle = '#fff';
    ctx.beginPath(); ctx.arc(cx - r * 0.35, cy - r * 0.15, r * 0.1, 0, 7); ctx.fill();
    ctx.beginPath(); ctx.arc(cx + r * 0.35, cy - r * 0.15, r * 0.1, 0, 7); ctx.fill();
    // 嘴（随 mouth 张合）
    const mh = Math.max(2, st.mouth * r * 0.7);
    ctx.fillStyle = '#5a2230';
    ctx.beginPath(); ctx.ellipse(cx, cy + r * 0.35, r * 0.22, mh, 0, 0, 7); ctx.fill();
    // 名字 + 动作
    ctx.fillStyle = COLORS[st.name];
    ctx.font = '20px sans-serif'; ctx.textAlign = 'center';
    ctx.fillText(LABELS[st.name], cx, cy + r + 36);
    ctx.fillStyle = '#fff8'; ctx.font = '13px sans-serif';
    ctx.fillText(`[mock] ${st.motion}`, cx, cy + r + 58);
    ctx.restore();
    requestAnimationFrame(loop);
  }
  loop();
  return {
    preload: async () => {},
    switchTo: async (name) => { st.name = name; },
    setViseme: (p) => { st.targetMouth = p?.ParamMouthOpenY ?? st.targetMouth; },
    playMotion: (name) => { setMotion(name); return true; },
    idle: () => { setMotion('idle'); },
  };
}

export const Character = {
  stage: null,
  mode: 'none',       // 'real' | 'mock'
  current: null,
  canvas: null,

  _fallbackToMock(reason) {
    if (this.mode === 'mock') return;
    console.warn('[character] 切到 mock 兜底：', reason);
    try { this.stage?.destroy?.(); } catch (e) {}
    this.stage = makeMock(this.canvas);
    this.mode = 'mock';
    if (this.current) this.stage.switchTo?.(this.current);
  },

  async init(canvas) {
    this.canvas = canvas;
    try {
      // character-client 在 packages/stage/js/，character.js 在 packages/character/ → 退两级
      const mod = await import('../../character/character.js');
      if (!mod.CharacterStage) throw new Error('CharacterStage 未导出');
      this.stage = await mod.CharacterStage.mount(canvas);
      this.mode = 'real';
      console.info('[character] 使用真 Live2D 模块');
    } catch (e) {
      console.warn('[character] 真 Live2D 不可用，启用 mock：', e.message);
      this.stage = makeMock(canvas);
      this.mode = 'mock';
    }
  },
  async preload(name, opts) { return this.stage.preload?.(name, opts); },
  async switchTo(name, opts) {
    this.current = name;
    const ok = await this.stage.switchTo?.(name, opts);
    if (ok === false && this.mode === 'real') {
      this._fallbackToMock(`模型 ${name} 不可用或未加载`);
      return this.stage.switchTo?.(name, opts);
    }
    return ok;
  },
  setViseme(p) { this.stage.setViseme?.(p); },
  playMotion(name, opts) { this.stage.playMotion?.(name, opts); },
  idle() { this.stage.idle?.(); },
};
