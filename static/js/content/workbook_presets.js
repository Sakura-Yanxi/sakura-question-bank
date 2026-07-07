(function () {
  const FALLBACK_RULE = "right_header_strict";
  const DEFAULT_RECOMMENDATION = "wd_tablet_topbar";
  const PRESETS = [
    {
      value: "wd_tablet_topbar",
      label: "一眼题本",
      hint: "平板版顶部页眉",
      matchAny: ["wd", "一眼"],
    },
    {
      value: "right_header_strict",
      label: "做题本集结地",
      hint: "右上页眉",
      matchAny: ["880", "做题本集结地"],
    },
  ];

  function presetForRule(rule, fallback = FALLBACK_RULE) {
    return PRESETS.find((preset) => preset.value === rule) || PRESETS.find((preset) => preset.value === fallback) || PRESETS[0];
  }

  function compactFilename(filename) {
    return String(filename || "").replace(/\s+/g, "").toLowerCase();
  }

  function recommendedForFilename(filename) {
    const compact = compactFilename(filename);
    return PRESETS.find((preset) => preset.matchAny.some((keyword) => compact.includes(keyword))) || presetForRule(DEFAULT_RECOMMENDATION);
  }

  window.SakuraWorkbookPresets = {
    all: () => PRESETS.slice(),
    fallbackRule: FALLBACK_RULE,
    labelFor: (rule) => presetForRule(rule).label,
    normalizeRule: (rule) => presetForRule(rule).value,
    recommendedForFilename,
  };
})();
