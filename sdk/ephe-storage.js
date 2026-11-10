/* The page-storage shim for a mounted plugin surface.
 *
 * A surface document is served with `sandbox allow-scripts allow-popups`, so its
 * origin is opaque and the engine throws a `SecurityError` when the document so
 * much as reads `window.localStorage`. This file gives a bundle that was written
 * against the Storage API the API it expects, and sends its writes over the page
 * SDK's own channel (`ephe.sdk`) to the shell that framed it. The shell writes
 * them into that plugin's state root and no other bundle's.
 *
 * Reads are synchronous because the mount writes a snapshot of the bundle's store
 * into the document immediately ahead of this script. A write updates that view at
 * once and travels to the shell in the background, so a read straight after a
 * write returns the written value. If the shell refuses or does not answer, the
 * key goes back to its last confirmed value, an `ephestorageerror` event is
 * dispatched, and the next call that touches the key throws an `EpheStorageError`
 * carrying the code of the failure. Nothing is ever silently wrong.
 *
 * What this does not emulate: named-property access (`localStorage.theme`),
 * `for...in`, `JSON.stringify(localStorage)`, the cross-document `storage` event,
 * and the engine's 5 MiB quota — the page store's own ceiling (8 KiB per value,
 * 64 KiB per bundle, `core/plugin_state.py`) is enforced by the shell and arrives
 * as a refused write. `sessionStorage` is a memory area for this document: the
 * sandbox gives every document a fresh opaque origin, so a session area would not
 * have survived a reload anyway.
 *
 * The full contract, including the list above, is stated for plugin authors in
 * `docs/PLUGIN_SDK.md` §3c.
 */
