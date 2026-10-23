"use strict";
(() => {
  const el = id => document.getElementById(id);
  let pid = new URLSearchParams(location.search).get("p"), revision = null, csrf;
  let links = new Map(), receipt = null, busy = false, dirty = false, selection, historyCursor, mineCursor;
  const status = text => { el("editor-status").textContent = text; };
  const errors = {
    POINT_REVISION_CHANGED: "Точка уже изменена. Скопируйте свой текст и откройте свежую версию в другой вкладке.",
    TARGET_REVISION_CHANGED: "Одна из связанных точек изменилась. Удалите её из списка и выберите свежую версию через поиск.",
    TARGET_NOT_PUBLIC: "Одна из связанных точек недоступна. Выберите другую.",
    AUTH_REQUIRED: "Войдите через Аккаунт, затем повторите публикацию. Ваш текст здесь сохранён.",
    CSRF_REQUIRED: "Сессия изменилась. Войдите через Аккаунт и повторите публикацию.",
    POINT_EDIT_FORBIDDEN: "Изменять напрямую можно только свою пользовательскую точку.",
    UNDECLARED_POINT_LINK: "В тексте есть смысловая ссылка, которой нет в списке связей. Выберите её через поиск или уберите ссылку.",
    ACCOUNT_CHANGED: "Аккаунт сменился. Войдите в исходный аккаунт, чтобы завершить проверку предыдущей публикации.",
    INVALID_INPUT: "Проверьте язык, текст и число связей (1–16).",
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
  function renderLinks() {
    el("point-links").replaceChildren();
    for (const pin of links.values()) {
      const li = document.createElement("li"), remove = document.createElement("button");
      const a = document.createElement("a");
      a.textContent = pin.id; a.href = "/?" + new URLSearchParams({ p: pin.id, open: pin.id });
      a.target = "_blank"; a.rel = "noopener noreferrer"; li.append(a);
      remove.type = "button"; remove.textContent = "Убрать связь";
      remove.disabled = busy || Boolean(receipt);
      remove.addEventListener("click", () => { links.delete(pin.id); receipt = null; dirty = true; renderLinks(); });
      li.append(" ", remove); el("point-links").append(li);
    }
  }
  el("link-word").addEventListener("click", () => {
    const input = el("point-body");
    selection = { start: input.selectionStart, end: input.selectionEnd, text: input.value };
    window.openNode06Picker({ onSelect(pin) {
      if (busy) return;
      if (links.size >= 16 && !links.has(pin.id)) { status("Не больше 16 связей."); return; }
      if (pin.id === pid) { status("Точку нельзя связать с собой."); return; }
      links.set(pin.id, { id: pin.id, revision_id: pin.revision_id, content_digest: pin.content_digest });
      const selected = selection.text.slice(selection.start, selection.end);
      if (selected && input.value === selection.text && !/[\[\]\n]/.test(selected)) {
        input.value = selection.text.slice(0, selection.start) + `[${selected}](md://point/${pin.id})` + selection.text.slice(selection.end);
      }
      receipt = null; dirty = true; renderLinks(); input.focus();
    }});
  });
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
    el("point-body").readOnly = true; el("point-lang").readOnly = true; renderLinks();
    try {
      // Refresh CSRF after login in another tab, without discarding an uncertain receipt.
      const session = await api("/me");
      csrf = session.csrf_token;
      if (receipt && receipt.actor !== session.user_id) throw new Error("ACCOUNT_CHANGED");
      const payload = { body: el("point-body").value, lang: el("point-lang").value, links: [...links.values()] };
      if (pid) payload.expected_revision_id = revision;
      const encoded = JSON.stringify(payload);
      if (!receipt || receipt.body !== encoded) receipt = { body: encoded, key: crypto.randomUUID(), actor: session.user_id };
      attemptedWrite = true;
      const result = await api(pid ? "/points/" + pid : "/points", { method: pid ? "PATCH" : "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf, "Idempotency-Key": receipt.key }, body: receipt.body });
      pid = result.id; revision = result.revision_id; receipt = null; dirty = false;
      window.history.replaceState(null, "", "/editor/?" + new URLSearchParams({ p: pid }));
      el("title").textContent = "Редактирование точки"; openPoint(); status(result.changed ? "Опубликовано. Связи не добавляют поддержку." : "Изменений нет.");
      // A failed history read must not misreport a committed publication as failed.
      try { await history(true); } catch (_) { status("Опубликовано. Историю сейчас загрузить не удалось; текст сохранён."); }
    } catch (error) {
      if (error.definite && attemptedWrite) receipt = null;
      failure(error);
      if (receipt) status("Ответ о публикации не получен. Нажмите Опубликовать ещё раз для безопасной проверки. Текст сохранён и временно защищён от изменения.");
    }
    finally { busy = false; el("publish").disabled = false; el("link-word").disabled = Boolean(receipt); el("point-body").readOnly = Boolean(receipt); el("point-lang").readOnly = Boolean(receipt); renderLinks(); }
  });
  (async () => {
    try {
      const me = await api("/me"); csrf = me.csrf_token;
      if (pid) {
        if (!/^p_[0-9a-f]{32}$/.test(pid)) throw new Error("POINT_EDIT_FORBIDDEN");
        const point = await api("/points/" + pid);
        if (point.source.kind !== "user" || point.source.author_user_id !== me.user_id) throw new Error("POINT_EDIT_FORBIDDEN");
        revision = point.revision_id; el("point-body").value = point.body; el("point-lang").value = point.lang;
        const revisions = await history(true), current = revisions.find(row => row.revision_id === revision);
        if (!current) throw new Error("POINT_REVISION_CHANGED");
        links = new Map(current.citations.map(pin => [pin.id, { id: pin.id, revision_id: pin.revision_id, content_digest: pin.content_digest }]));
        renderLinks(); el("title").textContent = "Редактирование точки"; openPoint();
      }
      el("editor-form").hidden = false; status("Вы вошли: " + me.handle);
      try { await mine(); } catch (_) { status("Редактор готов. Список ваших точек временно недоступен."); }
    } catch(error) { failure(error); }
  })();
  window.addEventListener("beforeunload", event => { if (dirty || receipt) { event.preventDefault(); } });
})();
