/* Home presentation only. Never rename, filter or translate the shared graph. */
(() => {
  'use strict';
  const home = document.querySelector('#start-page[data-home-default]');
  if (!home) return;
  const variants = [...home.querySelectorAll('[data-home-language]')];
  const available = new Map(variants.map(node => [node.dataset.homeLanguage.toLowerCase(), node.dataset.homeLanguage]));
  const select = home.querySelector('[data-home-language-select]');
  const key = 'node06.home-language.' + home.dataset.homeKey;
  const fallback = home.dataset.homeDefault;
  const match = language => {
    let tag = String(language || '').toLowerCase();
    while (tag) {
      if (available.has(tag)) return available.get(tag);
      tag = tag.includes('-') ? tag.slice(0, tag.lastIndexOf('-')) : '';
    }
    return null;
  };
  function apply(language) {
    const chosen = available.get(String(language).toLowerCase()) || fallback;
    for (const node of variants) node.hidden = node.dataset.homeLanguage !== chosen;
    if (select) select.value = chosen;
    document.documentElement.lang = chosen;
    home.dataset.homeCurrent = chosen;
  }
  let saved;
  try { saved = localStorage.getItem(key); } catch { /* Storage is optional. */ }
  const browser = (navigator.languages || [navigator.language]).map(match).find(Boolean);
  // Fallback always selects a whole variant, never individual fields or links.
  apply((saved && available.get(saved.toLowerCase())) || browser || fallback);
  if (select) {
    select.parentElement.hidden = false;
    select.addEventListener('change', () => {
      apply(select.value);
      try { localStorage.setItem(key, select.value); } catch { /* Still switch this page. */ }
    });
  }
})();
