(async()=>{
  const res=await fetch('/data/points.json');
  const all=await res.json();
  const byId=new Map(all.map(p=>[p.id,p]));
  const lang=document.body?.dataset.lang;
  if(document.body?.dataset.page!=='field') return;
  const host=document.getElementById('field-map');
  const card=document.getElementById('hover-card');
  const local=all.filter(p=>p.lang===lang);
  if(!local.length) return;
  const params=new URLSearchParams(location.search);
  let center=byId.get(params.get('p'));
  if(!center||center.lang!==lang) center=[...local].sort((a,b)=>b.degree-a.degree)[0];
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
  visible.forEach(p=>{const P=pos.get(p.id),g=document.createElementNS(svgNS,'g');g.setAttribute('class','node'+(p.id===center.id?' center':''));g.dataset.id=p.id;const c=document.createElementNS(svgNS,'circle');c.setAttribute('cx',P.x);c.setAttribute('cy',P.y);c.setAttribute('r',radius(p));g.appendChild(c);g.addEventListener('mouseenter',e=>{card.hidden=false;card.innerHTML=`${escapeHtml(p.preview)}<span class="id">${escapeHtml(p.id)} · ${p.degree} links</span>`});g.addEventListener('mousemove',e=>{const r=host.getBoundingClientRect();card.style.left=Math.min(e.clientX-r.left+16,r.width-360)+'px';card.style.top=Math.max(8,e.clientY-r.top+16)+'px'});g.addEventListener('mouseleave',()=>card.hidden=true);g.addEventListener('click',()=>{location.href=`/${p.lang}/p/${encodeURIComponent(p.id)}/`});svg.appendChild(g)});
  host.replaceChildren(svg);
  function escapeHtml(s){return s.replace(/[&<>'"]/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[ch]))}
})();
