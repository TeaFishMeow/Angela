// 网易云式单列滚动歌词（路演版）
// - 单列、当前句垂直居中、平滑 lerp 滚动
// - 四态着色：singing(正在唱) / upcoming(即将进入) / past(已完成) / future(未进入)
// - performer 分段：text 内 （Neo）/（合唱）/(You) 标记剥掉、按段着色（仅 singing/upcoming 鲜明）
// 见 docs/03-数据格式规范.md §2、docs/06 §5

const DIGITAL = /Neo|Angela|数字/i;
const TEAMMATE = /队友|You/i;

function whoOfPerformer(p) {
  if (!p) return 'duet';
  const d = DIGITAL.test(p), t = TEAMMATE.test(p);
  if (d && t) return 'duet';
  if (d) return 'neo';
  if (t) return 'teammate';
  return 'duet';
}
function labelWho(label) {
  if (/Neo/i.test(label)) return 'neo';
  if (/合唱/.test(label)) return 'duet';
  if (/You|队友/i.test(label)) return 'teammate';
  return 'duet';
}
function esc(s) { return s.replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c])); }
function performerLabel(p) {
  if (!p) return '';
  if (/Neo/i.test(p) && /Teammate|队友|You/i.test(p)) return 'Neo + 队友C';
  if (/Neo/i.test(p)) return 'Neo';
  if (/Teammate|队友|You/i.test(p)) return '队友C';
  return p;
}
function renderPerformerHint(ln, enabled) {
  if (!enabled) return '';
  const who = whoOfPerformer(ln.performer);
  const label = performerLabel(ln.performer);
  if (!label) return '';
  return `<span class="singer-hint singer-${who}">${esc(label)}</span>`;
}
// 单句复合：剥掉 （谁）/(谁) 标记，后续文本按标记 who 着色
function renderHtml(text, performer) {
  const re = /[（(]\s*([^）)]+?)\s*[）)]/g;
  let html = '', last = 0, m, who = whoOfPerformer(performer);
  while ((m = re.exec(text))) {
    if (m.index > last) html += `<span class="seg seg-${who}">${esc(text.slice(last, m.index))}</span>`;
    who = labelWho(m[1]);
    last = re.lastIndex;
  }
  html += `<span class="seg seg-${who}">${esc(text.slice(last))}</span>`;
  return html;
}

export class LyricsView {
  constructor() {
    this.wrap = document.getElementById('lyrics');
    this.scroll = document.getElementById('lyrics-scroll');
    this.items = [];
    this.currentIdx = -1;
    this.offset = 0;
    this.target = 0;
  }

  load(data) {
    const lines = (data && data.lines) || [];
    const showSingerHint = data?.scene === 'yinwei-aiqing';
    this.scroll.innerHTML = '';
    this.items = lines.map((ln) => {
      const el = document.createElement('div');
      el.className = 'lyric-line future';
      el.innerHTML = renderPerformerHint(ln, showSingerHint) + renderHtml(ln.text, ln.performer);
      this.scroll.appendChild(el);
      return { ln, el };
    });
    this.currentIdx = -1;
    this.offset = 0;
    this.target = 0;
    this.scroll.style.transform = 'translateY(0px)';
    this.applyStates();
  }

  // 每帧调用（合唱主循环）：定位当前句、滚动、四态
  update(t) {
    let idx = -1;
    for (let i = 0; i < this.items.length; i++) {
      const ln = this.items[i].ln;
      if (t >= ln.t && t < ln.t + ln.d) { idx = i; break; }
    }
    if (idx < 0) {
      // 间隙：保持"最近唱过"的那句为当前（网易云体感）
      for (let i = this.items.length - 1; i >= 0; i--) {
        if (t >= this.items[i].ln.t) { idx = i; break; }
      }
    }
    if (idx !== this.currentIdx) {
      this.currentIdx = idx;
      this.applyStates();
      this.computeTarget();
    }
    // 平滑滚动（lerp）
    this.offset += (this.target - this.offset) * 0.16;
    this.scroll.style.transform = `translateY(${-this.offset}px)`;
  }

  activeLineAt(t) {
    for (const it of this.items) {
      const ln = it.ln;
      if (t >= ln.t && t < ln.t + ln.d) return ln;
    }
    return null;
  }

  applyStates() {
    const c = this.currentIdx;
    this.items.forEach((it, i) => {
      let st = 'future';
      if (i === c) st = 'singing';
      else if (i === c + 1) st = 'upcoming';
      else if (i < c) st = 'past';
      it.el.className = 'lyric-line ' + st;
    });
  }

  computeTarget() {
    if (this.currentIdx < 0) { this.target = 0; return; }
    const el = this.items[this.currentIdx].el;
    const wrapH = this.wrap.clientHeight;
    // 让当前句垂直居中
    this.target = el.offsetTop + el.offsetHeight / 2 - wrapH / 2;
  }

  clear() {
    this.scroll.innerHTML = '';
    this.items = [];
    this.currentIdx = -1;
    this.offset = 0;
    this.target = 0;
    this.scroll.style.transform = 'translateY(0px)';
  }
}
