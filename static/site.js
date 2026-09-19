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

  function closePanel(){
    openPoint=null;
    panel.hidden=true;
    host.focus({preventScroll:true});
    updateUrl();
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

  panelClose.addEventListener('click',closePanel);

  panelBody.addEventListener('click',e=>{
    const pointLink=e.target.closest('a.point-link');
    if(pointLink){
      const target=byId.get(pointLink.dataset.pointId);
      if(!target) return;
      e.preventDefault();
      focusPoint(target);
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

  function clamp(value,min,max){return Math.max(min,Math.min(max,value));}

  // Same six-component -> three opposed local axes idea as Hexrelatum.
  // Coordinates stay six-dimensional; projection only folds each opposed pair
  // into one local 3D axis for navigation.
  function relativeAxis(tp,tn,cp,cn){
    const numerator=tp*cn-tn*cp;
    const denominator=tp*cn+tn*cp;
    return denominator?numerator/denominator:0;
  }

  function sixToLocal(point,centre){
    if(point.id===centre.id) return {x:0,y:0,z:0};
    const t=point.coordinates||[1,1,1,1,1,1];
    const c=centre.coordinates||[1,1,1,1,1,1];
    return {
      x:relativeAxis(t[0],t[1],c[0],c[1]),
      y:relativeAxis(t[2],t[3],c[2],c[3]),
      z:relativeAxis(t[4],t[5],c[4],c[5])
    };
  }

  function normalize(v){
    const n=Math.hypot(v.x,v.y,v.z)||1;
    return {x:v.x/n,y:v.y/n,z:v.z/n,length:n};
  }

  function displayPosition(point,depth){
    if(depth===0) return {x:0,y:0,z:0,depth};
    const local=sixToLocal(point,center);
    const unit=normalize(local);
    // Unit sphere separates directly linked points from depth-2 points.
    // Local six-dimensional magnitude only modulates distance within each band.
    const magnitude=clamp(unit.length/1.45,0,1);
    const r=depth===1 ? 0.30+0.62*magnitude : 1.12+0.38*magnitude;
    return {x:unit.x*r,y:unit.y*r,z:unit.z*r,depth};
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
    const camera=3.9;
    const perspective=zoom/Math.max(2.1,camera-rv.z);
    const scale=Math.min(w,h)*2.02*perspective;
    return {x:w/2+rv.x*scale,y:h/2-rv.y*scale,z:rv.z,scale,perspective};
  }

  function pathFrom3D(points,w,h){
    return points.map((v,i)=>{
      const p=project(v,w,h);
      return `${i?'L':'M'}${p.x.toFixed(2)},${p.y.toFixed(2)}`;
    }).join(' ');
  }

  function addWireSphere(svg,w,h){
    const ns='http://www.w3.org/2000/svg';
    const addPath=(points,cls)=>{
      const path=document.createElementNS(ns,'path');
      path.setAttribute('d',pathFrom3D(points,w,h));
      path.setAttribute('class',cls);
      path.setAttribute('fill','none');
      svg.appendChild(path);
    };
    const steps=72;
    // Latitude rings.
    [-0.75,-0.5,-0.25,0,0.25,0.5,0.75].forEach(y=>{
      const rr=Math.sqrt(1-y*y);
      const pts=[];
      for(let i=0;i<=steps;i++){
        const a=i/steps*Math.PI*2;
        pts.push({x:Math.cos(a)*rr,y,z:Math.sin(a)*rr});
      }
      addPath(pts,'unit-sphere-grid');
    });
    // Longitude rings.
    for(let ring=0;ring<8;ring++){
      const phi=ring/8*Math.PI;
      const pts=[];
      for(let i=0;i<=steps;i++){
        const a=i/steps*Math.PI*2;
        const x=Math.cos(a)*Math.cos(phi);
        const z=Math.cos(a)*Math.sin(phi);
        const y=Math.sin(a);
        pts.push({x,y,z});
      }
      addPath(pts,'unit-sphere-grid');
    }
    // Equator/boundary emphasis.
    const eq=[];
    for(let i=0;i<=steps;i++){
      const a=i/steps*Math.PI*2;
      eq.push({x:Math.cos(a),y:0,z:Math.sin(a)});
    }
    addPath(eq,'unit-sphere-boundary');
  }

  function renderMap(){
    // A language is a separate root-point family. Cross-language links remain
    // part of the graph but do not duplicate a sphere in the current field.
    const inCurrentLanguage=id=>{
      const point=byId.get(id);
      return point&&point.lang===lang?point:null;
    };
    const d1=center.links.map(inCurrentLanguage).filter(Boolean);
    const d1ids=new Set(d1.map(p=>p.id));
    const d2ids=new Set();
    d1.forEach(p=>p.links.forEach(id=>{if(id!==center.id&&!d1ids.has(id)) d2ids.add(id);}));
    const d2=[...d2ids].map(inCurrentLanguage).filter(Boolean);

    const w=1000,h=650;
    const basePos=new Map([[center.id,{x:0,y:0,z:0,depth:0}]]);
    d1.forEach(p=>basePos.set(p.id,displayPosition(p,1)));
    d2.forEach(p=>basePos.set(p.id,displayPosition(p,2)));

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

    const radius=p=>Math.max(9,Math.min(38,9+Math.sqrt(Math.max(0,p.degree))*6));
    const svgNS='http://www.w3.org/2000/svg';
    const svg=document.createElementNS(svgNS,'svg');
    svg.setAttribute('viewBox',`0 0 ${w} ${h}`);
    svg.setAttribute('aria-label','Rotatable six-component point field');
    const defs=document.createElementNS(svgNS,'defs');
    defs.innerHTML='<radialGradient id="sphere" cx="35%" cy="30%" r="70%"><stop offset="0%" stop-color="#e2f0f5"/><stop offset="28%" stop-color="#9eb9c4"/><stop offset="70%" stop-color="#405463"/><stop offset="100%" stop-color="#18232d"/></radialGradient>';
    svg.appendChild(defs);

    addWireSphere(svg,w,h);

    // Three opposed pairs, six components. Colors intentionally match Hexrelatum:
    // cyan <-> red, magenta <-> green, yellow <-> blue.
    const axes=[
      {v:{x:-1.48,y:0,z:0},color:'#00d2dc',name:'x-'},{v:{x:1.48,y:0,z:0},color:'#ee484a',name:'x+'},
      {v:{x:0,y:-1.48,z:0},color:'#d646d6',name:'y-'},{v:{x:0,y:1.48,z:0},color:'#3ece70',name:'y+'},
      {v:{x:0,y:0,z:-1.48},color:'#f0cd2c',name:'z-'},{v:{x:0,y:0,z:1.48},color:'#4170ee',name:'z+'}
    ];
    const origin=project({x:0,y:0,z:0},w,h);
    axes.forEach(axis=>{
      const B=project(axis.v,w,h);
      const l=document.createElementNS(svgNS,'line');
      l.setAttribute('x1',origin.x);l.setAttribute('y1',origin.y);l.setAttribute('x2',B.x);l.setAttribute('y2',B.y);
      l.setAttribute('class','axis');l.setAttribute('stroke',axis.color);l.dataset.axis=axis.name;svg.appendChild(l);
      const dot=document.createElementNS(svgNS,'circle');
      dot.setAttribute('cx',B.x);dot.setAttribute('cy',B.y);dot.setAttribute('r','4.2');dot.setAttribute('fill',axis.color);dot.setAttribute('class','axis-tip');svg.appendChild(dot);
    });

    edges.forEach(([a,b])=>{
      const A=projected.get(a),B=projected.get(b);if(!A||!B)return;
      const da=basePos.get(a)?.depth||0,db=basePos.get(b)?.depth||0;
      const l=document.createElementNS(svgNS,'line');
      l.setAttribute('x1',A.x);l.setAttribute('y1',A.y);l.setAttribute('x2',B.x);l.setAttribute('y2',B.y);
      l.setAttribute('class',Math.max(da,db)===2?'edge edge-outer':'edge');svg.appendChild(l);
    });

    visible.slice().sort((a,b)=>projected.get(a.id).z-projected.get(b.id).z).forEach(p=>{
      const P=projected.get(p.id),g=document.createElementNS(svgNS,'g');
      const depth=basePos.get(p.id)?.depth||0;
      g.setAttribute('class','node depth-'+depth+(p.id===center.id?' center':''));
      g.dataset.id=p.id;
      const c=document.createElementNS(svgNS,'circle');
      c.setAttribute('cx',P.x);c.setAttribute('cy',P.y);c.setAttribute('r',radius(p)*clamp(P.scale*2.5,.72,1.35));
      g.appendChild(c);
      g.addEventListener('mouseenter',()=>{card.hidden=false;card.innerHTML=`${escapeHtml(p.preview)}<span class="id">${escapeHtml(p.id)} · ${p.degree} links</span>`;});
      g.addEventListener('mousemove',e=>{const r=host.getBoundingClientRect();card.style.left=Math.min(e.clientX-r.left+16,r.width-360)+'px';card.style.top=Math.max(8,e.clientY-r.top+16)+'px';});
      g.addEventListener('mouseleave',()=>card.hidden=true);
      svg.appendChild(g);
    });
    host.replaceChildren(svg);
    document.getElementById('field-center-id').textContent=center.id;
  }

  let pointerTargetId=null;
  host.addEventListener('pointerdown',e=>{
    if(e.button!==0) return;
    const node=e.target.closest?.('.node');
    pointerTargetId=node?.dataset.id||null;
    dragging=true;moved=false;lastX=e.clientX;lastY=e.clientY;
    host.setPointerCapture(e.pointerId);host.classList.add('dragging');
  });
  host.addEventListener('pointermove',e=>{
    if(!dragging) return;
    const dx=e.clientX-lastX,dy=e.clientY-lastY;
    if(Math.abs(dx)+Math.abs(dy)>3) moved=true;
    if(moved){
      rotY+=dx*0.008;rotX=clamp(rotX+dy*0.008,-1.45,1.45);
      renderMap();
    }
    lastX=e.clientX;lastY=e.clientY;
  });
  host.addEventListener('pointerup',e=>{
    const id=pointerTargetId;
    dragging=false;host.classList.remove('dragging');
    try{host.releasePointerCapture(e.pointerId);}catch(_){}
    if(!moved&&id){
      const target=byId.get(id);
      if(target) focusPoint(target);
    }
    pointerTargetId=null;
  });
  host.addEventListener('pointercancel',()=>{dragging=false;moved=false;pointerTargetId=null;host.classList.remove('dragging');});
  host.addEventListener('wheel',e=>{e.preventDefault();zoom=clamp(zoom*(e.deltaY>0?.92:1.08),.65,1.7);renderMap();},{passive:false});

  document.addEventListener('keydown',e=>{
    if(['INPUT','TEXTAREA'].includes(document.activeElement?.tagName)) return;
    if(e.key==='Escape'&&!panel.hidden){
      e.preventDefault();
      closePanel();
      return;
    }
    let changed=true;
    if(e.key==='ArrowLeft'||e.code==='KeyA') rotY-=0.12;
    else if(e.key==='ArrowRight'||e.code==='KeyD') rotY+=0.12;
    else if(e.key==='ArrowUp'||e.code==='KeyW') rotX-=0.12;
    else if(e.key==='ArrowDown'||e.code==='KeyS') rotX+=0.12;
    else if(e.code==='KeyQ') zoom=Math.max(.65,zoom*.92);
    else if(e.code==='KeyE') zoom=Math.min(1.7,zoom*1.08);
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
