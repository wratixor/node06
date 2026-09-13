export const PROTOCOL = "node06-embed/1";
export const MAX_MESSAGE_BYTES = 64 * 1024;
export const ALLOWED_METHODS = new Set([
  "site.get",
  "point.get",
  "theme.set",
  "navigate",
  "capabilities.get",
  "point.createIntent",
  "point.editIntent",
  "reaction.setIntent",
  "reaction.clearIntent",
  "trust.setIntent",
]);

const COLOR = /^(#[0-9a-fA-F]{6}|#[0-9a-fA-F]{3})$/;
const CHANNEL = /^[A-Za-z0-9_-]{22,128}$/;
const REQUEST_ID = /^[A-Za-z0-9_-]{1,128}$/;

export function isPlainRecord(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value)
    && Object.getPrototypeOf(value) === Object.prototype;
}

export function encodedSize(value) {
  try {
    return new TextEncoder().encode(JSON.stringify(value)).byteLength;
  } catch {
    return Infinity;
  }
}

function exactKeys(value, keys) {
  const actual = Object.keys(value).sort();
  const expected = [...keys].sort();
  return actual.length === expected.length && actual.every((key, index) => key === expected[index]);
}

export function validateHello(message) {
  if (!isPlainRecord(message) || encodedSize(message) > MAX_MESSAGE_BYTES) return false;
  return exactKeys(message, ["protocol", "channel", "kind"])
    && message.protocol === PROTOCOL
    && message.kind === "hello"
    && typeof message.channel === "string"
    && CHANNEL.test(message.channel);
}

export function validateRequest(message, channel) {
  if (!isPlainRecord(message) || encodedSize(message) > MAX_MESSAGE_BYTES) return false;
  if (!exactKeys(message, ["protocol", "channel", "id", "kind", "method", "params"])) return false;
  return message.protocol === PROTOCOL
    && message.channel === channel
    && message.kind === "request"
    && typeof message.id === "string"
    && REQUEST_ID.test(message.id)
    && typeof message.method === "string"
    && ALLOWED_METHODS.has(message.method)
    && isPlainRecord(message.params);
}

export function validateTheme(theme) {
  if (!isPlainRecord(theme)) return null;
  const allowed = new Set(["bg", "text", "accent", "panel", "border", "radius", "font", "density"]);
  if (Object.keys(theme).some((key) => !allowed.has(key))) return null;
  const colors = ["bg", "text", "accent", "panel", "border"];
  for (const key of colors) {
    if (key in theme && (typeof theme[key] !== "string" || !COLOR.test(theme[key]))) return null;
  }
  if ("radius" in theme && (!Number.isInteger(theme.radius) || theme.radius < 0 || theme.radius > 16)) return null;
  if ("font" in theme && !["system", "serif", "mono"].includes(theme.font)) return null;
  if ("density" in theme && !["normal", "compact"].includes(theme.density)) return null;
  return theme;
}
