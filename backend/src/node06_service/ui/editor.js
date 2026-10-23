"use strict";
(() => {
  const el = id => document.getElementById(id);
  let pid = new URLSearchParams(location.search).get("p"), revision = null, csrf, language = "und";
  const from = new URLSearchParams(location.search).get("from");
  let favorites = new Map();
  let links = new Map(), receipt = null, busy = false, dirty = false, selection, historyCursor, mineCursor;
  const status = text => { el("editor-status").textContent = text; };
  const errors = {
    POINT_REVISION_CHANGED: "Точка уже изменена. Скопируйте свой текст и откройте свежую версию в другой вкладке.",
    TARGET_REVISION_CHANGED: "Одна из связанных точек изменилась. Удалите её из списка и выберите свежую версию через поиск.",
    TARGET_NOT_PUBLIC: "Одна из связанных точек недоступна. Выберите другую.",
    AUTH_REQUIRED: "Войдите через Аккаунт, затем повторите публикацию. Ваш текст здесь сохранён.",
    CSRF_REQUIRED: "Сессия изменилась. Войдите через Аккаунт и повторите публикацию.",
    PROPOSAL_REQUIRED: "У точки есть подписчики: предложите новую версию через раздел Подписки / Versions.",
    FAVORITES_LIMIT: "Можно сохранить до 64 избранных тегов. Уберите ненужные.",
    POINT_EDIT_FORBIDDEN: "Изменять напрямую можно только свою пользовательскую точку.",
    UNDECLARED_POINT_LINK: "В тексте есть смысловая ссылка, которой нет в списке связей. Выберите её через поиск или уберите ссылку.",
    ACCOUNT_CHANGED: "Аккаунт сменился. Войдите в исходный аккаунт, чтобы завершить проверку предыдущей публикации.",
    INVALID_INPUT: "Проверьте текст и число связей (1–16).",
    AUTH_RATE_LIMITED: "Слишком много запросов. Повторите позже.",
  };
  async function api(path, options = {}) {
    const controller = new AbortController(), timer = setTimeout(() => controller.abort(), 15000);
    try {
      const response = await fetch("/api/v1" + path, { ...options, credentials: "same-origin", cache: "no-store", signal: controller.signal });
      const value = await response.json();
      if (!response.ok) { const error = new Error(value.code || "REQUEST_FAILED"); error.definite = response.status < 500; throw error; }
      return value;
    } finally { clearTimeout(timer); }
  }
  function failure(error) { status(errors[error.message] || "Запрос не завершён. Текст сохранён на этой странице; повторите попытку."); }
  function label(pin) {
    const text = (pin.preview || pin.id).split(/\s[—–]\s|\n/)[0].trim();
    return text.length > 40 ? text.slice(0, 37).trimEnd() + "…" : text;
  }
  function renderLinks() {
    el("point-links").replaceChildren();
    for (const pin of links.values()) {
      const li = document.createElement("li"), remove = document.createElement("button");
      const a = document.createElement("a");
      a.textContent = label(pin); a.title = pin.preview || pin.id; a.href = "/?" + new URLSearchParams({ p: pin.id, open: pin.id });
      a.target = "_blank"; a.rel = "noopener noreferrer"; li.append(a);
      remove.type = "button"; remove.textContent = "×";
      remove.setAttribute("aria-label","Убрать связь"); remove.title="Убрать связь";
      remove.disabled = busy || Boolean(receipt);
      remove.addEventListener("click", () => { links.delete(pin.id); receipt = null; dirty = true; renderLinks(); });
      const star = document.createElement("button"); star.type = "button";
      star.textContent = favorites.has(pin.id) ? "★" : "☆";
      star.setAttribute("aria-label",favorites.has(pin.id) ? "★ В избранном" : "☆ Сохранить тег");
      star.title = favorites.has(pin.id) ? "Убрать из избранного" : "Сохранить тег";
      star.disabled = busy || Boolean(receipt);
      star.addEventListener("click", () => saveFavorite(pin.id, !favorites.has(pin.id)));
      li.append(" ", star, remove); el("point-links").append(li);
    }
  }
  function selectPin(pin) {
    if (busy || receipt) return;
    const input = el("point-body");
    if (links.size >= 16 && !links.has(pin.id)) { status("Не больше 16 связей."); return; }
    if (pin.id === pid) { status("Точку нельзя связать с собой."); return; }
    links.set(pin.id, { id: pin.id, preview: pin.preview, revision_id: pin.revision_id, content_digest: pin.content_digest });
    const position = selection || { start: input.selectionStart, end: input.selectionEnd, text: input.value };
    const selected = position.text.slice(position.start, position.end);
    if (selected && input.value === position.text && !/[\[\]\n]/.test(selected)) {
      input.value = position.text.slice(0, position.start) + `[${selected}](md://point/${pin.id})` + position.text.slice(position.end);
      input.setSelectionRange(position.start, position.start);
    }
    selection = null; dirty = true; renderLinks(); input.focus();
  }
  const search = document.querySelector(".point-search");
  el("tag-search").append(search);
  el("point-picker-query").placeholder = "Найти тег / смысл";
  el("point-picker-query").setAttribute("aria-label", "Найти связанную точку / тег");
  window.setNode06PickerSelection(selectPin);
  el("point-body").addEventListener("input", () => {selection = null;});
  el("point-body").addEventListener("select", () => {selection = null;});
  el("link-word").addEventListener("click", () => {
    if (busy || receipt) return;
    const input = el("point-body");
    selection = { start: input.selectionStart, end: input.selectionEnd, text: input.value };
    window.openNode06Picker({ onSelect: selectPin });
  });
  function renderFavorites() {
    el("favorite-tags").replaceChildren();
    el("favorite-wrap").hidden = !favorites.size;
    if (!favorites.size) return;
    for (const pin of favorites.values()) {
      const li = document.createElement("li"), add = document.createElement("button"), remove = document.createElement("button");
      add.type = remove.type = "button";
      add.textContent = "+ " + label(pin); add.title = pin.preview || pin.id; add.disabled = Boolean(pin.unavailable) || busy || Boolean(receipt);
      add.addEventListener("click", async () => {
        if (busy || receipt) return;
        try { const current = await api("/points/" + pin.id); selectPin(current); }
        catch(error) { failure(error); }
      });
      remove.textContent = "×"; remove.setAttribute("aria-label","Убрать из избранного"); remove.title="Убрать из избранного"; remove.disabled = busy || Boolean(receipt);
      remove.addEventListener("click", () => saveFavorite(pin.id, false));
      li.append(add, remove); el("favorite-tags").append(li);
    }
  }
  async function refreshFavorites() {
    const page = await api("/me/favorites"); favorites = new Map(page.items.map(pin => [pin.id, pin]));
    renderFavorites(); renderLinks();
  }
  async function saveFavorite(id, active) {
    if (busy || receipt) return;
    busy = true; renderFavorites(); renderLinks();
    try {
      const me = await api("/me");
      await api("/me/favorites/" + id, {method:"POST", headers:{"Content-Type":"application/json", "X-CSRF-Token":me.csrf_token, "Idempotency-Key":crypto.randomUUID()}, body:JSON.stringify({active})});
      try { await refreshFavorites(); status(active ? "Тег сохранён в аккаунте." : "Тег убран из избранного."); }
      catch(_) { status("Избранное сохранено сервером, но обновить список не удалось. Обновите страницу после сохранения текста."); }
    } catch(error) { failure(error); }
    finally { busy = false; renderFavorites(); renderLinks(); }
  }
  async function history(reset = false) {
    if (reset) { historyCursor = null; el("history").querySelector("ol").replaceChildren(); }
    const page = await api(`/points/${pid}/revisions?` + new URLSearchParams(historyCursor ? { before: historyCursor } : {}));
    for (const row of page.items) {
      const li = document.createElement("li"), summary = document.createElement("summary"), details = document.createElement("details"), pre = document.createElement("pre");
      summary.textContent = row.created_at + " · " + row.revision_id; pre.textContent = row.body;
      details.append(summary, pre); li.append(details); el("history").querySelector("ol").append(li);
    }
    historyCursor = page.next_cursor; el("more-history").hidden = !historyCursor; el("history").hidden = false;
    return page.items;
  }
  el("more-history").addEventListener("click", async () => { el("more-history").disabled = true; try { await history(); } catch (e) { failure(e); } finally { el("more-history").disabled = false; } });
  async function mine() {
    const page = await api("/me/points?" + new URLSearchParams(mineCursor ? { after: mineCursor } : {}));
    for (const row of page.items) {
      const li = document.createElement("li"), a = document.createElement("a");
      a.textContent = row.preview || row.id; a.href = "/editor/?" + new URLSearchParams({ p: row.id }); li.append(a); el("my-points").querySelector("ul").append(li);
    }
    mineCursor = page.next_cursor; el("more-mine").hidden = !mineCursor;
  }
  el("more-mine").addEventListener("click", async () => { el("more-mine").disabled = true; try { await mine(); } catch(e) { failure(e); } finally { el("more-mine").disabled = false; } });
  function openPoint() { el("open-point").hidden = false; el("open-point").href = "/?" + new URLSearchParams({ p: pid, open: pid }); }
  el("editor-form").addEventListener("input", () => { receipt = null; dirty = true; });
  el("editor-form").addEventListener("submit", async event => {
    event.preventDefault(); if (busy) return;
    let attemptedWrite = false;
    busy = true; el("publish").disabled = true; el("link-word").disabled = true;
    renderFavorites(); el("point-body").readOnly = true; renderLinks();
    try {
      // Refresh CSRF after login in another tab, without discarding an uncertain receipt.
      const session = await api("/me");
      csrf = session.csrf_token;
      if (receipt && receipt.actor !== session.user_id) throw new Error("ACCOUNT_CHANGED");
      const payload = { body: el("point-body").value, lang: language, links: [...links.values()].map(({id, revision_id, content_digest}) => ({id, revision_id, content_digest})) };
      if (pid) payload.expected_revision_id = revision;
      const encoded = JSON.stringify(payload);
      if (!receipt || receipt.body !== encoded) receipt = { body: encoded, key: crypto.randomUUID(), actor: session.user_id };
      attemptedWrite = true;
      const result = await api(pid ? "/points/" + pid : "/points", { method: pid ? "PATCH" : "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf, "Idempotency-Key": receipt.key }, body: receipt.body });
      pid = result.id; revision = result.revision_id; receipt = null; dirty = false;
      window.history.replaceState(null, "", "/editor/?" + new URLSearchParams({ p: pid }));
      el("title").textContent = "Изменить точку"; openPoint(); status(result.changed ? "Опубликовано." : "Изменений нет.");
      // A failed history read must not misreport a committed publication as failed.
      try { await history(true); } catch (_) { status("Опубликовано. Историю сейчас загрузить не удалось; текст сохранён."); }
    } catch (error) {
      if (error.definite && attemptedWrite) receipt = null;
      failure(error);
      if (receipt) status("Ответ о публикации не получен. Нажмите Опубликовать ещё раз для безопасной проверки. Текст сохранён и временно защищён от изменения.");
    }
    finally { busy = false; el("publish").disabled = false; el("link-word").disabled = Boolean(receipt); el("point-body").readOnly = Boolean(receipt); renderLinks(); renderFavorites(); }
  });
  el("retry-login").addEventListener("click", () => location.reload());
  (async () => {
    try {
      const me = await api("/me"); csrf = me.csrf_token;
      if (pid) {
        if (!/^p_[0-9a-f]{32}$/.test(pid)) throw new Error("POINT_EDIT_FORBIDDEN");
        const point = await api("/points/" + pid);
        if (point.source.kind !== "user" || point.source.author_user_id !== me.user_id) throw new Error("POINT_EDIT_FORBIDDEN");
        revision = point.revision_id; el("point-body").value = point.body; language = point.lang || "und";
        const revisions = await history(true), current = revisions.find(row => row.revision_id === revision);
        if (!current) throw new Error("POINT_REVISION_CHANGED");
        links = new Map(current.citations.map(pin => [pin.id, { id: pin.id, revision_id: pin.revision_id, content_digest: pin.content_digest }]));
        renderLinks(); el("title").textContent = "Изменить точку"; openPoint();
      }
      if (!pid && from) {
        if (!/^[a-z0-9][a-z0-9_-]{0,95}$/.test(from)) throw new Error("TARGET_NOT_PUBLIC");
        const source = await api("/points/" + from);
        links.set(source.id, {id:source.id,preview:source.preview,revision_id:source.revision_id,content_digest:source.content_digest});
        renderLinks();
      }
      el("editor-form").hidden = false; el("tag-tools").hidden = false; status("Вы вошли: " + me.handle);
      try { await refreshFavorites(); } catch (_) { status("Редактор готов. Избранное временно недоступно."); }
      try { await mine(); } catch (_) { status("Редактор готов. Список ваших точек временно недоступен."); }
      el("editor-form").dataset.ready = "true";
    } catch(error) { failure(error); el("retry-login").hidden = false; }
  })();
  window.addEventListener("beforeunload", event => { if (dirty || receipt) { event.preventDefault(); } });
})();
