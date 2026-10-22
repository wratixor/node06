/* Copy this file to your own static site; no external script permission is needed. */
"use strict";
window.connectNode06 = async function connectNode06({ embedOrigin, siteId }) {
  const origin = new URL(embedOrigin);
  if (origin.origin !== embedOrigin || origin.protocol !== "https:" || !/^s_[0-9a-f]{32}$/.test(siteId))
    throw new Error("INVALID_CONFIG");
  const protocol = "node06-embed/1";
  const frame = document.createElement("iframe");
  frame.hidden = true;
  frame.title = "NODE06 public API bridge";
  frame.referrerPolicy = "no-referrer";
  frame.setAttribute("sandbox", "allow-scripts allow-same-origin");
  const pending = new Map();
  let channel, ready = false, closed = false;
  let resolveReady, rejectReady;
  const boot = new Promise((resolve, reject) => { resolveReady = resolve; rejectReady = reject; });
  const timeout = setTimeout(() => { rejectReady(new Error("BRIDGE_TIMEOUT")); close(); }, 10000);
  function close() {
    if (closed) return;
    closed = true;
    clearTimeout(timeout);
    rejectReady(new Error("BRIDGE_CLOSED"));
    window.removeEventListener("message", receive);
    for (const entry of pending.values()) { clearTimeout(entry.timer); entry.reject(new Error("BRIDGE_CLOSED")); }
    pending.clear();
    frame.remove();
  }
  function receive(event) {
    const m = event.data;
    if (event.source !== frame.contentWindow || event.origin !== embedOrigin || !m
      || m.protocol !== protocol || m.channel !== channel) return;
    if (m.kind === "ready" && !ready) {
      ready = true; clearTimeout(timeout); resolveReady(); return;
    }
    if (!["result", "error"].includes(m.kind) || typeof m.id !== "string") return;
    const entry = pending.get(m.id);
    if (!entry) return;
    clearTimeout(entry.timer); pending.delete(m.id);
    if (m.kind === "result") entry.resolve(m.data);
    else entry.reject(new Error(typeof m.error?.code === "string" ? m.error.code : "READ_FAILED"));
  }
  frame.addEventListener("load", () => {
    // Reloads never silently reattach pending work to another document.
    if (channel) { close(); return; }
    channel = crypto.randomUUID().replaceAll("-", "");
    frame.contentWindow.postMessage({ protocol, channel, kind: "hello" }, embedOrigin);
  });
  window.addEventListener("message", receive);
  frame.src = `${embedOrigin}/bridge/v1/${siteId}/`;
  document.body.append(frame);
  await boot;
  return { frame, close, request(method, params = {}) {
    if (closed || !ready) return Promise.reject(new Error("BRIDGE_CLOSED"));
    if (pending.size >= 8) return Promise.reject(new Error("BUSY"));
    const id = crypto.randomUUID().replaceAll("-", "");
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => { pending.delete(id); reject(new Error("TIMEOUT")); }, 11000);
      pending.set(id, { resolve, reject, timer });
      try { frame.contentWindow.postMessage({ protocol, channel, id, kind: "request", method, params }, embedOrigin); }
      catch (error) { clearTimeout(timer); pending.delete(id); reject(error); }
    });
  } };
};
