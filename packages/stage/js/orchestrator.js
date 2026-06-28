// 舞台编排（路演版）：两场串行 + 主时钟主循环 + WS 驱动 + 离线兜底。
// 新增：MV 背景与伴奏带同步起播；网易云式歌词（见 lyrics.js）；"跳到收尾"直入 outro。
// 见 docs/02-接口契约.md、docs/06-舞台前端.md
import { CONFIG, SCENE_META } from './config.js';
import { WsClient } from './ws-client.js';
import { Clock } from './clock.js';
import { LyricsView } from './lyrics.js';
import { Character } from './character-client.js';

const $ = (id) => document.getElementById(id);
const audio = $('audio'), mv = $('mv');
const ws = new WsClient();
const clock = new Clock(); clock.attach(audio);
const lyrics = new LyricsView();

let scene = null;
let phase = 'idle';          // idle | loaded | singing | outro
let curAction = null, rafId = null, sceneIdx = 0, offlineTimer = null;
let introActive = false, outroSent = false;   // 真后端按 proto 拆分 load/start/outro，舞台据此自动串接
let ttsPlayback = Promise.resolve(false);
let ttsCollecting = false, ttsActing = false, ttsVisemeRaf = null;

// 中文/空格路径要 encodeURI（MV/backing 文件名含中文+空格）
const absUrl = (u) => /^https?:/.test(u) ? u : encodeURI(CONFIG.assetBase + u);
const backingDelayForScene = (id) => Math.max(0, CONFIG.backingDelaySecByScene?.[id] ?? CONFIG.backingDelaySec ?? 0);
const sampleJSON = async (name, fallback) => {
  const base = '../../data/samples/';
  try {
    const r = await fetch(base + name);
    if (r.ok) return await r.json();
  } catch (e) {}
  const r = await fetch(base + fallback);
  return r.json();
};

// ---------- UI 小工具 ----------
function setStatus(text, kind = '') {
  $('status').textContent = text;
  $('status').style.color = kind === 'ok' ? '#9f9' : kind === 'warn' ? '#fc6' : '';
}
function showSubtitle(speaker, text) {
  const el = $('subtitle');
  el.innerHTML = `<b>${speaker}</b>：${text}`;
  el.classList.remove('singing-subtitle');
  el.classList.remove('hidden');
}
function hideSubtitle() {
  const el = $('subtitle');
  el.classList.add('hidden');
  el.classList.remove('singing-subtitle');
}
function resetTtsPlayback() {
  ttsCollecting = false;
  ttsActing = false;
  ttsBuf = [];
  ttsVisemes = [];
  if (ttsVisemeRaf) cancelAnimationFrame(ttsVisemeRaf);
  ttsVisemeRaf = null;
}

const clamp01 = (v) => Math.max(0, Math.min(1, v));
const hasVocalVisemeTrack = () => !!clock.tracks.visemes?.frames?.length;
const vocalMouthThreshold = () => Math.max(0, Math.min(0.95, CONFIG.vocalMouthThreshold ?? 0.08));
const hasDigitalSinger = (ln) => /Angela|Neo|数字/i.test(ln?.performer || '');
const isTeammateOnly = (ln) => /Teammate|队友|You/i.test(ln?.performer || '') && !hasDigitalSinger(ln);
const isSingingAction = (seg) => /singing|sway/i.test(seg?.action || '');

function lyricMouthAt(t, ln, strength = 1) {
  const text = String(ln?.text || '');
  const dur = Math.max(0.5, Number(ln?.d) || 3);
  const local = ln ? Math.max(0, t - ln.t) : t;
  const progress = ln ? clamp01(local / dur) : 0.5;
  const syllableRate = ln ? Math.max(5.8, Math.min(10.5, text.length / dur * 1.35)) : 7.2;
  const attack = Math.min(1, local / 0.18);
  const release = ln ? Math.min(1, Math.max(0, (ln.t + dur - t) / 0.25)) : 1;
  const envelope = Math.max(0.05, Math.min(attack, release));
  const cycle = (local * syllableRate) % 1;
  const openPhase = cycle < 0.58 ? Math.sin((cycle / 0.58) * Math.PI) : 0;
  const pulse = Math.pow(Math.max(0, openPhase), 0.48);
  const detail = Math.max(0, Math.sin(local * Math.PI * 2 * (syllableRate * 0.5) + 0.8)) * 0.12;
  const phrasing = 0.88 + 0.12 * Math.sin(progress * Math.PI);
  return clamp01((0.025 + pulse * 0.78 + detail) * envelope * phrasing * strength);
}

