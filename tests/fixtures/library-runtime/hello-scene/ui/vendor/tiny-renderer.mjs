// The fixture library of tests/test_plugin_libraries.py. A few hundred bytes of real
// ES module standing in for the multi-megabyte engine bundle a scene plugin vendors in
// production, so the declared-hash path runs end to end on bytes this repository owns.
export const RENDERER_VERSION = "0.0.1";

export function clear(canvas) {
  canvas.textContent = "";
  return canvas;
}
