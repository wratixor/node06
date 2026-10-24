/* Shared public point picker. No sessions, votes or writes. */
"use strict";
(() => {
  if (document.body.dataset.page !== "field" && document.body.dataset.pointPicker !== "true") return;
  const body = document.body;
  const label = (en,ru) => document.documentElement.lang === "ru" ? ru : en;
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
  input.placeholder = label("Search","Поиск");
  input.setAttribute("aria-label", label("Search points","Поиск точек"));
  input.setAttribute("aria-controls", "point-picker");
  input.setAttribute("aria-expanded", "false");
  const submit = element("button", "", form);
  submit.id = "point-picker-open";
  submit.type = "submit";
  submit.setAttribute("aria-label", label("Search","Поиск"));
  submit.title = label("Search","Поиск");
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
  element("h2", label("Results","Результаты"), heading).id = "point-picker-title";
  const close = button("×", heading);
  close.setAttribute("aria-label", label("Close results","Закрыть результаты"));
  const status = element("p", "", panel);
  status.id = "point-picker-status";
  status.setAttribute("role", "status");
  const results = element("ul", "", panel);
  results.id = "point-picker-results";
  const more = button(label("More","Ещё"), panel);
  more.id = "point-picker-more";
  more.hidden = true;
  let transportPromise, bridge, transportConfig;
  let generation = 0, selectionGeneration = 0, debounce, cursor = null, query = "";
  let seen = new Set(), onSelect = null, defaultSelection = null;
  const errors = {
    POINT_NOT_FOUND: label("Point unavailable.","Точка больше недоступна."),
    INVALID_SEARCH_QUERY: label("Use at most 8 words.","Не более 8 слов."),
    METHOD_NOT_ALLOWED: label("Server update required.","Нужно обновить сервер."),
    INVALID_CONFIG: label("Check connection settings.","Проверьте настройки подключения."),
    BRIDGE_CLOSED: label("Connection closed. Retry search.","Соединение закрыто. Повторите поиск."),
  };
  function failure(error) {
    return errors[error.message] || label("Search unavailable. Please retry.","Поиск недоступен. Повторите попытку.");
  }
  async function read(url) {
    if(body.dataset.hosted==='true'&&body.dataset.viewSite&&body.dataset.fieldPath!=='/'&&url.startsWith('/api/v1/')){
      const scoped=new URL(url,location.origin);scoped.searchParams.set('site',body.dataset.viewSite);url=scoped.pathname+scoped.search;
    }
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
          if (method === "points.geometry") return read(`/api/v1/geometry?${new URLSearchParams({ids:params.point_ids.join(",")})}`);
          const suffix = method === "point.social" ? "/social-summary" : method === "point.neighbors" ? "/neighbors" : "";
          return read(`/api/v1/points/${encodeURIComponent(params.point_id)}${suffix}`);
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
  window.node06EditorConnection = async () => {
    await transport();
    return transportConfig || (body.dataset.searchSite ? {
      siteId:body.dataset.searchSite, embedOrigin:location.origin,
      serviceOrigin:body.dataset.managementOrigin,
    } : null);
  };
  window.node06ReturnPath = () => transportConfig ? `/sites/${transportConfig.siteId}/` : body.dataset.searchSite ? `/sites/${body.dataset.searchSite}/` : body.dataset.fieldPath || '/';
  window.node06ManagementOrigin = () => transportConfig?.serviceOrigin || body.dataset.managementOrigin || (body.dataset.hosted === "true" && !body.dataset.searchSite ? location.origin : "");
  window.readNode06Public = (method, params) => {
    if (!["point.read", "points.searchPage", "point.neighbors", "point.social", "points.geometry"].includes(method))
      return Promise.reject(new Error("METHOD_NOT_ALLOWED"));
    return request(method, params);
  };
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
  async function selectTag(id) {
    const current = ++selectionGeneration;
    const callback = onSelect;
    status.textContent = label("Adding tag…","Добавляем тег…");
    try {
      const point = await request("point.read", {point_id:id});
      if(current!==selectionGeneration || panel.hidden || callback!==onSelect)return;
      const pin={id:point.id,lang:point.lang,revision_id:point.revision_id,
        content_digest:point.content_digest,preview:point.preview,href:href(point.id)};
      closePanel();callback(pin);
    } catch(error){if(current===selectionGeneration&&!panel.hidden)status.textContent=failure(error);}
  }
  async function search(append = false) {
    clearTimeout(debounce);
    const value = input.value.trim();
    const current = ++generation;
    if (!append) {
      ++selectionGeneration;
      results.replaceChildren(); seen = new Set(); cursor = null; query = value;
    }
    more.hidden = true;
    if (!value) {
      if (onSelect) { openPanel(); status.textContent = label("Enter a word.","Введите слово."); }
      else closePanel();
      input.focus(); return;
    }
    openPanel();
    status.textContent = label("Searching…","Поиск…");
    try {
      const page = await request("points.searchPage", { query, after: append ? cursor : "", limit: 10 });
      if (current !== generation || panel.hidden) return;
      for (const point of page.items) {
        if (!idPattern.test(point.id) || seen.has(point.id) || seen.size >= 50) continue;
        seen.add(point.id);
        const item = element("li", "", results);
        item.dataset.pointId=point.id;
        const result=element(onSelect?"button":"a","",item);
        element("span",point.preview||point.id,result);
        if(onSelect){result.type="button";result.title=label("Add as tag","Добавить как тег");result.addEventListener("click",()=>selectTag(point.id));}
        else{result.href=href(point.id);result.title=label("Open article","Открыть статью");if(transportConfig){result.target="_blank";result.rel="noopener noreferrer";}}

      }
      cursor = page.next_cursor;
      more.hidden = !cursor || seen.size >= 50;
      status.textContent = seen.size ? `${seen.size} · ${cursor && seen.size >= 50
        ? label("Refine the query","Уточните запрос") : label("Found","Найдено")}` : label("No matches.","Ничего не найдено.");
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
    ++generation; ++selectionGeneration;
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
    ++selectionGeneration;
    openPanel(); input.focus(); form.scrollIntoView({ block: "start", behavior: "instant" }); positionPanel();
    if (input.value.trim()) search();
    else status.textContent = label("Enter a word.","Введите слово.");
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
    ++generation; ++selectionGeneration; more.hidden = true;
    clearTimeout(debounce);
    if (!input.value.trim()) {
      results.replaceChildren();
      if (onSelect) { openPanel(); status.textContent = label("Enter a word.","Введите слово."); }
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
      const first = results.querySelector("a,button");
      if (first) { event.preventDefault(); event.stopPropagation(); first.focus(); }
    }
  });
  more.addEventListener("click", () => search(true));
  window.addEventListener("resize", positionPanel);
  window.addEventListener("scroll", positionPanel, { passive: true });
  window.addEventListener("pagehide", () => bridge?.close());
})();
