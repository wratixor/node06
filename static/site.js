(async()=>{
  const res=await fetch('/data/points.json');
  const all=await res.json();
  const byId=new Map(all.map(p=>[p.id,p]));
  const lang=document.body?.dataset.lang;
  if(document.body?.dataset.page!=='field') return;

  const host=document.getElementById('field-map');
  const card=document.getElementById('hover-card');
  const modal=document.getElementById('point-modal');
  const modalBody=document.getElementById('point-modal-body');
  const modalClose=document.getElementById('point-modal-close');
  const modalFocus=document.getElementById('point-modal-focus');
  const local=all.filter(p=>p.lang===lang);
  if(!local.length) return;

  const params=new URLSearchParams(location.search);
  let center=byId.get(params.get('p'));
  if(!center||center.lang!==lang) center=[...local].sort((a,b)=>b.degree-a.degree)[0];
  let openPoint=null;

  function updateUrl({centerId=center.id,openId=null,replace=false}={}){
    const q=new URLSearchParams();
    if(centerId) q.set('p',centerId);
    if(openId) q.set('open',openId);
    const url=`/${lang}/?${q.toString()}`;
    history[replace?'replaceState':'pushState']({},'',url);
  }

  function escapeHtml(s=''){
    return s.replace(/[&<>'"]/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[ch]));
  }

  function openModal(point,{push=true}={}){
    if(!point) return;
    openPoint=point;
    modalBody.innerHTML=`
      <div class="eyebrow">ROOT POINT · ${escapeHtml(point.id)}</div>
      <div class="point-text">${point.html}</div>
      <section>
        <h2>LINKS</h2>
        <ul class="links-list">${point.links.map(id=>{
          const target=byId.get(id);
          return target?`<li><a class="point-link" href="/${target.lang}/?p=${encodeURIComponent(center.id)}&open=${encodeURIComponent(target.id)}" data-point-id="${escapeHtml(target.id)}">${escapeHtml(target.preview)}</a></li>`:'';
        }).join('')}</ul>
      </section>
      <p class="meta">created ${point.created_at.slice(0,10)} · last interaction ${point.last_interaction_at.slice(0,10)} · ${point.degree} links</p>`;
    modal.hidden=false;
    document.body.classList.add('modal-open');
    modalFocus.textContent=lang==='ru'?'СДЕЛАТЬ ЦЕНТРОМ':'CENTER ON MAP';
    modalClose.setAttribute('aria-label',lang==='ru'?'Закрыть':'Close');
    if(push) updateUrl({openId:point.id});
  }

  function closeModal({push=true}={}){
    modal.hidden=true;
    document.body.classList.remove('modal-open');
    openPoint=null;
    if(push) updateUrl({openId:null});
  }

  function focusPoint(point){
    if(!point) return;
    center=point;
    closeModal({push:false});
    updateUrl({centerId:center.id,openId:null});
    renderMap();
  }

  modalClose.addEventListener('click',()=>closeModal());
  modal.addEventListener('click',e=>{if(e.target===modal) closeModal();});
  modalFocus.addEventListener('click',()=>focusPoint(openPoint));
  document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!modal.hidden) closeModal();});
  modalBody.addEventListener('click',e=>{
    const a=e.target.closest('a.point-link');
    if(!a) return;
    const target=byId.get(a.dataset.pointId);
    if(!target) return;
    e.preventDefault();
    openModal(target);
  });

  function renderMap(){
    const d1=center.links.map(id=>byId.get(id)).filter(Boolean);
    const d1ids=new Set(d1.map(p=>p.id));
    const d2ids=new Set();
    d1.forEach(p=>p.links.forEach(id=>{if(id!==center.id&&!d1ids.has(id)) d2ids.add(id)}));
    const d2=[...d2ids].map(id=>byId.get(id)).filter(Boolean);

    const w=1000,h=650,cx=w/2,cy=h/2;
    const pos=new Map([[center.id,{x:cx,y:cy,depth:0}]]);
    const placeRing=(arr,r,depth,offset=0)=>arr.forEach((p,i)=>{
      const a=offset+(Math.PI*2*i/Math.max(1,arr.length));
      pos.set(p.id,{x:cx+Math.cos(a)*r,y:cy+Math.sin(a)*r,depth});
    });
    placeRing(d1,170,1,-Math.PI/2);
    placeRing(d2,285,2,Math.PI/Math.max(2,d2.length));

    const visible=[center,...d1,...d2];
    const visibleIds=new Set(visible.map(p=>p.id));
    const edgeKeys=new Set();
    const edges=[];
    visible.forEach(p=>p.links.forEach(q=>{
      if(!visibleIds.has(q)) return;
      const key=[p.id,q].sort().join('|');
      if(edgeKeys.has(key)) return;
      edgeKeys.add(key);edges.push([p.id,q]);
    }));

    const radius=p=>Math.max(10,Math.min(42,10+Math.sqrt(Math.max(0,p.degree))*7));
    const svgNS='http://www.w3.org/2000/svg';
    const svg=document.createElementNS(svgNS,'svg');svg.setAttribute('viewBox',`0 0 ${w} ${h}`);
    const defs=document.createElementNS(svgNS,'defs');
    defs.innerHTML='<radialGradient id="sphere" cx="35%" cy="30%" r="70%"><stop offset="0%" stop-color="#e2f0f5"/><stop offset="28%" stop-color="#9eb9c4"/><stop offset="70%" stop-color="#405463"/><stop offset="100%" stop-color="#18232d"/></radialGradient>';
    svg.appendChild(defs);
    edges.forEach(([a,b])=>{const A=pos.get(a),B=pos.get(b);if(!A||!B)return;const l=document.createElementNS(svgNS,'line');l.setAttribute('x1',A.x);l.setAttribute('y1',A.y);l.setAttribute('x2',B.x);l.setAttribute('y2',B.y);l.setAttribute('class','edge');svg.appendChild(l)});
    visible.forEach(p=>{
      const P=pos.get(p.id),g=document.createElementNS(svgNS,'g');
      g.setAttribute('class','node'+(p.id===center.id?' center':''));
      g.dataset.id=p.id;
      const c=document.createElementNS(svgNS,'circle');c.setAttribute('cx',P.x);c.setAttribute('cy',P.y);c.setAttribute('r',radius(p));g.appendChild(c);
      g.addEventListener('mouseenter',()=>{card.hidden=false;card.innerHTML=`${escapeHtml(p.preview)}<span class="id">${escapeHtml(p.id)} · ${p.degree} links</span>`});
      g.addEventListener('mousemove',e=>{const r=host.getBoundingClientRect();card.style.left=Math.min(e.clientX-r.left+16,r.width-360)+'px';card.style.top=Math.max(8,e.clientY-r.top+16)+'px'});
      g.addEventListener('mouseleave',()=>card.hidden=true);
      g.addEventListener('click',()=>openModal(p));
      svg.appendChild(g);
    });
    host.replaceChildren(svg);
    const centerLabel=document.getElementById('field-center-id');
    if(centerLabel) centerLabel.textContent=center.id;
  }

  renderMap();

  const initialOpen=byId.get(params.get('open'));
  if(initialOpen) openModal(initialOpen,{push:false});

  addEventListener('popstate',()=>{
    const q=new URLSearchParams(location.search);
    const nextCenter=byId.get(q.get('p'));
    if(nextCenter&&nextCenter.lang===lang&&nextCenter.id!==center.id){center=nextCenter;renderMap();}
    const nextOpen=byId.get(q.get('open'));
    if(nextOpen) openModal(nextOpen,{push:false}); else closeModal({push:false});
  });
})();
