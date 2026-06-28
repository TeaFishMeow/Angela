// WebSocket 客户端：信封封装 + 事件总线 + 断线重连。
// 信封：{ type, seq, ts, data }。见 docs/02-接口契约.md
import { CONFIG } from './config.js';

export class WsClient {
  constructor(url = CONFIG.wsUrl) {
    this.url = url;
    this.seq = 0;
    this.ws = null;
    this.handlers = new Map();      // type -> Set<fn>
    this.connected = false;
    this.backoff = 0;
    this._manualClose = false;
  }

  on(type, fn) {
    if (!this.handlers.has(type)) this.handlers.set(type, new Set());
    this.handlers.get(type).add(fn);
    return () => this.handlers.get(type)?.delete(fn);
  }
  emit(msg) {
    const set = this.handlers.get(msg.type);
    if (set) for (const fn of set) fn(msg.data, msg);
    // 通配
    const all = this.handlers.get('*');
    if (all) for (const fn of all) fn(msg);
  }

  send(type, data = {}, ts = 0) {
    if (!this.connected) return;
    this.seq += 1;
    this.ws.send(JSON.stringify({ type, seq: this.seq, ts, data }));
  }

  async connect() {
    return new Promise((resolve) => {
      const open = () => {
        try {
          this.ws = new WebSocket(this.url);
        } catch (e) { return this._scheduleReconnect(); }
        this.ws.onopen = () => {
          this.connected = true; this.backoff = 0;
          this.emit({ type: '_open' });
          resolve();
        };
        this.ws.onmessage = (ev) => {
          try { this.emit(JSON.parse(ev.data)); }
          catch (e) { console.warn('[ws] bad msg', e); }
        };
        this.ws.onclose = () => {
          this.connected = false;
          this.emit({ type: '_close' });
          if (!this._manualClose) this._scheduleReconnect();
        };
        this.ws.onerror = () => { /* close 会接上 */ };
      };
      open();
    });
  }

  _scheduleReconnect() {
    this.backoff = Math.min(this.backoff * 2 || 1000, 8000);
    setTimeout(() => { if (!this._manualClose) this.connect(); }, this.backoff);
  }

  close() { this._manualClose = true; this.ws?.close(); }
}
