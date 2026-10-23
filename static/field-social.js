/* Public per-point social state. Personal reads stay on the first-party host. */
"use strict";
(() => {
  if (!window.readNode06Public) return;
  const body = document.body;
  const decimal = value => typeof value === "string" && /^\d{1,12}(?:\.\d{1,12})?$/.test(value);
  function node(tag, text, parent) {
    const item = document.createElement(tag); item.textContent = text;
    if (parent) parent.append(item); return item;
  }
  function mount(container, id, displayed = {}) {
    container.className = "point-social";
    container.dataset.pointId = id;
    node("h2", "Поддержка и версии / Support & versions", container);
    const state = node("div", "", container), personal = node("p", "", container);
    state.setAttribute("role", "status");
    const actions = node("div", "", container); actions.className = "picker-actions";
    const origin = body.dataset.managementOrigin || (body.dataset.hosted === "true" && !body.dataset.searchSite ? location.origin : "");
    let manage;
    function updateManage() {
      const currentOrigin = window.node06ManagementOrigin?.() || origin;
      if (manage && currentOrigin) {
        const url = new URL("/community/", currentOrigin);
        url.search = new URLSearchParams({p:id}); manage.href = url.href;
      }
    }
    if (origin) {
      const url = new URL("/community/", origin); url.search = new URLSearchParams({p:id});
      manage = node("a", "Подписаться / версии / голосовать ↗", actions);
      manage.href = url.href; manage.target = "_blank"; manage.rel = "noopener noreferrer";
    }
    const refresh = node("button", "Обновить / Refresh", actions); refresh.type = "button";
    let ticket = 0;
    const alive = sequence => sequence === ticket && container.isConnected;
    async function own(summary, sequence) {
      personal.textContent = "Личная подписка доступна на доверенном сервере / Open account to manage support.";
      if (body.dataset.hosted !== "true" || body.dataset.searchSite || !origin || new URL(origin).origin !== location.origin) return;
      const abort = new AbortController(), timer = setTimeout(()=>abort.abort(),10000);
      try {
        const response = await fetch(`/api/v1/me/subscriptions/${encodeURIComponent(id)}`, {
          credentials:"same-origin", cache:"no-store", signal:abort.signal,
        });
        if (!alive(sequence)) return;
        if (response.status === 401) {personal.textContent = "Войдите, чтобы увидеть свою подписку / Sign in to see your support."; return;}
        if (!response.ok) throw new Error("PERSONAL_UNAVAILABLE");
        const result = await response.json(); if (!alive(sequence)) return;
        const sub = result.subscription;
        personal.textContent = !sub?.active ? "Вы не подписаны / You are not subscribed." :
          sub.revision_id === summary.revision_id && sub.content_digest === summary.content_digest ?
          "Вы поддерживаете основную версию / You support the current version." :
          "Вы поддерживаете другую версию / You support another version.";
        if (result.ballot) personal.textContent += result.ballot === "new" ? " Голос: новая / Voted new." : " Голос: старая / Voted old.";
      } catch (_) {if(alive(sequence))personal.textContent="Личная подписка временно недоступна / Personal support unavailable.";}
      finally {clearTimeout(timer);}
    }
    async function load() {
      const sequence = ++ticket; refresh.disabled = true;
      state.replaceChildren(); node("p", "Загрузка состояния / Loading…", state); personal.textContent = "";
      try {
        const summary = await window.readNode06Public("point.social", {point_id:id});
        updateManage();
        if (!alive(sequence)) return;
        if (summary.schema !== "node06-point-social/1" || summary.id !== id || typeof summary.protected !== "boolean") throw new Error("INVALID_RESPONSE");
        state.replaceChildren();
        const same = !displayed.content_digest || displayed.content_digest === summary.content_digest && displayed.revision_id === summary.revision_id;
        if (!same) node("p", "На сервере другая версия текста. Откройте версии перед поддержкой / Server text changed; review versions first.", state);
        node("p", summary.protected ? "Точка из Git / системы: изменения через источник / Source-managed point." : "Правки с подписчиками принимаются голосованием / Subscribed text changes by voting.", state);
        const influence = summary.influence;
        if (!influence?.available) node("p", "Расчёт влияния ещё не опубликован / Influence not published yet.", state);
        else if (influence.pending) node("p", "Влияние пересчитывается / Influence recalculation pending.", state);
        else if (same) {
          if (![influence.current,influence.held,influence.subscribed].every(decimal)) throw new Error("INVALID_RESPONSE");
          node("p", `Влияние основной версии / Current-version influence: ${influence.current}`, state);
          if (influence.held !== "0") node("p", `На другие версии / Other versions: ${influence.held}`, state);
        }
        const proposal = summary.proposal;
        if (proposal) {
          node("p", "Идёт голосование / Revision vote open. До: " + new Date(proposal.closes_at).toLocaleString(), state);
          if (!influence.pending && proposal.tally && [proposal.tally.old,proposal.tally.new].every(decimal))
            node("p", `Явные голоса по влиянию / Explicit vote influence: старая ${proposal.tally.old}, новая ${proposal.tally.new}`, state);
          if (manage) manage.textContent = "Сравнить версии и голосовать / Compare & vote ↗";
        } else if (manage) manage.textContent = "Подписаться / версии / история ↗";
        await own(summary, sequence);
      } catch(error) {
        updateManage();
        if (alive(sequence)) {
          state.replaceChildren();
          node("p", error.message === "METHOD_NOT_ALLOWED" || error.message === "NOT_FOUND" ?
            "Сервер ещё не поддерживает состояние на карте / Server update required." :
            "Социальное состояние временно недоступно / Social state unavailable. Retry refresh.", state);
        }
      } finally {if(alive(sequence))refresh.disabled = false;}
    }
    refresh.addEventListener("click",load);
    void load();
  }
  window.renderNode06Social = mount;
  function selected(detail) {
    const text = document.querySelector("#point-panel-body .point-text");
    if (!text || !detail?.id) return;
    const old = document.querySelector("#point-panel-body .point-social"); if(old)old.remove();
    const container = document.createElement("section"); text.before(container);
    mount(container, detail.id, detail);
  }
  window.addEventListener("node06:point",event=>selected(event.detail));
  if (body.dataset.currentPoint) {
    const id = body.dataset.currentPoint;
    // Use the displayed pin, never re-label an older local text as current.
    selected({id,revision_id:body.dataset.currentRevision || null,content_digest:body.dataset.currentDigest});
  }
  window.addEventListener("focus",()=>{
    document.querySelectorAll(".point-social button").forEach(button=>{if(!button.disabled && button.getClientRects().length)button.click();});
  });
})();
