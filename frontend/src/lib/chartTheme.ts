// Palette per the dataviz skill's validated default (references/palette.md).
export function chartColors(dark: boolean) {
  return {
    series1: dark ? "#3987e5" : "#2a78d6", // blue - purchases / primary magnitude
    series2: dark ? "#d95926" : "#eb6834", // orange - sales
    series3: dark ? "#9085e9" : "#4a3aa7", // violet - independent
    partyD: dark ? "#3987e5" : "#2a78d6",
    partyR: dark ? "#e66767" : "#e34948",
    partyI: dark ? "#9085e9" : "#4a3aa7",
    grid: dark ? "#2c2c2a" : "#e1e0d9",
    axis: dark ? "#383835" : "#c3c2b7",
    textMuted: "#898781",
    textSecondary: dark ? "#c3c2b7" : "#52514e",
    surface: dark ? "#1a1a19" : "#fcfcfb",
  };
}
