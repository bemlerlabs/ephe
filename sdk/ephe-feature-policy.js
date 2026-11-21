/* The surface feature policy: what a mounted plugin document may reach.
 *
 * A mount declares its capabilities in the manifest. The route writes the
 * declared set into the document as a JSON block and the shell writes the same
 * set into the webview before its first script runs; this file is the one place
 * that turns a missing name into an absent API. WebGL contexts, WebAssembly and
 * audio output are removed from a document that did not declare them, and left
 * alone for one that did.
 *
 * The script runs twice in the native window — once as the shell's
 * initialization script and once as the route's injected script — so it is
 * idempotent: the first application wins and the second is a no-op.
 */
(function (global) {
  "use strict";
  if (global.__EPHE_FEATURE_POLICY_APPLIED__) return;
  global.__EPHE_FEATURE_POLICY_APPLIED__ = true;

  var policy = global.__EPHE_FEATURE_POLICY__;
  if (!policy) {
    var element = global.document && global.document.getElementById("ephe-feature-policy");
    try {
      policy = element ? JSON.parse(element.textContent || "{}") : {};
    } catch (error) {
      policy = {};
    }
  }

  function declared(name) {
    return policy[name] === true;
  }

  function remove(name) {
    try {
      delete global[name];
    } catch (error) {
      try {
        global[name] = undefined;
      } catch (inner) {}
    }
  }

  if (!declared("webgl")) {
    var blocked = { webgl: 1, webgl2: 1, "experimental-webgl": 1 };
    var prototypes = [];
    if (global.HTMLCanvasElement) prototypes.push(global.HTMLCanvasElement.prototype);
    if (global.OffscreenCanvas) prototypes.push(global.OffscreenCanvas.prototype);
    prototypes.forEach(function (prototype) {
      if (!prototype || !prototype.getContext) return;
      var original = prototype.getContext;
      prototype.getContext = function (kind) {
        if (blocked[String(kind).toLowerCase()]) return null;
        return original.apply(this, arguments);
      };
    });
    remove("WebGLRenderingContext");
    remove("WebGL2RenderingContext");
  }

  if (!declared("wasm")) remove("WebAssembly");

  if (!declared("audio-out")) {
    remove("AudioContext");
    remove("webkitAudioContext");
    if (global.HTMLMediaElement && global.HTMLMediaElement.prototype) {
      global.HTMLMediaElement.prototype.play = function () {
        return Promise.reject(new Error("audio-out is not declared"));
      };
    }
  }
})(typeof window !== "undefined" ? window : this);
