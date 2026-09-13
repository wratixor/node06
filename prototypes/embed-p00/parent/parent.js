import { PROTOCOL } from "../protocol.mjs";

const embedOrigin = "http://localhost:4274";
const frame = document.querySelector("iframe");
const log = document.querySelector("[data-log]");
const state = document.querySelector("[data-state]");
let channel = null;
let serial = 0;
const pending = new Map();

function write(message) {
  log.textContent = `${new Date().toLocaleTimeString()} ${message}\n${log.textContent}`;
}

function freshChannel() {
  const bytes = crypto.getRandomValues(new Uint8Array(24));
  return btoa(String.fromCharCode(...bytes)).replace(/[+/=]/g, "_");
}

function rejectPending(reason) {
  for (const { reject } of pending.values()) reject(new Error(reason));
  pending.clear();
}

function handshake() {
  rejectPending("FRAME_RELOADED");
  channel = freshChannel();
  state.textContent = "Connecting…";
  frame.contentWindow.postMessage({ protocol: PROTOCOL, channel, kind: "hello" }, embedOrigin);
}

function request(method, params) {
  if (!channel) return Promise.reject(new Error("BRIDGE_NOT_READY"));
  const id = `r${++serial}`;
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => { pending.delete(id); reject(new Error("TIMEOUT")); }, 10_000);
    pending.set(id, { resolve, reject, timer });
    frame.contentWindow.postMessage({ protocol: PROTOCOL, channel, id, kind: "request", method, params }, embedOrigin);
  });
}

frame.addEventListener("load", handshake);
window.addEventListener("message", (event) => {
  if (event.origin !== embedOrigin || event.source !== frame.contentWindow || !event.data || event.data.protocol !== PROTOCOL || event.data.channel !== channel) return;
  if (event.data.kind === "ready") {
    state.textContent = "Connected: read-only bridge; no credentials exposed.";
    write("ready accepted from exact iframe origin/source/channel");
    return;
  }
  const entry = pending.get(event.data.id);
  if (!entry) return;
  clearTimeout(entry.timer);
  pending.delete(event.data.id);
  if (event.data.kind === "error") entry.reject(new Error(event.data.error.code));
  else entry.resolve(event.data.data);
});

document.querySelector("[data-point]").addEventListener("click", async () => {
  try { write(JSON.stringify(await request("point.get", { point_id: "s_demo" }))); } catch (error) { write(error.message); }
});
document.querySelector("[data-theme]").addEventListener("click", async () => {
  try { write(JSON.stringify(await request("theme.set", { theme: { bg: "#15202b", accent: "#79d5ff", radius: 12, font: "mono" } }))); } catch (error) { write(error.message); }
});
document.querySelector("[data-bad-theme]").addEventListener("click", async () => {
  try { await request("theme.set", { theme: { bg: "url(https://attacker.invalid/x)" } }); write("unexpected theme acceptance"); } catch (error) { write(`unsafe theme rejected: ${error.message}`); }
});
document.querySelector("[data-write]").addEventListener("click", async () => {
  try { await request("point.createIntent", { body: "not allowed here" }); write("unexpected write acceptance"); } catch (error) { write(`write denied: ${error.message}`); }
});
document.querySelector("[data-reload]").addEventListener("click", () => { frame.src = frame.src; });

fetch("http://localhost:4274/private-api").then(() => write("unexpected cross-origin fetch success")).catch(() => write("parent CSP blocked direct external fetch as expected"));
