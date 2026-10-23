"use strict";
(() => {
  const el = id => document.getElementById(id);
  let me = null, point = null, social = null, ownPin = null, ownFavorite = false, links = new Map();
  let blocksCursor, pointsCursor;
  let subsCursor, inboxCursor, newsCursor, busy = false, draftDirty = false, mutationConfirmed = false;
  // Retain uncertain intent across network retries; switching accounts cannot replay it.
  const receipts = new Map();
  const status = message => { el("community-status").textContent = message; };
  const messages = {
    PENDING_REQUEST: "Сначала повторите прежнее действие, чтобы проверить его результат. Текст сохранён.",
    AUTH_REQUIRED: "Войдите через Аккаунт. Текст на этой странице сохранён.",
    ACCOUNT_CHANGED: "Аккаунт сменился. Вернитесь в исходный аккаунт для проверки предыдущего действия.",
    POINT_PROTECTED: "Эта точка управляется через Git или системой и защищена от голосований.",
    PROPOSAL_ALREADY_OPEN: "Для этой точки уже есть открытое предложение.",
    PROPOSAL_DAILY_LIMIT: "Вы уже предложили правку за последние 24 часа.",
    POINT_REVISION_CHANGED: "Основная версия изменилась. Сохраните свой текст и откройте свежую версию в другой вкладке.",
    TARGET_REVISION_CHANGED: "Связанная точка изменилась. Уберите её связь и выберите свежую версию.",
    PROPOSAL_UNCHANGED: "Новая версия совпадает с основной.",
    VOTING_CLOSED: "Это голосование уже завершено.",
    PROPOSAL_STALE: "Основной текст изменился. Эта правка больше не применяется.",
    BALLOT_SWITCH_REQUIRED: "Во время голосования смените версию явным голосом за старую или новую.",
    AUTH_RATE_LIMITED: "Слишком много действий. Повторите позже.",
    INVALID_INPUT: "Проверьте текст и ссылки.",
  };
  function node(tag, text, parent) {
    const value = document.createElement(tag); if (text) value.textContent = text;
    if (parent) parent.append(value); return value;
  }
  function button(text, parent, handler) {
    const value = node("button", text, parent); value.type = "button"; value.dataset.requiresAuth = "true"; value.disabled = !me || busy;
    value.addEventListener("click", () => act(handler)); return value;
  }
  const tabs=[['points','Мои точки'],['subscriptions','Подписки'],['blocks','Блокировки'],['favorites','Избранное'],['inbox','Лента'],['trust','Доверие'],['news','Git']];
  function showTab(name){
    for(const panel of document.querySelectorAll('[data-profile-panel]'))panel.hidden=panel.dataset.profilePanel!==name;
    for(const b of el('profile-tabs').children){const active=b.dataset.tab===name;b.setAttribute('aria-selected',String(active));b.tabIndex=active?0:-1;}
  }
  el('profile-tabs').setAttribute('role','tablist');
  for(const [name,title] of tabs){
    const b=node('button',title,el('profile-tabs'));b.type='button';b.dataset.tab=name;b.id='profile-tab-'+name;b.setAttribute('role','tab');b.setAttribute('aria-controls','profile-panel-'+name);
    const panel=document.querySelector(`[data-profile-panel=${name}]`);panel.id='profile-panel-'+name;panel.setAttribute('role','tabpanel');panel.setAttribute('aria-labelledby',b.id);
    b.addEventListener('click',()=>showTab(name));
  }
  el('profile-tabs').addEventListener('keydown',event=>{
    const current=tabs.findIndex(([name])=>name===event.target.dataset.tab);
    if(current<0||!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;
    event.preventDefault();const next=event.key==='Home'?0:event.key==='End'?tabs.length-1:(current+(event.key==='ArrowLeft'?-1:1)+tabs.length)%tabs.length;
    showTab(tabs[next][0]);el('profile-tabs').children[next].focus();
  });
  showTab('subscriptions');
  function filterProfile(){
    const query=el('profile-query').value.trim().toLocaleLowerCase();
    for(const row of document.querySelectorAll('[data-profile-panel] ul > li'))row.hidden=Boolean(query&&!row.textContent.toLocaleLowerCase().includes(query));
  }
  el('profile-query').addEventListener('input',filterProfile);
  el('profile-filter').addEventListener('submit',event=>{event.preventDefault();filterProfile();});
  const profileObserver=new MutationObserver(filterProfile);
  for(const panel of document.querySelectorAll('[data-profile-panel]'))profileObserver.observe(panel,{childList:true,subtree:true,characterData:true});
  async function refreshPoints(append=false){
    if(!me)return;
    if(!append){pointsCursor=null;el('profile-points').replaceChildren();}
    const page=await api('/me/points?'+new URLSearchParams(pointsCursor?{after:pointsCursor}:{}));
    for(const row of page.items){
      const li=node('li','',el('profile-points'));
      const a=node('a',row.preview||row.id,li);a.className='profile-point';a.href='/?'+new URLSearchParams({p:row.id,open:row.id});
      const edit=node('a','Изменить',li);edit.href='/editor/?'+new URLSearchParams({p:row.id});
    }
    pointsCursor=page.next_cursor;el('more-points').hidden=!pointsCursor;
  }
  el('more-points').addEventListener('click',()=>act(()=>refreshPoints(true)));
  async function refreshFavorites(){
    el('profile-favorites').replaceChildren();if(!me)return;
    const page=await api('/me/favorites');
    for(const row of page.items){
      const li=node('li','',el('profile-favorites'));
      const a=node('a',row.preview||row.id,li);a.className='profile-point';a.href='/?'+new URLSearchParams({p:row.id,open:row.id});
      button('×',li,async()=>{await write('/me/favorites/'+row.id,{active:false});await refreshFavorites();}).setAttribute('aria-label','Убрать из избранного');
    }
    if(!page.items.length)node('li','Пока пусто',el('profile-favorites'));
  }
  function failure(error) { status(messages[error.message] || "Действие не завершено. Текст сохранён; повторите попытку."); }
  async function api(path, options = {}) {
    const controller = new AbortController(), timeout = setTimeout(() => controller.abort(), 15000);
    try {
      const response = await fetch("/api/v1" + path, { ...options, credentials: "same-origin", cache: "no-store", signal: controller.signal });
      const value = await response.json();
      if (!response.ok) { const error = new Error(value.code || "FAILED"); error.definite = response.status < 500; error.status = response.status; throw error; }
      return value;
    } finally { clearTimeout(timeout); }
  }
  async function write(path, payload) {
    const session = await api("/me");
    if(me&&session.user_id!==me.user_id)throw new Error("ACCOUNT_CHANGED");
    const body = JSON.stringify(payload), previous = receipts.get(path);
    if (previous && (previous.body !== body || previous.user !== session.user_id)) throw new Error(previous.user !== session.user_id ? "ACCOUNT_CHANGED" : "PENDING_REQUEST");
    const receipt = previous || { body, user: session.user_id, key: crypto.randomUUID() };
    receipts.set(path, receipt);
    try {
      const result = await api(path, { method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": session.csrf_token, "Idempotency-Key": receipt.key }, body });
      receipts.delete(path); mutationConfirmed = true; return result;
    } catch(error) { if (error.definite) receipts.delete(path); throw error; }
  }
  async function act(action) {
    if (busy) return; busy = true; mutationConfirmed = false;
    document.querySelectorAll("button").forEach(b => { if (b.id !== "point-picker-open") b.disabled = true; });
    el("proposal-body").readOnly = true;
    el("color-form").querySelectorAll("input").forEach(input=>{input.disabled=true;});
    try { await action(); } catch (error) {
      if (mutationConfirmed) status("Действие сохранено сервером. Не удалось обновить отображение; нажмите Обновить.");
      else failure(error);
    }
    finally {
      busy = false;
      document.querySelectorAll("button").forEach(b => { b.disabled = !me && b.dataset.requiresAuth === "true"; });
      el("color-form").querySelectorAll("input").forEach(input=>{input.disabled=receipts.has("/me/geometry");});
      const unresolved = point && receipts.has(`/points/${point.id}/proposals`);
      el("proposal-body").readOnly = Boolean(unresolved);
      el("proposal-link").disabled = Boolean(unresolved);
      if (unresolved) status("Ответ о предложении не получен. Повторите Предложить версию для безопасной проверки; текст защищён от изменения.");
      if (social) { renderProposals(); applyBudget(); }
    }
  }
  function renderLinks() {
    el("proposal-links").replaceChildren();
    for (const pin of links.values()) {
      const li = node("li", pin.id + " ", el("proposal-links"));
      button("Убрать связь", li, async () => { links.delete(pin.id); draftDirty = true; renderLinks(); });
    }
  }
  async function load(pid, resetDraft = true) {
    if (point && point.id !== pid) {
      if (receipts.size) throw new Error("PENDING_REQUEST");
      if (draftDirty && !confirm("Перейти к другой точке и убрать несохранённый текст?")) return;
    }
    social = await api(`/points/${pid}/social`); point = social.point;
    ownPin = me ? await api(`/me/subscriptions/${pid}`) : null;
    history.replaceState(null, "", "/community/?" + new URLSearchParams({ p: pid, ...(new URLSearchParams(location.search).has("intent")?{intent:new URLSearchParams(location.search).get("intent")}:{}) }));
    el("selected-point").hidden = false; el("point-name").textContent = point.preview || point.id;
    el("point-origin").textContent = point.lang + " · " + point.source.kind;
    el("point-current").textContent = point.body;
    el("point-address").href = "/?" + new URLSearchParams({ p: pid, open: pid });
    el("support-point").hidden = !me;
    el("support-point").textContent = ownPin?.subscription?.active ? "Отписаться / снять поддержку" : "Подписаться на основную версию";
    ownFavorite = me ? (await api("/me/favorites")).items.some(row=>row.id===pid) : false;
    el("favorite-point").hidden=!me;el("favorite-point").textContent=ownFavorite?"Удалить из избранного":"В избранное";
    el("block-point").hidden = !me || Boolean(ownPin?.block && ownPin.block.content_digest === point.content_digest && ownPin.block.revision_id === point.revision_id);
    el("unblock-point").hidden = !me || !ownPin?.block;
    el("confirm-support").hidden = !me || !ownPin?.subscription?.active || ownPin.subscription.content_digest === point.content_digest || ownPin.ballot === "new";
    el("support-status").textContent = ownPin?.block ? (ownPin.block.content_digest === point.content_digest ? "Вы блокируете основную версию." : "Блокировка другой версии; для новой основной версии подтвердите её отдельно.") : !ownPin?.subscription?.active ? "Вы не подписаны." : ownPin.subscription.content_digest === point.content_digest ? "Вы поддерживаете основную версию." : "Вы подписаны на другую версию. Для новой основной версии нужна явная поддержка.";
    el("protection").textContent = social.protected ? "Защищённая точка: обновления принимаются из Git или системы." : "Пользовательская точка: правки с подписчиками принимаются голосованием.";
    const open = social.proposals.find(q => q.state === "open");
    el("proposal-form").hidden = !me || social.protected || Boolean(open);
    if (resetDraft) {
      el("proposal-body").value = point.body;
      links = new Map();
      for (const id of (point.declared_links || []).slice(0,16)) {
        try { const target = await api("/points/" + id); links.set(id, { id, revision_id: target.revision_id, content_digest: target.content_digest }); }
        catch (_) { /* A stale target is deliberately not silently replaced. */ }
      }
      draftDirty = false; renderLinks();
    }
    renderProposals(); applyBudget();
  }
  function applyBudget() {
    const next = ownPin?.next_proposal_at;
    const delayed = next && new Date(next).getTime() > Date.now();
    el("submit-proposal").disabled = Boolean(delayed);
    el("submit-proposal").title = delayed ? "Следующее предложение: " + new Date(next).toLocaleString() : "";
  }
  function renderProposals() {
    el("proposals").replaceChildren();
    for (const q of social.proposals) {
      const section = node("section", "", el("proposals")); section.className = "community-proposal";
      const labels={open:"идёт голосование",adopted:"принято",retained:"сохранена старая версия",stale:"основа изменилась"};
      node("h3", "Предложение · " + (labels[q.state] || q.state), section);
      node("p", "Завершение: " + new Date(q.closes_at).toLocaleString(), section);
      const comparison = node("div", "", section); comparison.className = "community-comparison";
      for (const [title,body] of [["Старая версия",q.base_body],["Новая версия",q.content.body]]) {
        const version = node("article", "", comparison); version.className = "community-version";
        node("h4",title,version); node("pre",body,version);
      }
      const tally = social.influence?.tallies?.[q.id];
      node("p",q.result ? `Итоговое влияние: старая ${q.result.old_influence ?? "—"}, новая ${q.result.new_influence ?? "—"}` : tally ? `Влияние явных голосов: старая ${tally.old}, новая ${tally.new}. Всего у подписчиков: ${tally.subscribed}` : "Расчёт влияния ожидается. Число аккаунтов не используется вместо него.",section);
      if (q.state === "open") {
        const choice = ownPin?.ballot;
        node("p",choice ? "Ваш явный голос: " + (choice === "new" ? "новая версия" : "старая версия") : "Вы ещё не голосовали. Подписка сама не даёт голос.",section);
        for (const value of ["old","new"]) button(value === "old" ? "Голос за старую" : "Голос за новую",section,async()=>{
          await write(`/proposals/${q.id}/vote`,{choice:value}); status("Голос записан, подписка переключена на выбранную версию.");
          await load(point.id,false); await refreshMine(); await refreshBlocks();
        });
      }
    }
  }
  el("choose-point").addEventListener("click", () => {
    if (busy) return;
    window.openNode06Picker({onSelect: pin => act(async()=>{
      await load(pin.id); status("Точка выбрана.");
    })});
  });
  el("support-point").addEventListener("click", () => act(async()=>{
    await write(`/points/${point.id}/subscription`,{revision_id:point.revision_id,content_digest:point.content_digest,active:!ownPin?.subscription?.active});
    status("Подписка обновлена. Это действие само не голосует за правку."); await load(point.id,false); await refreshMine(); await refreshBlocks();
  }));
  el("favorite-point").addEventListener("click",()=>act(async()=>{
    await write(`/me/favorites/${point.id}`,{active:!ownFavorite});await load(point.id,false);status("Избранное обновлено.");
  }));
  el("confirm-support").addEventListener("click", () => act(async()=>{
    await write(`/points/${point.id}/subscription`,{revision_id:point.revision_id,content_digest:point.content_digest,active:true});
    await load(point.id,false); await refreshMine(); await refreshBlocks(); status("Поддержка новой основной версии подтверждена.");
  }));
  for (const [id,active] of [["block-point",true],["unblock-point",false]]) el(id).addEventListener("click",()=>act(async()=>{
    const pin=active?point:ownPin.block;
    await write(`/points/${point.id}/block`,{revision_id:pin.revision_id,content_digest:pin.content_digest,active});
    await load(point.id,false);await refreshMine();await refreshBlocks();status(active?"Блокировка записана. Это не голос за старую версию.":"Блокировка снята.");
  }));
  // Same order as the root seed and the six-coordinate API. No pair is
  // reconstructed from RGB, and changing one stat never changes its opposite.
  const statOrder=[0,1,2,3,4,5];
  function readStats(){
    const values=statOrder.map(stat=>el('coordinate-'+stat).valueAsNumber);
    return values.every(value=>Number.isInteger(value)&&value>=1&&value<=65535)?values:null;
  }
  function previewColor() {
    const values=readStats();
    if(!values){el('color-preview').textContent='';return;}
    const hex=[0,2,4].map(j=>Math.round(255*values[j]/(values[j]+values[j+1])).toString(16).padStart(2,"0")).join("");
    el("color-preview").textContent="#"+hex;el("color-preview").style.backgroundColor="#"+hex;
  }
  function showStats(values){
    statOrder.forEach((stat,index)=>{el('coordinate-'+stat).value=String(values[index]);});
    previewColor();
  }
  for(const stat of statOrder)el('coordinate-'+stat).addEventListener('input',previewColor);
  el("color-form").addEventListener("submit",event=>{
    event.preventDefault();const values=readStats();if(!values){el('color-form').reportValidity();return;}
    act(async()=>{
      const saved=await write("/me/geometry",{coordinates:values});showStats(saved.coordinates);
      status("Координаты сохранены. Позиции обновятся после пересчёта влияния.");
    });
  });
  async function refreshColor() {
    if(!me)return;
    const profile=await api("/me/geometry");showStats(profile.coordinates);
    el("my-color").hidden=false;if(location.hash==="#my-color"){el("my-color").open=true;showTab("trust");}
  }
  async function refreshBlocks(append=false) {
    if(!me)return;
    if(!append){blocksCursor=null;el("my-blocks").replaceChildren();}
    const page=await api("/me/blocks?"+new URLSearchParams(blocksCursor?{after:blocksCursor}:{}));
    for(const row of page.items){const li=node("li",'',el("my-blocks"));
      const a=node('a',row.preview||row.point_id,li);a.className='profile-point';a.href='/?'+new URLSearchParams({p:row.point_id,open:row.point_id});
      button("Снять блокировку",li,async()=>{
      await write(`/points/${row.point_id}/block`,{revision_id:row.revision_id,content_digest:row.content_digest,active:false});
      await refreshBlocks();await refreshMine();if(point?.id===row.point_id)await load(point.id,false);
    });}
    blocksCursor=page.next_cursor;el("more-blocks").hidden=!blocksCursor;
  }
  el("more-blocks").addEventListener("click",()=>act(()=>refreshBlocks(true)));
  el("proposal-link").addEventListener("click", () => {
    if (busy) return;
    const input = el("proposal-body"), text = input.value, start = input.selectionStart, end = input.selectionEnd;
    window.openNode06Picker({onSelect:pin=>{
      if (busy || pin.id === point.id || links.size >= 16 && !links.has(pin.id)) return;
      links.set(pin.id,{id:pin.id,revision_id:pin.revision_id,content_digest:pin.content_digest});
      const selected = text.slice(start,end);
      if (selected && input.value === text && !/[\[\]\n]/.test(selected)) input.value=text.slice(0,start)+`[${selected}](md://point/${pin.id})`+text.slice(end);
      draftDirty=true; renderLinks(); input.focus();
    }});
  });
  el("proposal-form").addEventListener("input",()=>{draftDirty=true;});
  el("proposal-form").addEventListener("submit",event=>{event.preventDefault();act(async()=>{
    await write(`/points/${point.id}/proposals`,{body:el("proposal-body").value,lang:point.lang || "und",links:[...links.values()],expected_revision_id:point.revision_id,expected_digest:point.content_digest});
    draftDirty=false;status("Предложение опубликовано. Для поддержки новой версии нажмите явный голос.");await load(point.id,false);
  });});
  async function refreshMine(append=false) {
    if (!me) return;
    if (!append) {subsCursor=null;el("my-subscriptions").replaceChildren();el("my-trust").replaceChildren();}
    const own=await api("/me/social?"+new URLSearchParams(subsCursor?{after:subsCursor}:{}));
    for (const row of own.items) {
      const li=node("li","",el("my-subscriptions"));
      const a=node('a',row.preview||row.point_id,li);a.className='profile-point';a.href='/?'+new URLSearchParams({p:row.point_id,open:row.point_id});
      button('Версии',li,async()=>{await load(row.point_id);});
      button('×',li,async()=>{
        await write(`/points/${row.point_id}/subscription`,{revision_id:row.revision_id,content_digest:row.content_digest,active:false});
        await refreshMine();if(point?.id===row.point_id)await load(point.id,false);
      }).setAttribute('aria-label','Отписаться');
    }
    subsCursor=own.next_cursor;el("more-subscriptions").hidden=!subsCursor;
    if (!append) for (const target of own.trust) {
      const li=node("li",target+" ",el("my-trust"));button("Снять доверие",li,async()=>{await write(`/people/${target}/trust`,{active:false});await refreshMine();});
    }
    const influence=await api("/me/influence");
    el("my-influence").textContent=influence ? `Ваше влияние: ${influence.weight}. На поддержку точек: ${influence.point_budget}${influence.pending ? "; ожидается пересчёт" : ""}.` : "Расчёт влияния ещё не опубликован.";
  }
  async function refreshInbox(append=false) {
    if (!me) return;
    if (!append) {inboxCursor=null;el("inbox").replaceChildren();}
    const page=await api("/me/inbox?"+new URLSearchParams(inboxCursor?{before:inboxCursor}:{}));
    for (const row of page.items) {
      const li=node("li",row.kind+" · "+row.point_id+" ",el("inbox"));
      button("Открыть",li,async()=>{await load(row.point_id);});
      if (!row.read_at) button("Прочитано",li,async()=>{await write(`/me/inbox/${row.seq}/read`,{});await refreshInbox();});
    }
    inboxCursor=page.next_cursor;el("more-inbox").hidden=!inboxCursor;
  }
  async function refreshNews(append=false) {
    if (!append) {newsCursor=null;el("news").replaceChildren();}
    const page=await api("/news?"+new URLSearchParams(newsCursor?{before:newsCursor}:{}));
    for (const row of page.items) {
      const li=node("li",row.kind+" · "+row.point_id+" · "+(row.payload.commit||""),el("news"));
      const a=node("a"," Открыть",li);a.href="/?"+new URLSearchParams({p:row.point_id,open:row.point_id});
    }
    newsCursor=page.next_cursor;el("more-news").hidden=!newsCursor;
  }
  el("more-subscriptions").addEventListener("click",()=>act(()=>refreshMine(true)));
  el("more-inbox").addEventListener("click",()=>act(()=>refreshInbox(true)));
  el("more-news").addEventListener("click",()=>act(()=>refreshNews(true)));
  el("people-form").addEventListener("submit",event=>{event.preventDefault();act(async()=>{
    const page=await api("/people?"+new URLSearchParams({q:el("people-query").value}));el("people-results").replaceChildren();
    for (const user of page.items) {const li=node("li",user.handle+" ",el("people-results"));if(user.id!==me?.user_id) button("Доверять",li,async()=>{await write(`/people/${user.id}/trust`,{active:true});await refreshMine();});}
  });});
  el("community-refresh").addEventListener("click",()=>act(async()=>{
    if(point)await load(point.id,false);
    await refreshMine();await refreshBlocks();await refreshPoints();await refreshFavorites();await refreshInbox();await refreshNews();
    status("Обновлено.");
  }));
  window.addEventListener("beforeunload",event=>{if(draftDirty||receipts.size)event.preventDefault();});
  (async()=>{
    busy=true;el("choose-point").disabled=true;
    try {me=await api("/me");status("Вы вошли: "+me.handle);} catch(error){status(error.status === 401 ? "Просмотр доступен всем. Для подписки и голосования войдите через Аккаунт." : "Не удалось проверить сессию. Обновите страницу, когда сервер будет доступен.");}
    try {
      const pid=new URLSearchParams(location.search).get("p");if(pid&&/^[a-z0-9][a-z0-9_-]{0,95}$/.test(pid))await load(pid);
      await refreshColor();await refreshMine();await refreshBlocks();await refreshPoints();await refreshFavorites();await refreshInbox();await refreshNews();
    } catch(error){failure(error);}
    finally {
      busy=false;
      document.querySelectorAll("button").forEach(b=>{b.disabled=!me && b.dataset.requiresAuth==="true";});
      if(social){renderProposals();applyBudget();}
      const intent=new URLSearchParams(location.search).get("intent");
      const requested={support:"support-point",block:"block-point",favorite:"favorite-point"}[intent];
      if(requested&&me){el(requested).focus();el(requested).scrollIntoView({block:"center"});}
    }
  })();
})();