function articulationGateAt(t, ln) {
  const text = String(ln?.text || '');
  const dur = Math.max(0.5, Number(ln?.d) || 3);
  const local = ln ? Math.max(0, t - ln.t) : t;
  const syllableRate = ln ? Math.max(5.8, Math.min(10.5, text.length / dur * 1.35)) : 7.2;
  const cycle = (local * syllableRate) % 1;
  if (cycle >= 0.62) return 0.04;
  return 0.08 + 0.92 * Math.pow(Math.sin((cycle / 0.62) * Math.PI), 0.55);
}

function singingVisemeAt(t, seg) {
  const params = clock.visemeAt(t);
  const baked = clamp01(params.ParamMouthOpenY || 0);
  const hasVocalTrack = hasVocalVisemeTrack();
  const threshold = vocalMouthThreshold();
  const ln = lyrics.activeLineAt(t);

  if (ln && isTeammateOnly(ln)) {
    return { ...params, ParamMouthOpenY: Math.min(baked, 0.04) };
  }

  const shouldSing = (ln && hasDigitalSinger(ln)) || (!ln && isSingingAction(seg));
  if (!shouldSing) return params;

  if (hasVocalTrack && baked < threshold) {
    return { ...params, ParamMouthOpenY: 0 };
  }

  const gate = articulationGateAt(t, ln);
  if (hasVocalTrack) {
    const vocalEnvelope = clamp01((baked - threshold) / (1 - threshold));
    const mouth = Math.min(0.92, (0.10 + vocalEnvelope * 0.82) * gate);
    return { ...params, ParamMouthOpenY: mouth };
  }

  const fallback = lyricMouthAt(t, ln, ln ? 1.0 : 0.62);
  return { ...params, ParamMouthOpenY: fallback };
}

// ---------- 合唱主循环（主时钟 = 伴奏带 currentTime，自动回退 tick/虚拟）----------
function loop() {
  if (phase !== 'singing') return;
  const t = clock.now();
  $('clock-t').textContent = `⏱ ${t.toFixed(1)}s`;
  $('clock-t').style.color = clock.drift > CONFIG.driftWarn ? '#f86' : '';
  lyrics.update(t);
  const seg = clock.actionAt(t);
  if (!ttsActing) Character.setViseme(singingVisemeAt(t, seg));
  if (!ttsActing && seg && seg !== curAction) { Character.playMotion(seg.action, seg); curAction = seg; }
  rafId = requestAnimationFrame(loop);
}
function startLoop() { cancelAnimationFrame(rafId); curAction = null; loop(); }
function stopLoop() { cancelAnimationFrame(rafId); }