(function (global) {
  "use strict";

  var CHANNEL = "ephe.sdk";
  var SNAPSHOT_ID = "ephe-storage-snapshot";
  var WAIT_MS = 120000;

  /* The key grammar of the page store (`core/plugin_state.py: _CLIENT_KEY`), not
   * the wider grammar `localStorage` itself allows: a key outside it can never
   * reach the state root, so the shim refuses it where the bundle can catch it. */
  var KEY = /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/;

  function failure(code, message, cause) {
    var error = new Error(message);
    error.name = "EpheStorageError";
    error.code = code;
    if (cause !== undefined) error.cause = cause;
    return error;
  }

  function codify(error, code) {
    if (error && error.name === "EpheStorageError") return error;
    return failure(code, (error && error.message) || "the storage bridge failed", error);
  }

  /* The engine's own storage, when the document has one. Reading the property is
   * exactly what throws in a sandbox, so the probe is the try. */
  function working(kind) {
    try {
      var area = global[kind];
      if (!area) return null;
      if (typeof area.getItem !== "function" || typeof area.setItem !== "function") return null;
      void area.length;
      return area;
    } catch (error) {
      return null;
    }
  }

  /* The snapshot the mount wrote into the document. A missing or unreadable
   * element is not "an empty store": the shim refuses to guess and every call
   * throws `storage_unavailable`, because an empty view over a store that has
   * entries is the silent wrong answer this whole file exists to avoid. */
  function snapshotView() {
    if (typeof document === "undefined") return null;
    var node = document.getElementById(SNAPSHOT_ID);
    if (!node) return null;
    try {
      var parsed = JSON.parse(node.textContent || "{}");
      return parsed && typeof parsed === "object" ? parsed : null;
    } catch (error) {
      return null;
    }
  }

  function announce(key, error) {
    if (typeof global.dispatchEvent !== "function" || typeof global.CustomEvent !== "function") {
      return;
    }
    try {
      global.dispatchEvent(
        new global.CustomEvent("ephestorageerror", {
          detail: { key: key, code: error.code, message: error.message },
        }),
      );
    } catch (ignored) {
      // A host object that refuses a CustomEvent is not a reason to lose the write.
    }
  }

  /* One `ephe.sdk` request/answer exchange, the same protocol `sdk/ephe.js` speaks.
   * Kept here rather than required from `ephe.js`, because a bundle that never
   * loaded the SDK still reaches for `localStorage`. */
  function channel() {
    var next = 1;
    var pending = new Map();

    global.addEventListener("message", function (event) {
      var data = event.data;
      if (!data || data.channel !== CHANNEL || !data.id) return;
      if (event.source !== global.parent) return;
      var slot = pending.get(data.id);
      if (!slot) return;
      pending.delete(data.id);
      clearTimeout(slot.timer);
      if (data.ok) slot.resolve(data.result);
      else {
        slot.reject(
          failure("storage_refused", data.message || "the host refused the storage write", data.code),
        );
      }
    });

    return function send(method, fields) {
      if (global.parent === global) {
        return Promise.reject(
          failure("storage_no_host", "this page is not embedded, so there is no host to keep its storage"),
        );
      }
      var id = String(next++);
      var body = { channel: CHANNEL, id: id, method: method };
      Object.keys(fields || {}).forEach(function (name) {
        body[name] = fields[name];
      });
      return new Promise(function (resolve, reject) {
        var timer = setTimeout(function () {
          pending.delete(id);
          reject(
            failure("storage_timeout", "the host did not answer the storage write within " + WAIT_MS + " ms"),
          );
        }, WAIT_MS);
        pending.set(id, { resolve: resolve, reject: reject, timer: timer });
        global.parent.postMessage(body, "*");
      });
    };
  }

  /* A Storage-shaped area. `confirmed` is what the shell is believed to hold,
   * `known` is what this document shows (the confirmed view plus its own writes),
   * and `failed` remembers a key whose last write did not land. */
  function createStore(spec) {
    spec = spec || {};
    var snapshot = spec.snapshot === undefined ? null : spec.snapshot;
    var send = spec.send || null;
    var persistent = spec.persistent !== false;
    var ready = snapshot !== null;
    var confirmed = new Map();
    var known = new Map();
    var failed = new Map();
    var pending = new Map();
    var queue = Promise.resolve();
    var sequence = 0;

    if (ready) {
      Object.keys(snapshot).forEach(function (key) {
        if (!KEY.test(key)) return;
        var value = snapshot[key];
        var text = typeof value === "string" ? value : JSON.stringify(value);
        confirmed.set(key, text);
        known.set(key, text);
      });
    }

    function ensureReady() {
      if (!ready) {
        throw failure(
          "storage_unavailable",
          "the mount delivered no page-storage snapshot, so a read here could be wrong",
        );
      }
    }

    function refuseFailed(key) {
      var error = failed.get(key);
      if (error) throw error;
    }

    /* The view: what the shell confirmed, under the latest write this document
     * has queued for the key. Keeping the two layers apart is what lets one
     * failed write revert its own key without dropping a newer write to another
     * key that has not landed yet. */
    function show(key) {
      var queued = pending.get(key);
      if (queued) {
        if (queued.value === null) known.delete(key);
        else known.set(key, queued.value);
        return;
      }
      if (confirmed.has(key)) known.set(key, confirmed.get(key));
      else known.delete(key);
    }

    /* One queued write landed or was refused. `id` is the write's own sequence
     * number: a newer write for the same key has already replaced the pending
     * entry, and its value is the one the view must keep showing. */
    function settle(key, value, id, error) {
      var queued = pending.get(key);
      var latest = Boolean(queued && queued.id === id);
      if (latest) pending.delete(key);
      if (error) {
        failed.set(key, error);
        if (latest) show(key);
        announce(key, error);
        return;
      }
      if (value === null) confirmed.delete(key);
      else confirmed.set(key, value);
      failed.delete(key);
      if (latest) show(key);
    }

    function write(key, value) {
      if (!persistent) {
        if (value === null) confirmed.delete(key);
        else confirmed.set(key, value);
        failed.delete(key);
        if (value === null) known.delete(key);
        else known.set(key, value);
        return;
      }
      var id = ++sequence;
      pending.set(key, { value: value, id: id });
      show(key);
      queue = queue.then(function () {
        return Promise.resolve()
          .then(function () {
            return send("storage.set", { key: key, value: value });
          })
          .then(
            function () {
              settle(key, value, id, null);
            },
            function (error) {
              settle(key, value, id, codify(error, "storage_write_failed"));
            },
          );
      });
    }

    function keyName(raw) {
      var key = String(raw);
      if (!KEY.test(key)) {
        throw failure(
          "storage_key_invalid",
          "a page-storage key is 1-64 characters from A-Z a-z 0-9 . _ -, starting with a letter or digit",
        );
      }
      return key;
    }

    var area = {
      getItem: function (raw) {
        ensureReady();
        var key = keyName(raw);
        refuseFailed(key);
        return known.has(key) ? known.get(key) : null;
      },
      setItem: function (raw, value) {
        ensureReady();
        var key = keyName(raw);
        var text = String(value);
        write(key, text);
      },
      removeItem: function (raw) {
        ensureReady();
        var key = keyName(raw);
        write(key, null);
      },
      clear: function () {
        ensureReady();
        if (!persistent) {
          known.clear();
          confirmed.clear();
          failed.clear();
          pending.clear();
          return;
        }
        var names = new Set();
        known.forEach(function (_value, key) {
          names.add(key);
        });
        names.forEach(function (key) {
          write(key, null);
        });
      },
      key: function (index) {
        ensureReady();
        var position = Number(index);
        if (!isFinite(position) || position < 0) return null;
        var names = Array.from(known.keys());
        return position < names.length ? names[position] : null;
      },
    };

    Object.defineProperty(area, "length", {
      enumerable: true,
      get: function () {
        ensureReady();
        return known.size;
      },
    });

    return area;
  }

  function define(name, area) {
    try {
      Object.defineProperty(global, name, {
        configurable: true,
        enumerable: true,
        get: function () {
          return area;
        },
      });
      return;
    } catch (error) {
      // Older engines keep the property on the prototype; assignment is the fallback.
    }
    try {
      global[name] = area;
    } catch (ignored) {
      // Nothing left to try: the native error stays visible to the bundle.
    }
  }

  /* Install only where the engine refuses the native area: a native window has a
   * working `localStorage`, and a shim there would be a downgrade. `force` and a
   * named `send` exist for the unit test, which has no sandbox to reproduce. */
  function install(options) {
    options = options || {};
    var forced = options.force === true;
    if (forced || !working("localStorage")) {
      var snapshot = options.snapshot !== undefined ? options.snapshot : snapshotView();
      define(
        "localStorage",
        createStore({
          snapshot: snapshot,
          send: options.send || channel(),
          persistent: true,
        }),
      );
    }
    if (forced || !working("sessionStorage")) {
      define(
        "sessionStorage",
        createStore({
          snapshot: options.sessionSnapshot !== undefined ? options.sessionSnapshot : {},
          persistent: false,
        }),
      );
    }
  }

  try {
    global.EpheStorageShim = { install: install, createStore: createStore, failure: failure };
  } catch (ignored) {
    // A page is free to have made `globalThis` non-extensible; the area below still installs.
  }

  install();
})(globalThis);
