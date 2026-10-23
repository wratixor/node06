/* Shared public point picker. No sessions, votes or writes. */
"use strict";
(() => {
  if (document.body.dataset.page !== "field" && document.body.dataset.pointPicker !== "true") return;
  const body = document.body;
  const idPattern = /^[a-z0-9][a-z0-9_-]{0,95}$/;
  function element(tag, text, parent) {
    const node = document.createElement(tag);
    if (text) node.textContent = text;
    if (parent) parent.append(node);
    return node;
  }
  function button(text, parent) {
    const node = element("button", text, parent);
    node.type = "button";
    return node;
  }
  const launch = button("ПОИСК / SEARCH", document.querySelector(".site-header nav"));
  launch.id = "point-picker-open";
  const dialog = element("dialog", "", body);
  dialog.id = "point-picker";
  dialog.setAttribute("aria-labelledby", "point-picker-title");
  const heading = element("div", "", dialog);
  heading.className = "picker-heading";
  element("h2", "Точки / Points", heading).id = "point-picker-title";
  const close = button("Закрыть / Close", heading);
  const form = element("form", "", dialog);
  form.className = "picker-form";
  const label = element("label", "Слово или смысл / Word or meaning", form);
  label.htmlFor = "point-picker-query";
  const input = element("input", "", form);
  input.id = "point-picker-query";
  input.type = "search";
  input.maxLength = 128;
  input.autocomplete = "off";
  const submit = element("button", "Найти / Search", form);
  submit.type = "submit";
  const status = element("p", "", dialog);
  status.id = "point-picker-status";
  status.setAttribute("role", "status");
  const results = element("ul", "", dialog);
  results.id = "point-picker-results";
  const more = button("Ещё / More", dialog);
  more.id = "point-picker-more";
  more.hidden = true;
  const detail = element("section", "", dialog);
  detail.id = "point-picker-detail";
  detail.hidden = true;
  detail.tabIndex = -1;
  dialog.insertBefore(detail, results);
  let transportPromise, bridge, transportConfig;
  let generation = 0, detailGeneration = 0, debounce, cursor = null, query = "";
  let seen = new Set(), selected = null, onSelect = null;
  const errors = {
    POINT_NOT_FOUND: "Точка больше недоступна / Point unavailable.",
    INVALID_SEARCH_QUERY: "Не более 8 слов / Use at most 8 words.",
    METHOD_NOT_ALLOWED: "Сервер ещё не поддерживает этот поиск / Server update required.",
    INVALID_CONFIG: "Проверьте настройки подключения / Check connection settings.",
    BRIDGE_CLOSED: "Соединение закрыто. Повторите поиск / Connection closed. Retry search.",
  };
  function failure(error) {
    return errors[error.message] || "Поиск недоступен. Повторите попытку / Search unavailable. Please retry.";
  }
  async function read(url) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 10000);
    try {
      const response = await fetch(url, { credentials: "omit", cache: "no-store", signal: controller.signal });
      const value = await response.json();
      if (!response.ok) throw new Error(value.code || "READ_FAILED");
      return value;
    } finally { clearTimeout(timeout); }
  }
  async function transport() {
    if (transportPromise) return transportPromise;
    transportPromise = (async () => {
      if (body.dataset.hosted === "true") {
        const site = body.dataset.searchSite;
        if (site && !/^s_[0-9a-f]{32}$/.test(site)) throw new Error("INVALID_CONFIG");
        return (method, params) => {
          if (site) return read(`/bridge/v1/${site}/read?${new URLSearchParams({ method, ...params })}`);
          if (method === "points.searchPage") {
            const { query: q, ...page } = params;
            return read(`/api/v1/points/search?${new URLSearchParams({ q, ...page })}`);
          }
          return read(`/api/v1/points/${encodeURIComponent(params.point_id)}`);
        };
      }
      const config = await read("/assets/connection.json");
      if (!config || Object.keys(config).sort().join() !== "embedOrigin,serviceOrigin,siteId"
        || !/^s_[0-9a-f]{32}$/.test(config.siteId)) throw new Error("INVALID_CONFIG");
      for (const key of ["embedOrigin", "serviceOrigin"]) {
        const url = new URL(config[key]);
        if (url.protocol !== "https:" || url.origin !== config[key]) throw new Error("INVALID_CONFIG");
      }
      transportConfig = config;
      bridge = await window.connectNode06(config);
      const capabilities = await bridge.request("capabilities.get");
      if (!["points.searchPage", "point.read"].every(method => capabilities.methods.includes(method)))
        throw new Error("METHOD_NOT_ALLOWED");
      return (method, params) => bridge.request(method, params);
    })().catch(error => {
      bridge?.close(); bridge = null; transportPromise = null;
      throw error;
    });
    return transportPromise;
  }
  async function request(method, params) {
    try { return await (await transport())(method, params); }
    catch (error) {
      if (["BRIDGE_CLOSED", "TIMEOUT", "NETWORK_ERROR"].includes(error.message)) {
        bridge?.close(); bridge = null; transportPromise = null;
      }
      throw error;
    }
  }
  function href(id) {
    if (transportConfig) {
      const url = new URL(`/sites/${transportConfig.siteId}/`, transportConfig.serviceOrigin);
      url.search = new URLSearchParams({ p: id, open: id });
      return url.href;
    }
    const url = new URL(body.dataset.fieldPath || "/", location.origin);
    url.search = new URLSearchParams({ p: id, open: id });
    return url.href;
  }
  async function showPoint(id) {
    const current = ++detailGeneration;
    selected = null;
    detail.hidden = false;
    detail.textContent = "Загрузка / Loading…";
    try {
      const point = await request("point.read", { point_id: id });
      if (current !== detailGeneration || !dialog.open) return;
      selected = { id: point.id, lang: point.lang, revision_id: point.revision_id,
        content_digest: point.content_digest, preview: point.preview, href: href(point.id) };
      detail.replaceChildren();
      element("h3", `${point.id} · ${point.lang}`, detail);
      // Never insert server-provided HTML in the parent page.
      element("p", point.body ?? point.preview, detail).className = "picker-body";
      const actions = element("div", "", detail);
      actions.className = "picker-actions";
      const open = element("a", "Открыть / Open", actions);
      open.href = selected.href;
      if (transportConfig) { open.target = "_blank"; open.rel = "noopener"; }
      const address = element("input", "", detail);
      address.value = selected.href;
      address.readOnly = true;
      address.setAttribute("aria-label", "Адрес точки / Point address");
      button("Копировать адрес / Copy address", actions).addEventListener("click", async () => {
        try {
          await navigator.clipboard.writeText(address.value);
          status.textContent = "Адрес скопирован / Address copied.";
        } catch {
          address.focus(); address.select();
          status.textContent = "Скопируйте выделенный адрес / Copy the selected address.";
        }
      });
      if (onSelect) button("Выбрать / Select", actions).addEventListener("click", () => {
        if (!selected) return;
        const value = { ...selected };
        const callback = onSelect;
        dialog.close();
        callback(value);
      });
      detail.scrollIntoView({ block: "start" });
      detail.focus({ preventScroll: true });
    } catch (error) { if (current === detailGeneration && dialog.open) detail.textContent = failure(error); }
  }
  async function search(append = false) {
    clearTimeout(debounce);
    const value = input.value.trim();
    const current = ++generation;
    if (!append) {
      ++detailGeneration; selected = null; detail.hidden = true;
      results.replaceChildren(); seen = new Set(); cursor = null; query = value;
    }
    more.hidden = true;
    if (!value) { status.textContent = "Введите слово / Enter a word."; return; }
    status.textContent = "Поиск / Searching…";
    try {
      const page = await request("points.searchPage", { query, after: append ? cursor : "", limit: 10 });
      if (current !== generation || !dialog.open) return;
      for (const point of page.items) {
        if (!idPattern.test(point.id) || seen.has(point.id) || seen.size >= 50) continue;
        seen.add(point.id);
        const item = element("li", "", results);
        const select = button(`${point.id} · ${point.lang}`, item);
        select.addEventListener("click", () => showPoint(point.id));
        element("p", point.preview, item);
      }
      cursor = page.next_cursor;
      more.hidden = !cursor || seen.size >= 50;
      status.textContent = seen.size ? `${seen.size} · ${cursor && seen.size >= 50
        ? "Уточните запрос / Refine the query" : "Найдено / Found"}` : "Ничего не найдено / No matches.";
    } catch (error) {
      if (current === generation && dialog.open) {
        status.textContent = failure(error);
        more.hidden = !(append && cursor);
      }
    }
  }
  window.openNode06Picker = (options = {}) => {
    onSelect = typeof options.onSelect === "function" ? options.onSelect : null;
    if (!dialog.open) dialog.showModal();
    input.focus();
    // Details must be re-read to capture a current revision for each selection.
    ++detailGeneration; selected = null; detail.hidden = true;
  };
  launch.addEventListener("click", () => window.openNode06Picker());
  close.addEventListener("click", () => dialog.close());
  dialog.addEventListener("keydown", event => {
    if (event.key === "Escape") {
      event.preventDefault(); event.stopPropagation(); dialog.close();
    }
  });
  dialog.addEventListener("close", () => { ++generation; ++detailGeneration; clearTimeout(debounce); onSelect = null; });
  form.addEventListener("submit", event => { event.preventDefault(); search(); });
  input.addEventListener("input", () => {
    ++generation; ++detailGeneration; selected = null; detail.hidden = true; more.hidden = true;
    clearTimeout(debounce); debounce = setTimeout(() => search(), 350);
  });
  more.addEventListener("click", () => search(true));
  window.addEventListener("pagehide", () => bridge?.close());
})();
