// 主时钟 + 轨道查表。合唱期渲染权威 = 伴奏带 <audio>.currentTime；
// 音频不可用（mock 无文件/后端没出 backing）时回退到 WS scene.tick；
// 离线（无 WS）时回退到虚拟时钟。见 docs/02 §5、docs/06 §4
import { CONFIG } from './config.js';

export class Clock {
  constructor() {
    this.audio = null;
    this.tracks = { visemes: null, actions: null };
    this.lastTick = null;       // 来自 scene.tick
    this.lastTickAt = null;     // 收到 scene.tick 的本地时间
    this.virtualStart = null;   // performance.now()/1000
    this.drift = 0;             // |服务端t - 本地t|
    this.baseOffset = 0;        // 跳前奏偏移：tick/虚拟回退时加上，保持与音频同一时间轴
    this.audioOffset = 0;       // 音频相对歌曲时间的补偿：songTime = audio.currentTime + audioOffset
  }

  attach(audioEl) { this.audio = audioEl; }
  reset() {
    this.lastTick = null;
    this.lastTickAt = null;
    this.virtualStart = null;
    this.drift = 0;
    this.baseOffset = 0;
    this.audioOffset = 0;
    this.tracks = { visemes: null, actions: null };
  }
  // enterSinging 跳前奏后设：让非音频回退（tick/虚拟）也按 offset 对齐，口型/歌词不错位
  setBaseOffset(v) { this.baseOffset = v || 0; }
  setAudioOffset(v) { this.audioOffset = v || 0; }

  // 离线模式：以真实经过时间作为虚拟时钟
  useVirtual() {
    this.virtualStart = performance.now() / 1000;
    this.lastTick = null;
    this.lastTickAt = null;
  }
  ensureVirtual() {
    if (this.lastTick == null && this.virtualStart == null) this.useVirtual();
  }

  // 收到心跳：记录服务端时间 + 计算漂移（对齐 baseOffset 后再比）
  notify(serverT) {
    const localAudioT = this._audioTime();
    this.lastTick = serverT;
    this.lastTickAt = performance.now() / 1000;
    this.drift = localAudioT == null ? 0 : Math.abs(serverT - (localAudioT + this.audioOffset - this.baseOffset));
  }

  _audioTime() {
    if (this.audio && this.audio.readyState >= 2 && !this.audio.paused && isFinite(this.audio.duration) && this.audio.duration > 0) {
      return this.audio.currentTime;
    }
    return null;
  }

  // ★ 当前时间（渲染权威）
  now() {
    const audioT = this._audioTime();
    if (audioT != null) return audioT + this.audioOffset;
    if (this.lastTick != null) {
      const elapsed = this.lastTickAt == null ? 0 : performance.now() / 1000 - this.lastTickAt;
      return this.lastTick + elapsed + this.baseOffset;
    }
    if (this.virtualStart != null) return performance.now() / 1000 - this.virtualStart + this.baseOffset;
    return this.baseOffset;
  }

  absUrl(u) { return /^https?:/.test(u) ? u : (CONFIG.assetBase + u); }
  async fetchJSON(u) { return fetch(this.absUrl(u)).then((r) => r.json()); }
  async resolve(v) {
    if (!v) return null;
    if (typeof v === 'string') return this.fetchJSON(v);
    if (typeof v === 'object' && v.url) return this.fetchJSON(v.url);
    return v; // 内联对象
  }

  async loadTracks({ lyrics, visemes, actions }) {
    this.tracks.visemes = await this.resolve(visemes);
    this.tracks.actions = await this.resolve(actions);
    return { lyrics: await this.resolve(lyrics), visemes: this.tracks.visemes, actions: this.tracks.actions };
  }

  // 口型：按 t 在 frames 线性插值 → {ParamMouthOpenY, ...}
  visemeAt(t) {
    const v = this.tracks.visemes;
    if (!v || !v.frames || !v.frames.length) return { ParamMouthOpenY: this.fallbackMouthAt(t) };
    const fps = v.fps || 30, start = v.start || 0;
    const f = (t - start) * fps;
    const i = Math.floor(f), frac = f - i;
    const n = v.frames.length;
    const a = v.frames[Math.max(0, Math.min(i, n - 1))];
    const b = v.frames[Math.max(0, Math.min(i + 1, n - 1))];
    const params = {};
    (v.params || ['ParamMouthOpenY']).forEach((k, j) => {
      const av = a[j] || 0, bv = (b && b[j] != null) ? b[j] : av;
      params[k] = av + (bv - av) * frac;
    });
    return params;
  }

  fallbackMouthAt(t) {
    const a = 0.38 + 0.24 * Math.sin(t * 13.0) + 0.14 * Math.sin(t * 23.0 + 0.7);
    return Math.max(0.06, Math.min(0.88, a));
  }

  // 动作：找 t 所在的段
  actionAt(t) {
    const tl = this.tracks.actions && this.tracks.actions.timeline;
    if (!tl) return null;
    let seg = null;
    for (const s of tl) { if (s.t <= t) seg = s; else break; }
    return seg;
  }
}
