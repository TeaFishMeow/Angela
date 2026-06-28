// 全局配置。可用 URL 参数覆盖：?ws=... &assets=...
import { resolveCharacterModels } from "../../character/model-presets.js";

const q = new URLSearchParams(location.search);
const characterModels = resolveCharacterModels(q);
const defaultWsUrl = () => {
  if (location.protocol === 'http:' || location.protocol === 'https:') {
    if (location.pathname.startsWith('/stage/')) {
      const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
      return `${proto}//${location.host}/ws`;
    }
  }
  return 'ws://localhost:8765';
};
export const CONFIG = {
  // WebSocket 地址：默认 mock_ws；真后端用 ?ws=ws://host:8000/ws
  wsUrl: q.get('ws') || defaultWsUrl(),
  // 静态资源根（后端 /assets 托管时留空走相对；纯本地可指 http://host:port）
  assetBase: q.get('assets') || '',
  // 两场串行顺序
  sceneOrder: ['chuanqi', 'yinwei-aiqing'],
  // 心跳纠偏阈值（秒）：|服务端t - 本地t| 超过则提示不同步
  driftWarn: 0.3,
  // Backing 在歌曲时间轴上的后移秒数。只给《传奇》保留 5 秒，《因为爱情》不偏移。
  backingDelaySecByScene: {
    chuanqi: 5,
    'yinwei-aiqing': 0,
  },
  // vocal/viseme 能量低于该阈值时强制闭嘴；只在没有 vocal 轨道时才走歌词兜底。
  vocalMouthThreshold: 0.08,
  // 数字人模型（character-client preload 用）。
  // P1 占位：Live2D 官方 CubismWebSamples · Cubism4（jsdelivr CDN）。Angela(女)=Hiyori、Neo(男)=Mark。
  // 真模型就位后改为本地相对路径："../character/models/angela/angela.model3.json"
  // Live2D model presets. Override with ?angela=ruri&neo=senko, or old values:
  // ?angela=old-haru&neo=old-natori. A full model3.json URL is also accepted.
  modelPresets: characterModels.presets,
  selectedModels: characterModels.selected,
  models: characterModels.models,
  modelGains: characterModels.gains,
};
export const SCENE_META = {
  chuanqi: { title: '传奇', character: 'angela' },
  'yinwei-aiqing': { title: '因为爱情', character: 'neo' },
};
