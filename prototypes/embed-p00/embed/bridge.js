import { PROTOCOL, validateHello, validateRequest, validateTheme } from "../protocol.mjs";

const registeredParent = "http://127.0.0.1:4273";
const site = { id: "s_demo", welcome_point_id: "s_demo", config_revision: "demo-1" };
const points = {
  s_demo: { id: "s_demo", revision: "v_demo_1", text: "Точка входа демонстрационного сайта." },
  all_sites: { id: "all_sites", revision: "v_core_1", text: "Все подключённые сайты." },
};

let boundChannel = null;
let boundSource = null;
let boundOrigin = null;

const status = document.querySelector("[data-status]");
const output = document.querySelector("[data-output]");

function post(message) {
  boundSource.postMessage(message, boundOrigin);
}

function error(id, code) {
  post({ protocol: PROTOCOL, channel: boundChannel, id, kind: "error", error: { code } });
}

function result(id, data) {
  post({ protocol: PROTOCOL, channel: boundChannel, id, kind: "result", data });
}

function applyTheme(theme) {
  const safe = validateTheme(theme);
  if (!safe) return false;
  const root = document.documentElement.style;
  for (const key of ["bg", "text", "accent", "panel", "border"]) {
    if (key in safe) root.setProperty(`--${key}`, safe[key]);
  }
  if ("radius" in safe) root.setProperty("--radius", `${safe.radius}px`);
  if ("font" in safe) root.setProperty("--font", safe.font === "mono" ? "ui-monospace, monospace" : safe.font === "serif" ? "ui-serif, serif" : "system-ui, sans-serif");
  if ("density" in safe) document.body.dataset.density = safe.density;
  return true;
}

function handleRequest(message) {
  if (message.method.endsWith("Intent")) {
    error(message.id, "AUTH_CONFIRMATION_REQUIRED");
    return;
  }
  switch (message.method) {
    case "site.get":
      result(message.id, site);
      return;
    case "point.get": {
      const point = points[message.params.point_id];
      if (!point) error(message.id, "POINT_NOT_FOUND");
      else result(message.id, point);
      return;
    }
    case "capabilities.get":
      result(message.id, { read: true, writes: "trusted-confirmation-required", parent_credentials: false });
      return;
    case "theme.set":
      if (!applyTheme(message.params.theme)) error(message.id, "INVALID_THEME");
      else result(message.id, { applied: true });
      return;
    case "navigate": {
      const point = points[message.params.point_id];
      if (!point) error(message.id, "POINT_NOT_FOUND");
      else {
        output.textContent = `${point.id}: ${point.text}`;
        result(message.id, { point_id: point.id });
      }
      return;
    }
    default:
      error(message.id, "METHOD_NOT_ALLOWED");
  }
}

window.addEventListener("message", (event) => {
  if (event.origin !== registeredParent || event.source !== window.parent) return;
  if (!boundChannel) {
    if (!validateHello(event.data)) return;
    boundChannel = event.data.channel;
    boundSource = event.source;
    boundOrigin = event.origin;
    status.textContent = "Bridge connected to the registered parent.";
    post({ protocol: PROTOCOL, channel: boundChannel, kind: "ready", capabilities: ["site.get", "point.get", "theme.set", "navigate"], config_revision: site.config_revision });
    return;
  }
  if (event.source !== boundSource || event.origin !== boundOrigin || !validateRequest(event.data, boundChannel)) return;
  handleRequest(event.data);
});

window.addEventListener("beforeunload", () => {
  boundChannel = null;
  boundSource = null;
  boundOrigin = null;
});
