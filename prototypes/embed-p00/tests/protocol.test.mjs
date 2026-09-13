import assert from "node:assert/strict";
import { MAX_MESSAGE_BYTES, PROTOCOL, validateHello, validateRequest, validateTheme } from "../protocol.mjs";

const channel = "A".repeat(32);
assert.equal(validateHello({ protocol: PROTOCOL, channel, kind: "hello" }), true);
assert.equal(validateHello({ protocol: PROTOCOL, channel, kind: "hello", parent_origin: "https://evil.example" }), false);
assert.equal(validateHello({ protocol: PROTOCOL, channel: "short", kind: "hello" }), false);
assert.equal(validateRequest({ protocol: PROTOCOL, channel, id: "r1", kind: "request", method: "point.get", params: { point_id: "s_demo" } }, channel), true);
assert.equal(validateRequest({ protocol: PROTOCOL, channel, id: "r1", kind: "request", method: "point.createIntent", params: {} }, channel), true);
assert.equal(validateRequest({ protocol: PROTOCOL, channel, id: "r1", kind: "request", method: "fetch.anyUrl", params: {} }, channel), false);
assert.equal(validateRequest({ protocol: PROTOCOL, channel, id: "r1", kind: "request", method: "point.get", params: {}, extra: true }, channel), false);
assert.equal(validateRequest({ protocol: PROTOCOL, channel, id: "r1", kind: "request", method: "point.get", params: { text: "x".repeat(MAX_MESSAGE_BYTES) } }, channel), false);
assert.deepEqual(validateTheme({ bg: "#123", accent: "#aabbcc", radius: 16, font: "mono", density: "compact" }), { bg: "#123", accent: "#aabbcc", radius: 16, font: "mono", density: "compact" });
assert.equal(validateTheme({ bg: "url(https://bad.example)" }), null);
assert.equal(validateTheme({ css: "body{display:none}" }), null);
assert.equal(validateTheme({ radius: 17 }), null);
console.log("protocol tests passed");
