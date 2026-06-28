const EIKANYA = "https://cdn.jsdelivr.net/gh/Eikanya/Live2d-model";
const OFFICIAL = "https://cdn.jsdelivr.net/gh/Live2D/CubismWebSamples/Samples/Resources";

export const MODEL_PRESETS = {
  ruri: {
    label: "Ruri Miko",
    gender: "female",
    source: "Eikanya/Live2d-model",
    model: `${EIKANYA}/galgame%20live2d/Fox%20Hime%20Zero/ruri_miko/ruri_miko.model3.json`,
    gain: 1.0,
  },
  mori: {
    label: "Mori Suit",
    gender: "female",
    source: "Eikanya/Live2d-model",
    model: `${EIKANYA}/galgame%20live2d/Fox%20Hime%20Zero/mori_suit/mori_suit.model3.json`,
    gain: 1.0,
  },
  "mori-miko": {
    label: "Mori Miko",
    gender: "female",
    source: "Eikanya/Live2d-model",
    model: `${EIKANYA}/galgame%20live2d/Fox%20Hime%20Zero/mori_miko/mori_miko.model3.json`,
    gain: 1.0,
  },
  senko: {
    label: "Senko",
    gender: "female",
    source: "Eikanya/Live2d-model",
    model: `${EIKANYA}/Live2D/Senko_Normals/senko.model3.json`,
    gain: 1.0,
  },
  "old-haru": {
    label: "Old Haru",
    gender: "sample",
    source: "Live2D/CubismWebSamples",
    model: `${OFFICIAL}/Haru/Haru.model3.json`,
    gain: 1.0,
  },
  "old-natori": {
    label: "Old Natori",
    gender: "sample",
    source: "Live2D/CubismWebSamples",
    model: `${OFFICIAL}/Natori/Natori.model3.json`,
    gain: 1.0,
  },
  "old-hiyori": {
    label: "Old Hiyori",
    gender: "sample",
    source: "Live2D/CubismWebSamples",
    model: `${OFFICIAL}/Hiyori/Hiyori.model3.json`,
    gain: 1.0,
  },
  "old-mark": {
    label: "Old Mark",
    gender: "sample",
    source: "Live2D/CubismWebSamples",
    model: `${OFFICIAL}/Mark/Mark.model3.json`,
    gain: 1.0,
  },
};

export const DEFAULT_MODEL_KEYS = {
  angela: "mori-miko",
  neo: "old-natori",
};

export function resolveModelPreset(keyOrUrl, fallbackKey) {
  const key = keyOrUrl || fallbackKey;
  if (MODEL_PRESETS[key]) return { key, ...MODEL_PRESETS[key] };
  if (/^https?:\/\//i.test(key)) {
    return { key: "custom-url", label: "Custom URL", gender: "custom", source: "url", model: key, gain: 1.0 };
  }
  const fallback = MODEL_PRESETS[fallbackKey] || MODEL_PRESETS[DEFAULT_MODEL_KEYS.angela];
  return { key: fallbackKey, ...fallback };
}

export function resolveCharacterModels(params = new URLSearchParams()) {
  const angelaKey = params.get("angela") || params.get("angelaModel") || DEFAULT_MODEL_KEYS.angela;
  const neoKey = params.get("neo") || params.get("neoModel") || DEFAULT_MODEL_KEYS.neo;
  const angela = resolveModelPreset(angelaKey, DEFAULT_MODEL_KEYS.angela);
  const neo = resolveModelPreset(neoKey, DEFAULT_MODEL_KEYS.neo);
  return {
    presets: MODEL_PRESETS,
    selected: { angela, neo },
    models: {
      angela: angela.model,
      neo: neo.model,
    },
    gains: {
      angela: angela.gain,
      neo: neo.gain,
    },
  };
}