// ---------- 进入合唱（MV 与伴奏带同步起播，跳过前奏）----------
async function enterSinging() {
  phase = 'singing';
  $('phase').textContent = '合唱中';
  hideSubtitle();
  if (!scene._tracksReady && !scene._tracks && scene.manifest?.tracks) {
    scene._tracksReady = (async () => {
      const r = await clock.loadTracks(scene.manifest.tracks);
      scene._tracks = scene.manifest.tracks; scene._lyrics = r.lyrics;
      lyrics.load(r.lyrics);
    })();
  }
  if (scene._tracksReady) {
    try {
      await scene._tracksReady;   // 等轨道（尤其歌词）就绪再取首句时间
    } catch (e) {
      console.warn('[tracks] load failed, use generated mouth/action fallback', e);
      setStatus('轨道加载失败，使用口型/动作兜底', 'warn');
    }
  }
  // 跳过前奏：从第一句歌词/人声开始（传奇前奏~36s、因为爱情~12s）。
  // 否则前奏期没词、嘴不动（visemes 正确为 0），看着像坏了。
  const offset = scene._startAt ?? scene._lyrics?.[0]?.t ?? 0;
  const backingDelay = backingDelayForScene(scene?.id);
  const audioStart = Math.max(0, offset - backingDelay);
  clock.setBaseOffset(offset);   // tick/虚拟回退也按 offset 对齐，口型/歌词不错位
  clock.setAudioOffset(backingDelay);
  audio.src = absUrl(scene._backingUrl || scene.manifest?.audio?.backing || '');
  audio.onerror = () => {
    clock.ensureVirtual();
    setStatus('音频不可用，使用虚拟时钟兜底', 'warn');
  };
  // 先 play 再 seek（seek-then-play 在部分浏览器会卡住不发声）；autoplay 被拦则回退 tick(+offset)
  audio.play()
    .then(() => { try { if (audioStart > 0) audio.currentTime = audioStart; } catch (e) {} })
    .catch(() => {
      clock.ensureVirtual();
      setStatus('音频未播放，使用 tick/虚拟时钟兜底', 'warn');
    });
  if (mv.src) {
    mv.play()
      .then(() => { try { if (offset > 0) mv.currentTime = offset; } catch (e) {} })
      .catch(() => {});
  }
  const act = scene.character === 'angela' ? 'singing_high' : 'singing_low';
  Character.playMotion(act, { loop: true });
  startLoop();
}

// ---------- WS 事件 ----------
function wireWs() {
  ws.on('_open', () => setStatus('已连接', 'ok'));
  ws.on('_close', () => setStatus('离线（重连中…）', 'warn'));

  ws.on('scene.loaded', (d) => {
    stopLoop();
    clock.reset();
    resetTtsPlayback();
    Character.setViseme({ ParamMouthOpenY: 0 });
    scene = d;
    introActive = true; outroSent = false;   // 新场：intro 待播、outro 未发
    ttsPlayback = Promise.resolve(false);
    $('phase').textContent = `已加载：${d.title}`;
    $('char-name').textContent = `${d.title} · ${d.character}`;
    if (d.manifest?.mv) { mv.src = absUrl(d.manifest.mv); mv.load(); }   // 仅载入首帧，合唱起再播
    $('btn-finale').disabled = false;
    startIntroFallbackTimer();
  });
  ws.on('character.set', (d) => { Character.switchTo(d.name); $('char-name').textContent = d.name; });

  ws.on('scene.tracks', (d) => {
    // 存 promise：enterSinging 要 await 它拿到首句时间再 seek（跳前奏）
    scene._tracksReady = (async () => {
      try {
        const r = await clock.loadTracks(d);
        scene._tracks = d; scene._lyrics = r.lyrics;
        lyrics.load(r.lyrics);
      } catch (e) {
        console.warn('[tracks] load failed', e);
        setStatus('轨道加载失败，使用口型/动作兜底', 'warn');
      }
    })();
  });
  ws.on('scene.start', (d) => {
    if (d.backingUrl) scene._backingUrl = d.backingUrl;
    scene._startAt = Number.isFinite(Number(d.t0)) ? Number(d.t0) : undefined;
    enterSinging();
  });
  ws.on('scene.tick', (d) => clock.notify(d.t));
  ws.on('scene.end', () => {
    phase = 'outro';
    stopLoop();
    resetTtsPlayback();
    $('phase').textContent = '唱完（收尾中）';
    $('btn-next').disabled = sceneIdx >= CONFIG.sceneOrder.length - 1;
    if (!outroSent && ws.connected) { outroSent = true; ws.send('outro.start', { id: scene?.id || '' }); }
  });

  ws.on('subtitle', (d) => showSubtitle(d.speaker || 'Angela', d.text));
  ws.on('viseme.frame', (d) => {
    if (ttsCollecting) {
      ttsVisemes.push({ t: Number(d.t ?? d.ts ?? 0) || 0, params: d.params || {} });
    } else {
      Character.setViseme(d.params || {});
    }
  });
  ws.on('action.set', async (d) => {
    if (phase === 'singing' && !introActive && d.name === 'idle') {
      ttsPlayback.then(() => { curAction = null; });
      return;
    }
    Character.playMotion(d.name, d);
    if (introActive && d.name === 'idle') {
      await ttsPlayback;
      Character.setViseme({ ParamMouthOpenY: 0 });
      introActive = false;
      ws.send('scene.start', { id: scene?.id || '' });
    }
  });
  ws.on('tts.start', () => { ttsBuf = []; ttsVisemes = []; ttsMime = 'audio/wav'; ttsCollecting = true; ttsActing = true; });
  ws.on('tts.audio', (d) => { if (d.b64) { ttsBuf.push(d.b64); if (d.mime) ttsMime = d.mime; } });
  // 每行 tts.end 后播放该行音频；等最后的 action.set idle 后再进合唱。
  ws.on('tts.end', () => {
    ttsCollecting = false;
    const frames = ttsVisemes.slice();
    ttsPlayback = ttsPlayback
      .then(() => playTtsBuffer(frames))
      .then((ok) => {
        if (phase === 'singing') hideSubtitle();
        return ok;
      });
  });
  ws.on('error', (d) => console.warn('[ws error]', d));
}

