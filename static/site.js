(async()=>{
  const res=await fetch('/data/points.json');
  const all=await res.json();
  const byId=new Map(all.map(p=>[p.id,p]));
  const body=document.body;
  if(!body||body.dataset.page!=='field') return;

  const lang=body.dataset.lang;
  const local=all.filter(p=>p.lang===lang);
  if(!local.length) return;

  const host=document.getElementById('field-map');
  const card=document.getElementById('hover-card');
  const panel=document.getElementById('point-panel');
  const panelBody=document.getElementById('point-panel-body');
  const panelClose=document.getElementById('point-panel-close');
  const controls=document.getElementById('field-controls');
  const shell=document.querySelector('.field-workspace');

  const params=new URLSearchParams(location.search);
  let center=byId.get(params.get('p'));
  if(!center||center.lang!==lang) center=[...local].sort((a,b)=>b.degree-a.degree)[0];
  let openPoint=byId.get(params.get('open')) || null;

  let mode=localStorage.getItem('node06-mode')||'read';
  let layout=localStorage.getItem('node06-layout')||'side';
  if(!['explore','read','feed'].includes(mode)) mode='read';
  if(!['side','below','overlay'].includes(layout)) layout='side';

  let rotX=-0.28, rotY=0.55, zoom=1;
  let dragging=false, lastX=0, lastY=0, moved=false;

  function escapeHtml(s=''){
    return String(s).replace(/[&<>'"]/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[ch]));
  }

  function updateUrl({replace=false}={}){
    const q=new URLSearchParams();
    if(center) q.set('p',center.id);
    if(openPoint&&mode==='read') q.set('open',openPoint.id);
    const url=`/${lang}/?${q.toString()}`;
    history[replace?'replaceState':'pushState']({},'',url);
  }

  function setMode(next,{persist=true}={}){
    mode=next;
    if(persist) localStorage.setItem('node06-mode',mode);
    controls.querySelectorAll('[data-mode]').forEach(b=>b.classList.toggle('active',b.dataset.mode===mode));
    if(mode==='explore'){
      openPoint=null;
      showEmptyPanel();
    } else if(mode==='feed') {
      openPoint=null;
      showFeed();
    } else if(openPoint) {
      showPoint(openPoint,false);
    } else {
      showEmptyPanel();
    }
    updateUrl({replace:true});
  }

  function setLayout(next,{persist=true}={}){
    layout=next;
    if(persist) localStorage.setItem('node06-layout',layout);
    shell.dataset.layout=layout;
    controls.querySelectorAll('[data-layout]').forEach(b=>b.classList.toggle('active',b.dataset.layout===layout));
  }

  function showEmptyPanel(){
    panel.hidden=false;
    panelBody.innerHTML=`<div class="panel-empty"><div class="eyebrow">${lang==='ru'?'ТОЧКА':'POINT'}</div><p>${lang==='ru'?'Выберите сферу. В режиме чтения текст появится здесь; в исследовании карта останется без текста.':'Select a sphere. Reading mode opens its text here; Explore keeps the field text-free.'}</p></div>`;
  }

  function showPoint(point,push=true){
    if(!point) return;
    openPoint=point;
    panel.hidden=false;
    panelBody.innerHTML=`
      <div class="eyebrow">ROOT POINT · ${escapeHtml(point.id)}</div>
      <div class="point-text">${point.html}</div>
      <section>
        <h2>LINKS</h2>
        <ul class="links-list">${point.links.map(id=>{
          const target=byId.get(id);
          return target?`<li><a class="point-link" href="/${target.lang}/?p=${encodeURIComponent(target.id)}&open=${encodeURIComponent(target.id)}" data-point-id="${escapeHtml(target.id)}">${escapeHtml(target.preview)}</a></li>`:'';
        }).join('')}</ul>
      </section>
      <p class="meta">created ${point.created_at.slice(0,10)} · last interaction ${point.last_interaction_at.slice(0,10)} · ${point.degree} links</p>`;
    if(push) updateUrl();
  }

  function showFeed(){
    const sorted=[...local].sort((a,b)=>b.last_interaction_at.localeCompare(a.last_interaction_at));
    panel.hidden=false;
    panelBody.innerHTML=`<div class="eyebrow">${lang==='ru'?'ЛЕНТА / ПОСЛЕДНИЕ ИЗМЕНЕНИЯ':'FEED / LATEST CHANGES'}</div>
      <ul class="feed-list">${sorted.map(p=>`<li><time>${p.last_interaction_at.slice(0,10)}</time><a href="/${lang}/?p=${encodeURIComponent(p.id)}" data-feed-id="${escapeHtml(p.id)}">${escapeHtml(p.preview)}</a><span>${p.degree} links</span></li>`).join('')}</ul>`;
  }

  function focusPoint(point,{fromUser=true}={}){
    if(!point) return;
    center=point;
    document.getElementById('field-center-id').textContent=center.id;
    renderMap();
    if(mode==='read') showPoint(point,false);
    else if(mode==='explore') showEmptyPanel();
    else showFeed();
    if(fromUser) updateUrl();
  }

  panelClose.addEventListener('click',()=>{
    openPoint=null;
    if(mode==='feed') showFeed(); else showEmptyPanel();
    updateUrl();
  });

  panelBody.addEventListener('click',e=>{
    const pointLink=e.target.closest('a.point-link');
    if(pointLink){
      const target=byId.get(pointLink.dataset.pointId);
      if(!target) return;
      e.preventDefault();
      center=target;
      renderMap();
      showPoint(target);
      return;
    }
    const feedLink=e.target.closest('a[data-feed-id]');
    if(feedLink){
      const target=byId.get(feedLink.dataset.feedId);
      if(!target) return;
      e.preventDefault();
      focusPoint(target);
    }
  });

  controls.addEventListener('click',e=>{
    const modeButton=e.target.closest('[data-mode]');
    if(modeButton){setMode(modeButton.dataset.mode);return;}
    const layoutButton=e.target.closest('[data-layout]');
    if(layoutButton){setLayout(layoutButton.dataset.layout);return;}
    const viewButton=e.target.closest('[data-view]');
    if(viewButton){
      if(viewButton.dataset.view==='reset'){rotX=-0.28;rotY=0.55;zoom=1;renderMap();}
      if(viewButton.dataset.view==='left'){rotY-=0.18;renderMap();}
      if(viewButton.dataset.view==='right'){rotY+=0.18;renderMap();}
      if(viewButton.dataset.view==='up'){rotX-=0.18;renderMap();}
      if(viewButton.dataset.view==='down'){rotX+=0.18;renderMap();}
    }
  });

  function fibonacciSphere(arr,radius,depth,phase=0){
    const map=new Map();
    const n=Math.max(1,arr.length);
    const golden=Math.PI*(3-Math.sqrt(5));
    arr.forEach((p,i)=>{
      const y=1-(i/(Math.max(1,n-1)))*2;
      const rr=Math.sqrt(Math.max(0,1-y*y));
      const theta=golden*i+phase;
      map.set(p.id,{x:Math.cos(theta)*rr*radius,y:y*radius,z:Math.sin(theta)*rr*radius,depth});
    });
    return map;
  }

  function rotate(v){
    const cy=Math.cos(rotY),sy=Math.sin(rotY),cx=Math.cos(rotX),sx=Math.sin(rotX);
    const x1=v.x*cy+v.z*sy;
    const z1=-v.x*sy+v.z*cy;
    const y2=v.y*cx-z1*sx;
    const z2=v.y*sx+z1*cx;
    return {x:x1,y:y2,z:z2};
  }

  function project(v,w,h){
    const rv=rotate(v);
    const camera=760;
    const scale=(camera/(camera-rv.z))*zoom;
    return {x:w/2+rv.x*scale,y:h/2+rv.y*scale,z:rv.z,scale};
  }

  function renderMap(){
    const d1=center.links.map(id=>byId.get(id)).filter(Boolean);
    const d1ids=new Set(d1.map(p=>p.id));
    const d2ids=new Set();
    d1.forEach(p=>p.links.forEach(id=>{if(id!==center.id&&!d1ids.has(id)) d2ids.add(id);}));
    const d2=[...d2ids].map(id=>byId.get(id)).filter(Boolean);

    const w=1000,h=650;
    const basePos=new Map([[center.id,{x:0,y:0,z:0,depth:0}]]);
    for(const [id,v] of fibonacciSphere(d1,175,1,-0.7)) basePos.set(id,v);
    for(const [id,v] of fibonacciSphere(d2,310,2,0.9)) basePos.set(id,v);

    const visible=[center,...d1,...d2];
    const visibleIds=new Set(visible.map(p=>p.id));
    const projected=new Map([...basePos].map(([id,v])=>[id,project(v,w,h)]));
    const edgeKeys=new Set(),edges=[];
    visible.forEach(p=>p.links.forEach(q=>{
      if(!visibleIds.has(q)) return;
      const key=[p.id,q].sort().join('|');
      if(edgeKeys.has(key)) return;
      edgeKeys.add(key);edges.push([p.id,q]);
    }));

    const radius=p=>Math.max(10,Math.min(42,10+Math.sqrt(Math.max(0,p.degree))*7));
    const svgNS='http://www.w3.org/2000/svg';
    const svg=document.createElementNS(svgNS,'svg');
    svg.setAttribute('viewBox',`0 0 ${w} ${h}`);
    svg.setAttribute('aria-label','Rotatable point field');
    const defs=document.createElementNS(svgNS,'defs');
    defs.innerHTML='<radialGradient id="sphere" cx="35%" cy="30%" r="70%"><stop offset="0%" stop-color="#e2f0f5"/><stop offset="28%" stop-color="#9eb9c4"/><stop offset="70%" stop-color="#405463"/><stop offset="100%" stop-color="#18232d"/></radialGradient>';
    svg.appendChild(defs);

    // Colored orientation axes. They are view aids only; social coordinates come later.
    const axes=[
      {a:{x:0,y:0,z:0},b:{x:330,y:0,z:0},cls:'axis axis-0'},
      {a:{x:0,y:0,z:0},b:{x:-330,y:0,z:0},cls:'axis axis-1'},
      {a:{x:0,y:0,z:0},b:{x:0,y:330,z:0},cls:'axis axis-2'},
      {a:{x:0,y:0,z:0},b:{x:0,y:-330,z:0},cls:'axis axis-3'},
      {a:{x:0,y:0,z:0},b:{x:0,y:0,z:330},cls:'axis axis-4'},
      {a:{x:0,y:0,z:0},b:{x:0,y:0,z:-330},cls:'axis axis-5'}
    ];
    axes.forEach(axis=>{
      const A=project(axis.a,w,h),B=project(axis.b,w,h);
      const l=document.createElementNS(svgNS,'line');
      l.setAttribute('x1',A.x);l.setAttribute('y1',A.y);l.setAttribute('x2',B.x);l.setAttribute('y2',B.y);l.setAttribute('class',axis.cls);svg.appendChild(l);
    });

    edges.forEach(([a,b])=>{
      const A=projected.get(a),B=projected.get(b);if(!A||!B)return;
      const l=document.createElementNS(svgNS,'line');l.setAttribute('x1',A.x);l.setAttribute('y1',A.y);l.setAttribute('x2',B.x);l.setAttribute('y2',B.y);l.setAttribute('class','edge');svg.appendChild(l);
    });

    visible.slice().sort((a,b)=>projected.get(a.id).z-projected.get(b.id).z).forEach(p=>{
      const P=projected.get(p.id),g=document.createElementNS(svgNS,'g');
      g.setAttribute('class','node'+(p.id===center.id?' center':''));
      g.dataset.id=p.id;
      const c=document.createElementNS(svgNS,'circle');
      c.setAttribute('cx',P.x);c.setAttribute('cy',P.y);c.setAttribute('r',radius(p)*Math.max(.72,Math.min(1.35,P.scale)));
      g.appendChild(c);
      g.addEventListener('mouseenter',()=>{card.hidden=false;card.innerHTML=`${escapeHtml(p.preview)}<span class="id">${escapeHtml(p.id)} · ${p.degree} links</span>`;});
      g.addEventListener('mousemove',e=>{const r=host.getBoundingClientRect();card.style.left=Math.min(e.clientX-r.left+16,r.width-360)+'px';card.style.top=Math.max(8,e.clientY-r.top+16)+'px';});
      g.addEventListener('mouseleave',()=>card.hidden=true);
      g.addEventListener('click',e=>{e.stopPropagation();if(moved)return;focusPoint(p);});
      svg.appendChild(g);
    });
    host.replaceChildren(svg);
    document.getElementById('field-center-id').textContent=center.id;
  }

  host.addEventListener('pointerdown',e=>{
    if(e.button!==0) return;
    dragging=true;moved=false;lastX=e.clientX;lastY=e.clientY;host.setPointerCapture(e.pointerId);host.classList.add('dragging');
  });
  host.addEventListener('pointermove',e=>{
    if(!dragging) return;
    const dx=e.clientX-lastX,dy=e.clientY-lastY;
    if(Math.abs(dx)+Math.abs(dy)>2) moved=true;
    rotY+=dx*0.008;rotX+=dy*0.008;
    rotX=Math.max(-1.45,Math.min(1.45,rotX));
    lastX=e.clientX;lastY=e.clientY;renderMap();
  });
  host.addEventListener('pointerup',e=>{dragging=false;host.classList.remove('dragging');try{host.releasePointerCapture(e.pointerId);}catch(_){}});
  host.addEventListener('wheel',e=>{e.preventDefault();zoom=Math.max(.65,Math.min(1.7,zoom*(e.deltaY>0?.92:1.08)));renderMap();},{passive:false});

  document.addEventListener('keydown',e=>{
    if(['INPUT','TEXTAREA'].includes(document.activeElement?.tagName)) return;
    let changed=true;
    if(e.key==='ArrowLeft'||e.key==='a') rotY-=0.12;
    else if(e.key==='ArrowRight'||e.key==='d') rotY+=0.12;
    else if(e.key==='ArrowUp'||e.key==='w') rotX-=0.12;
    else if(e.key==='ArrowDown'||e.key==='s') rotX+=0.12;
    else if(e.key==='q') zoom=Math.max(.65,zoom*.92);
    else if(e.key==='e') zoom=Math.min(1.7,zoom*1.08);
    else changed=false;
    if(changed){e.preventDefault();renderMap();}
  });

  setLayout(layout,{persist:false});
  controls.querySelectorAll('[data-mode]').forEach(b=>b.classList.toggle('active',b.dataset.mode===mode));
  renderMap();
  if(mode==='feed') showFeed();
  else if(mode==='read'&&openPoint) showPoint(openPoint,false);
  else if(mode==='read'&&params.get('p')) showPoint(center,false);
  else showEmptyPanel();

  addEventListener('popstate',()=>{
    const q=new URLSearchParams(location.search);
    const nextCenter=byId.get(q.get('p'));
    if(nextCenter&&nextCenter.lang===lang) center=nextCenter;
    openPoint=byId.get(q.get('open'))||null;
    renderMap();
    if(mode==='feed') showFeed(); else if(mode==='read'&&openPoint) showPoint(openPoint,false); else showEmptyPanel();
  });
})();
