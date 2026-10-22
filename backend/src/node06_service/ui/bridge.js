"use strict";
(() => {
  const protocol = "node06-embed/1";
  const methods = ["capabilities.get", "site.get", "point.get", "points.search"];
  const parents = document.body.dataset.parents.split(" ");
  const site = document.body.dataset.site;
  const active = new Set();
  let channel = null;
  let parentOrigin = null;
  const plain = value => value !== null && typeof value === "object"
    && Object.getPrototypeOf(value) === Object.prototype;
  const exact = (value, keys) => plain(value) && Object.keys(value).length === keys.length
    && keys.every(key => Object.hasOwn(value, key));
  const size = value => {
    try { return new TextEncoder().encode(JSON.stringify(value)).length; }
    catch { return Infinity; }
  };
  const send = value => window.parent.postMessage({ protocol, channel, ...value }, parentOrigin);
  const fail = (id, code) => send({ kind: "error", id, error: { code } });
  window.addEventListener("message", async event => {
    if (event.source !== window.parent || !parents.includes(event.origin)) return;
    const message = event.data;
    if (!plain(message) || size(message) > 64 * 1024 || message.protocol !== protocol) return;
    if (exact(message, ["protocol", "channel", "kind"]) && message.kind === "hello"
      && typeof message.channel === "string" && /^[A-Za-z0-9_-]{22,128}$/.test(message.channel)) {
      if (channel && (channel !== message.channel || parentOrigin !== event.origin)) return;
      channel = message.channel;
      parentOrigin = event.origin;
      send({ kind: "ready", capabilities: methods });
      return;
    }
    if (!channel || message.channel !== channel || event.origin !== parentOrigin
      || !exact(message, ["protocol", "channel", "id", "kind", "method", "params"])
      || message.kind !== "request" || typeof message.id !== "string"
      || !/^[A-Za-z0-9_-]{1,128}$/.test(message.id) || !plain(message.params)) return;
    const { id, method, params } = message;
    if (!methods.includes(method)) { fail(id, "METHOD_NOT_ALLOWED"); return; }
    const keys = method === "point.get" ? ["point_id"] : method === "points.search" ? ["query"] : [];
    if (!exact(params, keys) || keys.some(key => typeof params[key] !== "string"
      || params[key].length < 1 || params[key].length > 128)) { fail(id, "INVALID_PARAMS"); return; }
    // Ignore duplicate pending IDs, preserving the original request's single response.
    if (active.has(id)) return;
    if (active.size >= 8) { fail(id, "BUSY"); return; }
    active.add(id);
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 10000);
    try {
      const query = new URLSearchParams({ method, ...params });
      const response = await fetch(`/bridge/v1/${encodeURIComponent(site)}/read?${query}`, {
        credentials: "omit", cache: "no-store", signal: controller.signal,
      });
      const data = await response.json();
      if (size(data) > 255 * 1024) fail(id, "RESPONSE_TOO_LARGE");
      else if (!response.ok) fail(id, data.code || "READ_FAILED");
      else send({ kind: "result", id, data });
    } catch {
      fail(id, controller.signal.aborted ? "TIMEOUT" : "NETWORK_ERROR");
    } finally {
      clearTimeout(timer);
      active.delete(id);
    }
  });
})();
