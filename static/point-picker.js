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
  const header = document.querySelector(".site-header");
  const form = element("form", "", header.querySelector("nav"));
  form.className = "point-search";
  form.setAttribute("role", "search");
  const input = element("input", "", form);
  input.id = "point-picker-query";
  input.type = "search";
  input.maxLength = 128;
  input.autocomplete = "off";
  input.placeholder = "Поиск / Search";
  input.setAttribute("aria-label", "Поиск точек / Search points");
  input.setAttribute("aria-controls", "point-picker");
  input.setAttribute("aria-expanded", "false");
  const submit = element("button", "", form);
  submit.id = "point-picker-open";
  submit.type = "submit";
  submit.setAttribute("aria-label", "Найти / Search");
  submit.title = "Найти / Search";
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  const circle = document.createElementNS(svg.namespaceURI, "circle");
  circle.setAttribute("cx", "10.5"); circle.setAttribute("cy", "10.5"); circle.setAttribute("r", "6.5");
  const line = document.createElementNS(svg.namespaceURI, "path");
  line.setAttribute("d", "m16 16 5 5");
  svg.append(circle, line); submit.append(svg);
  const panel = element("section", "", body);
  panel.id = "point-picker";
  panel.hidden = true;
  panel.setAttribute("role", "region");
  panel.setAttribute("aria-labelledby", "point-picker-title");
  const heading = element("div", "", panel);
  heading.className = "picker-heading";
  element("h2", "Результаты / Results", heading).id = "point-picker-title";
  const close = button("×", heading);
  close.setAttribute("aria-label", "Закрыть результаты / Close results");
  const status = element("p", "", panel);
  status.id = "point-picker-status";
  status.setAttribute("role", "status");
  const detail = element("section", "", panel);
  detail.id = "point-picker-detail";
  detail.hidden = true;
  detail.tabIndex = -1;
  const results = element("ul", "", panel);
  results.id = "point-picker-results";
  const more = button("Ещё / More", panel);
  more.id = "point-picker-more";
  more.hidden = true;
  let transportPromise, bridge, transportConfig;
  let generation = 0, detailGeneration = 0, debounce, cursor = null, query = "";
  let seen = new Set(), selected = null, onSelect = null, defaultSelection = null;
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
      if (current !== detailGeneration || panel.hidden) return;
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
      const community = element("a", "Поддержка / Versions", actions);
      const communityUrl = new URL("/community/", transportConfig?.serviceOrigin || body.dataset.managementOrigin || location.origin);
      communityUrl.search = new URLSearchParams({ p: point.id });
      community.href = communityUrl.href; community.target = "_blank"; community.rel = "noopener noreferrer";
      const related = element("a", "Добавить связанную точку / Add related point", actions);
      const relatedUrl = new URL("/editor/", transportConfig?.serviceOrigin || body.dataset.managementOrigin || location.origin);
      relatedUrl.search = new URLSearchParams({ from: point.id });
      related.href = relatedUrl.href; related.target = "_blank"; related.rel = "noopener noreferrer";
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
        closePanel();
        callback(value);
      });
      panel.scrollTop = 0;
      detail.focus({ preventScroll: true });
    } catch (error) { if (current === detailGeneration && !panel.hidden) detail.textContent = failure(error); }
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
    if (!value) {
      if (onSelect) { openPanel(); status.textContent = "Введите слово / Enter a word."; }
      else closePanel();
      input.focus(); return;
    }
    openPanel();
    status.textContent = "Поиск / Searching…";
    try {
      const page = await request("points.searchPage", { query, after: append ? cursor : "", limit: 10 });
      if (current !== generation || panel.hidden) return;
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
      if (current === generation && !panel.hidden) {
        status.textContent = failure(error);
        more.hidden = !(append && cursor);
      }
    }
  }
  function positionPanel() {
    if (panel.hidden) return;
    const anchor = form.getBoundingClientRect();
    const width = panel.getBoundingClientRect().width;
    const left = Math.max(12, Math.min(anchor.left, innerWidth - width - 12));
    const top = Math.max(8, Math.min(anchor.bottom + 8, innerHeight - 120));
    panel.style.left = `${left}px`;
    panel.style.top = `${top}px`;
    panel.style.maxHeight = `${Math.min(innerHeight * .65, innerHeight - top - 12)}px`;
  }
  function openPanel() {
    panel.hidden = false;
    positionPanel();
    input.setAttribute("aria-expanded", "true");
  }
  function closePanel(focus = false) {
    panel.hidden = true;
    input.setAttribute("aria-expanded", "false");
    ++generation; ++detailGeneration;
    clearTimeout(debounce); onSelect = defaultSelection;
    if (focus) input.focus();
  }
  window.setNode06PickerSelection = callback => {
    defaultSelection = typeof callback === "function" ? callback : null;
    onSelect = defaultSelection;
  };
  window.openNode06Picker = (options = {}) => {
    onSelect = typeof options.onSelect === "function" ? options.onSelect : defaultSelection;
    // Details must be re-read for every editor selection.
    ++detailGeneration; selected = null; detail.hidden = true;
    openPanel(); input.focus(); form.scrollIntoView({ block: "start", behavior: "instant" }); positionPanel();
    if (input.value.trim()) search();
    else status.textContent = "Введите слово / Enter a word.";
  };
  close.addEventListener("click", () => closePanel(true));
  document.addEventListener("keydown", event => {
    if (event.key === "Escape" && !panel.hidden) {
      event.preventDefault(); event.stopImmediatePropagation(); closePanel(true);
    }
  });
  document.addEventListener("pointerdown", event => {
    if (!panel.hidden && !panel.contains(event.target) && !form.contains(event.target)) closePanel();
  });
  document.addEventListener("focusin", event => {
    if (!panel.hidden && !panel.contains(event.target) && !form.contains(event.target)) closePanel();
  });
  form.addEventListener("submit", event => { event.preventDefault(); search(); });
  input.addEventListener("input", () => {
    ++generation; ++detailGeneration; selected = null; detail.hidden = true; more.hidden = true;
    clearTimeout(debounce);
    if (!input.value.trim()) {
      results.replaceChildren();
      if (onSelect) { openPanel(); status.textContent = "Введите слово / Enter a word."; }
      else { closePanel(); status.textContent = ""; }
      return;
    }
    openPanel();
    debounce = setTimeout(() => search(), 350);
  });
  input.addEventListener("focus", () => {
    if (input.value.trim() && panel.hidden) { openPanel(); search(); }
  });
  input.addEventListener("keydown", event => {
    if (event.key === "ArrowDown" && !panel.hidden) {
      const first = results.querySelector("button");
      if (first) { event.preventDefault(); event.stopPropagation(); first.focus(); }
    }
  });
  more.addEventListener("click", () => search(true));
  window.addEventListener("resize", positionPanel);
  window.addEventListener("scroll", positionPanel, { passive: true });
  window.addEventListener("pagehide", () => bridge?.close());
})();