function startIntroFallbackTimer() {
  setTimeout(async () => {
    if (!introActive || !ws.connected || phase === 'singing') return;
    await ttsPlayback;
    Character.setViseme({ ParamMouthOpenY: 0 });
    introActive = false;
    ws.send('scene.start', { id: scene?.id || '' });
  }, 20000);
}

let ttsBuf = [];
let ttsVisemes = [];
let ttsMime = 'audio/wav';
function playTtsBuffer(frames = []) {
  if (!ttsBuf.length) {
    ttsActing = false;
    return Promise.resolve(false);
  }
  try {
    const bin = atob(ttsBuf.join(''));
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    const url = URL.createObjectURL(new Blob([bytes], { type: ttsMime || 'audio/wav' }));
    const ttsAudio = new Audio(url);
    ttsBuf = [];
    return new Promise((resolve) => {
      let done = false;
      let frameIdx = 0;
      const finish = (ok) => {
        if (done) return;
        done = true;
        if (ttsVisemeRaf) cancelAnimationFrame(ttsVisemeRaf);
        ttsVisemeRaf = null;
        ttsActing = false;
        Character.setViseme({ ParamMouthOpenY: 0 });
        URL.revokeObjectURL(url);
        resolve(ok);
      };
      const tick = () => {
        const t = ttsAudio.currentTime || 0;
        while (frameIdx + 1 < frames.length && frames[frameIdx + 1].t <= t) frameIdx++;
        if (frames[frameIdx]) Character.setViseme(frames[frameIdx].params || {});
        if (!done && !ttsAudio.ended) ttsVisemeRaf = requestAnimationFrame(tick);
      };
      ttsAudio.onended = () => finish(true);
      ttsAudio.onerror = () => finish(false);
      ttsAudio.play().then(() => { tick(); }).catch(() => finish(false));
    });
  } catch (e) {
    console.warn('[tts] play failed', e);
    ttsBuf = [];
    ttsActing = false;
    return Promise.resolve(false);
  }
}

// ---------- 离线兜底（WS 不可用）：吃 data/samples，虚拟时钟驱动 ----------
async function offlineRun(id) {
  setStatus('离线演示（虚拟时钟）', 'warn');
  clock.reset();
  resetTtsPlayback();
  Character.setViseme({ ParamMouthOpenY: 0 });
  const man = await sampleJSON('scene.' + id + '.json', 'scene.chuanqi.json');
  scene = { id, title: man.title, character: man.character, manifest: man };
  const lyr = await sampleJSON('lyrics.' + id + '.json', 'lyrics.sample.json');
  clock.tracks.visemes = await sampleJSON('visemes.' + id + '.json', 'visemes.sample.json');
  clock.tracks.actions = await sampleJSON('actions.' + id + '.json', 'actions.sample.json');
  await Character.switchTo(man.character);
  lyrics.load(lyr);
  clock.setBaseOffset(lyr?.lines?.[0]?.t || 0);
  clock.setAudioOffset(backingDelayForScene(id));
  phase = 'singing';
  $('phase').textContent = `合唱中（离线·${man.title}）`;
  Character.playMotion(man.character === 'angela' ? 'singing_high' : 'singing_low', { loop: true });
  clock.useVirtual();
  startLoop();
  $('btn-finale').disabled = false;
  if (offlineTimer) clearTimeout(offlineTimer);
  offlineTimer = setTimeout(() => {
    phase = 'outro'; stopLoop();
    $('phase').textContent = '唱完（离线）';
    $('btn-next').disabled = sceneIdx >= CONFIG.sceneOrder.length - 1;
  }, (man.duration || 90) * 1000);
}

