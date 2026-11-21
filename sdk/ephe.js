/* The page SDK. One file, served by the mount as ephe.js.
 *
 * A sandboxed document has no authority of its own. It asks the frame that
 * embedded it, and that frame is the only caller of the product API. A page
 * that is not embedded rejects every call.
 */
(function () {
  var CHANNEL = "ephe.sdk";
  var WAIT_MS = 120000;
  var nextId = 1;
  var pending = new Map();
  var listeners = new Set();

  function fail(code, message) {
    var error = new Error(message);
    error.code = code;
    return error;
  }

  function settle(data) {
    var slot = pending.get(data.id);
    if (!slot) return;
    pending.delete(data.id);
    clearTimeout(slot.timer);
    if (data.ok) slot.resolve(data.result);
    else slot.reject(fail(data.code || "sdk_refused", data.message || "refused"));
  }

  window.addEventListener("message", function (event) {
    var data = event.data;
    if (!data || data.channel !== CHANNEL || event.source !== window.parent) return;
    if (data.method === "event") {
      listeners.forEach(function (listener) {
        listener({ event: data.event, data: data.data });
      });
      return;
    }
    if (data.id) settle(data);
  });

  function ask(method, fields) {
    if (window.parent === window) {
      return Promise.reject(fail("sdk_no_host", "this page has no embedding frame"));
    }
    var id = String(nextId++);
    var body = { channel: CHANNEL, id: id, method: method };
    if (fields) {
      Object.keys(fields).forEach(function (name) {
        body[name] = fields[name];
      });
    }
    return new Promise(function (resolve, reject) {
      var timer = setTimeout(function () {
        pending.delete(id);
        reject(fail("sdk_timeout", "the host did not answer in time"));
      }, WAIT_MS);
      pending.set(id, { resolve: resolve, reject: reject, timer: timer });
      window.parent.postMessage(body, "*");
    });
  }

  var ephe = {
    storage: {
      get: function (key) {
        return ask("storage.get", { key: key }).then(function (result) {
          return result && result.present ? result.value : null;
        });
      },
      set: function (key, value) {
        return ask("storage.set", { key: key, value: value }).then(function () {
          return undefined;
        });
      },
    },
    callTool: function (name, args) {
      return ask("tool.call", { name: name, arguments: args || {} }).then(function (result) {
        return result && typeof result.result === "string" ? result.result : "";
      });
    },
    subscribe: function (listener) {
      listeners.add(listener);
      return function () {
        listeners.delete(listener);
      };
    },
  };

  globalThis.ephe = ephe;
})();