// 离线 outro：无 TTS 音频，用对白文本 + 幅度模拟口型
function offlineOutro() {
  setStatus('离线·收尾', 'warn');
  const lines = (scene?.manifest?.dialogue?.outro) || ['今天就到这里啦，谢谢大家。'];
  const speaker = scene?.character === 'neo' ? 'Neo' : 'Angela';
  let i = 0;
  const speak = () => {
    if (i >= lines.length) { Character.setViseme({ ParamMouthOpenY: 0 }); Character.idle(); hideSubtitle(); return; }
    showSubtitle(speaker, lines[i]);
    Character.playMotion('wave', { loop: false, dur: 2.5 });
    const dur = Math.max(1.6, lines[i].length * 0.2) * 1000;
    const t0 = performance.now();
    const tick = () => {
      const e = performance.now() - t0;
      if (e >= dur) { i++; speak(); return; }
      Character.setViseme({ ParamMouthOpenY: Math.max(0, 0.5 + 0.45 * Math.sin(e / 1000 * 14)) });
      requestAnimationFrame(tick);
    };
    tick();
  };
  speak();
}

// ---------- 控制按钮 ----------
function wireButtons() {
  $('btn-start').onclick = () => {
    hideSubtitle();
    sceneIdx = 0;
    const id = CONFIG.sceneOrder[0];
    if (ws.connected) ws.send('scene.load', { id });
    else offlineRun(id);
  };
  $('btn-next').onclick = () => {
    sceneIdx += 1;
    if (sceneIdx >= CONFIG.sceneOrder.length) return;
    const id = CONFIG.sceneOrder[sceneIdx];
    hideSubtitle();
    if (ws.connected) ws.send('scene.load', { id });
    else offlineRun(id);
  };
  $('btn-finale').onclick = () => {
    if (!scene) return;
    stopLoop(); audio.pause(); try { mv.pause(); } catch (e) {}
    resetTtsPlayback();
    if (offlineTimer) { clearTimeout(offlineTimer); offlineTimer = null; }
    phase = 'outro';
    $('phase').textContent = '收尾中（数字人开口）';
    outroSent = true;   // 防自然 scene.end 再触发一次 outro
    if (ws.connected) ws.send('scene.jump_outro', { id: scene.id || '' });
    else offlineOutro();
  };
  $('btn-stop').onclick = () => {
    phase = 'idle'; stopLoop(); audio.pause(); try { mv.pause(); } catch (e) {}
    resetTtsPlayback();
    Character.setViseme({ ParamMouthOpenY: 0 });
    if (offlineTimer) { clearTimeout(offlineTimer); offlineTimer = null; }
    if (ws.connected) ws.send('scene.stop', { id: scene?.id || '' });
    $('phase').textContent = '已停止';
  };
}

// ---------- 启动 ----------
async function init() {
  await Character.init($('cv'));
  for (const name of ['angela', 'neo']) {
    try { await Character.preload(name, { model: CONFIG.models[name], gain: CONFIG.modelGains?.[name] ?? 1.0 }); }
    catch (e) { /* 模型缺，switchTo 时再处理 */ }
  }
  await Character.switchTo('angela'); Character.idle();
  window.Character = Character;   // 调试钩子（docs/06 §6 约定 window.stage）
  wireButtons(); wireWs();
  setStatus('连接中…');
  ws.connect();
}
init();
