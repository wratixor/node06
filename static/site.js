(async()=>{
  const body=document.body;
  if(!body||body.dataset.page!=='field') return;
  const res=await fetch('/data/points.json'+(body.dataset.viewSite?'?'+new URLSearchParams({site:body.dataset.viewSite}):''));
  if(!res.ok) throw new Error('Field unavailable ('+res.status+'). Reload to retry.');
  const all=await res.json();
  const byId=new Map(all.map(p=>[p.id,p]));
  // Static copies hydrate a requested public point through the anonymous bridge.
  // This also makes a freshly published post addressable without a static rebuild.
  const dynamicRequested=new URLSearchParams(location.search).get('p')||new URLSearchParams(location.search).get('open');
  function safeRemoteHtml(html){
    const template=document.createElement('template');template.innerHTML=html;
    const allowed=new Set(['P','BR','EM','STRONG','CODE','PRE','A','UL','OL','LI','BLOCKQUOTE','H1','H2','H3','H4','HR']);
    function copy(source){
      if(source.nodeType===Node.TEXT_NODE)return document.createTextNode(source.textContent);
      if(source.nodeType!==Node.ELEMENT_NODE||!allowed.has(source.tagName))return document.createTextNode(source.textContent||'');
      const node=document.createElement(source.tagName);
      if(source.tagName==='A'){
        const pid=source.dataset.pointId;
        if(/^[a-z0-9][a-z0-9_-]{0,95}$/.test(pid||'')){
          node.dataset.pointId=pid;node.className='point-link';node.href=(body.dataset.fieldPath||'/')+'?'+new URLSearchParams({p:pid,open:pid});
        }else{try{const url=new URL(source.getAttribute('href'));if(['https:','http:'].includes(url.protocol)){node.href=url.href;node.target='_blank';node.rel='noopener noreferrer';}}catch{ /* Plain text for unsupported links. */ }}
      }
      node.append(...[...source.childNodes].map(copy));return node;
    }
    const box=document.createElement('div');box.append(...[...template.content.childNodes].map(copy));return box.innerHTML;
  }
  function mergePublic(point){
    if(!/^[a-z0-9][a-z0-9_-]{0,95}$/.test(point.id)||typeof point.html!=='string'||!Array.isArray(point.links))throw new Error('INVALID_POINT');
    const current=byId.get(point.id), value={coordinates:null,coordinate_source:'display-only',...current,...point,html:safeRemoteHtml(point.html),degree:point.degree??point.links.length};
    if(current)Object.assign(current,value);else{all.push(value);byId.set(point.id,value);}
  }
  if(body.dataset.hosted!=='true'&&/^[a-z0-9][a-z0-9_-]{0,95}$/.test(dynamicRequested||'')&&window.readNode06Public){
    try{
      const root=await window.readNode06Public('point.read',{point_id:dynamicRequested});mergePublic(root);
      const missing=root.links.filter(id=>!byId.has(id)).slice(0,50);
      for(let at=0;at<missing.length;at+=4){
        const results=await Promise.allSettled(missing.slice(at,at+4).map(point_id=>window.readNode06Public('point.read',{point_id})));
        for(const result of results)if(result.status==='fulfilled')mergePublic(result.value);else byId.get(root.id).neighbors_unavailable=true;
      }
    }catch{body.dataset.publicReadUnavailable='true';}
  }
  const geometryFallback=new Map(all.map(p=>[p.id,{coordinates:p.coordinates,coordinate_source:p.coordinate_source}]));
  let visibleSignature='';
  window.applyNode06Geometry = records => {
    for(const record of records){
      const point=byId.get(record.id);
      if(!point || record.revision_id!==point.revision_id || record.content_digest!==point.content_digest)continue;
      const valid=Array.isArray(record.coordinates)&&record.coordinates.length===6&&record.coordinates.every(v=>Number.isFinite(v)&&v>0)&&/^#[0-9a-f]{6}$/.test(record.color);
      if(record.coordinates!==null&&!valid)continue;
      Object.assign(point, valid?{coordinates:record.coordinates,coordinate_source:'opposite-pairs-v1',color:record.color}: {...geometryFallback.get(point.id),color:null});
      point.geometry_pending=record.pending;
    }
    if(openPoint){
      const heading=document.querySelector('#point-panel-body > .eyebrow');
      if(heading)heading.textContent=pointHeading(openPoint);
    }
    renderMap();
  };

  const params=new URLSearchParams(location.search);
  const fieldPath=body.dataset.fieldPath||'/';
  const requested=params.get('p')||params.get('open')||(body.dataset.homePage==='true'?'':body.dataset.homePoint);
  function preference(key,fallback){try{return localStorage.getItem(key)||fallback;}catch{return fallback;}}
  function remember(key,value){try{localStorage.setItem(key,value);}catch{/* Storage may be unavailable inside an iframe. */}}
  if(body.dataset.tenant){
    const theme=JSON.parse(body.dataset.theme||'{}');
    const colors={bg:'--bg',text:'--ink',accent:'--accent',panel:'--panel',border:'--line'};
    for(const [key,variable] of Object.entries(colors)){
      if(typeof theme[key]==='string'&&/^#([\da-f]{3}|[\da-f]{6})$/i.test(theme[key]))
        body.style.setProperty(variable,theme[key]);
    }
    if(Number.isInteger(theme.radius)&&theme.radius>=0&&theme.radius<=16)
      body.style.setProperty('--radius',theme.radius+'px');
    const fonts={system:'system-ui, sans-serif',serif:'Georgia, serif',mono:'ui-monospace, monospace'};
    if(Object.hasOwn(fonts,theme.font))body.style.fontFamily=fonts[theme.font];
    body.dataset.density=theme.density==='compact'?'compact':'normal';
  }
  const local=all;
  if(!local.length) return;

  const host=document.getElementById('field-map');
  const card=document.getElementById('hover-card');
  const panel=document.getElementById('point-panel');
  const panelBody=document.getElementById('point-panel-body');
  const panelClose=document.getElementById('point-panel-close');
  const controls=document.getElementById('field-controls');
  const shell=document.querySelector('.field-workspace');
  if(body.dataset.publicReadUnavailable==='true'&&byId.has(dynamicRequested)){
    const notice=document.createElement('p');notice.className='meta';notice.setAttribute('role','status');notice.textContent='Live data unavailable; showing saved roots.';shell.before(notice);
  }

  let center=byId.get(requested);
  if(!center) center=[...local].sort((a,b)=>b.degree-a.degree)[0];
  let openPoint=byId.get(params.get('open')||(!params.has('p')?body.dataset.homePoint:'')) || null;
  const startPage=document.getElementById('start-page');
  const rootField=document.getElementById('root-field');
  if(startPage){
    const hasPoint=byId.has(requested);
    startPage.hidden=hasPoint;rootField.hidden=!hasPoint;
    if(!hasPoint){
      if(requested){const error=document.createElement('p');error.textContent='Point unavailable: '+requested;startPage.prepend(error);}
      return;
    }
  }
  let mode=params.get('mode')||preference('node06-mode','read');
  let layout=preference('node06-layout','side');
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
    if(mode==='feed') q.set('mode','feed');
    const url=`${fieldPath}?${q.toString()}`;
    history[replace?'replaceState':'pushState']({},'',url);
  }

  function setMode(next,{persist=true}={}){
    mode=next;
    if(persist) remember('node06-mode',mode);
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
    if(persist) remember('node06-layout',layout);
    shell.dataset.layout=layout;
    controls.querySelectorAll('[data-layout]').forEach(b=>b.classList.toggle('active',b.dataset.layout===layout));
  }

  function showEmptyPanel(){
    panel.hidden=false;
    panelBody.innerHTML='<div class="panel-empty"><div class="eyebrow">POINT</div><p>Select a sphere. Reading mode opens its text here; Explore keeps the field text-free.</p></div>';
  }

  function pointHeading(point){
    return `${(point.origin||'root').toUpperCase()} POINT · ${point.id}${point.coordinate_source==='display-only'?' · DISPLAY LAYOUT ONLY':point.coordinate_source==='opposite-pairs-v1'?' · SOCIAL GEOMETRY':''}${point.geometry_pending?' · RECALCULATION PENDING':''}`;
  }
  function showPoint(point,push=true){
    if(!point) return;
    openPoint=point;
    panel.hidden=false;
    panelBody.innerHTML=`
      <div class="eyebrow">${escapeHtml(pointHeading(point))}</div>
      <div class="point-text" lang="${escapeHtml(point.lang||'und')}">${point.html}</div>
      <section>
        <h2>LINKS</h2>
        <ul class="links-list">${point.links.map(id=>{
          const target=byId.get(id);
          return target?`<li><a class="point-link" href="${fieldPath}?p=${encodeURIComponent(target.id)}&open=${encodeURIComponent(target.id)}" data-point-id="${escapeHtml(target.id)}">${escapeHtml(target.preview)}</a></li>`:'';
        }).join('')}</ul>
      </section>
      ${point.links_truncated?'<p class="meta">Only the first 50 links are shown.</p>':''}${point.neighbors_unavailable?'<p class="meta">Some linked points are unavailable.</p>':''}
      <p class="meta">created ${point.created_at.slice(0,10)} · last interaction ${point.last_interaction_at.slice(0,10)} · ${point.degree} links</p>`;
    document.querySelectorAll('.site-header nav a').forEach(link=>{
      const url=new URL(link.href);if(url.pathname==='/community/'){url.search=new URLSearchParams({p:point.id});link.href=url.href;}
    });
    body.dataset.currentPoint = point.id;
    body.dataset.currentRevision = point.revision_id || "";
    body.dataset.currentDigest = point.content_digest || "";
    window.dispatchEvent(new CustomEvent('node06:point', {detail:{id:point.id, revision_id:point.revision_id, content_digest:point.content_digest,author:point.author}}));
    if(push) updateUrl();
  }

  function showFeed(){
    panel.hidden=false;const container=document.createElement('div');panelBody.replaceChildren(container);
    if(window.renderNode06CreationFeed)window.renderNode06CreationFeed(container,{language:'en'});

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
    if(!point.coordinates||!centre.coordinates) return {x:0,y:0,z:0};
    const t=point.coordinates;
    const c=centre.coordinates;
    return {
      x:relativeAxis(t[0],t[1],c[0],c[1]),
      y:relativeAxis(t[2],t[3],c[2],c[3]),
      z:relativeAxis(t[4],t[5],c[4],c[5])
    };
  }

  function normalize(v){
    const length=Math.hypot(v.x,v.y,v.z),n=length||1;
    return {x:v.x/n,y:v.y/n,z:v.z/n,length};
  }

  function displayPosition(point,depth){
    if(depth===0) return {x:0,y:0,z:0,depth};
    const local=sixToLocal(point,center);
    let unit=normalize(local);
    if(unit.length<1e-9){
      // Equal semantic coordinates still describe different points. Give only
      // their display direction a stable fallback, without changing the seed.
      let hash=2166136261;
      for(const char of point.id) hash=Math.imul(hash^char.charCodeAt(0),16777619)>>>0;
      const angle=(hash/4294967296)*Math.PI*2;
      unit={x:Math.cos(angle),y:.35,z:Math.sin(angle),length:0};
      const length=Math.hypot(unit.x,unit.y,unit.z);
      unit.x/=length;unit.y/=length;unit.z/=length;
    }
    // Unit sphere separates directly linked points from depth-2 points.
    // Local six-dimensional magnitude only modulates distance within each band.
    const magnitude=clamp(unit.length/1.45,0,1);
    const r=depth===1 ? 0.30+0.62*magnitude : 1.12+0.38*magnitude;
    return {x:unit.x*r,y:unit.y*r,z:unit.z*r,depth,displayFallback:unit.length<1e-9};
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
    // Language is point metadata, never a partition of the shared graph.
    const d1=center.links.filter(id=>id!==center.id).map(id=>byId.get(id)).filter(Boolean);
    const d1ids=new Set(d1.map(p=>p.id));
    const d2ids=new Set();
    d1.forEach(p=>p.links.forEach(id=>{if(id!==center.id&&!d1ids.has(id)) d2ids.add(id);}));
    const d2=[...d2ids].map(id=>byId.get(id)).filter(Boolean);

    const w=1000,h=650;
    const basePos=new Map([[center.id,{x:0,y:0,z:0,depth:0}]]);
    d1.forEach(p=>basePos.set(p.id,displayPosition(p,1)));
    d2.forEach(p=>basePos.set(p.id,displayPosition(p,2)));
    const coincident=new Map();
    for(const [id,v] of basePos){
      if(v.depth===0) continue;
      const key=[v.depth,v.x.toFixed(6),v.y.toFixed(6),v.z.toFixed(6)].join('|');
      if(!coincident.has(key)) coincident.set(key,[]);
      coincident.get(key).push(id);
    }
    for(const ids of coincident.values()){
      if(ids.length<2) continue;
      ids.sort().forEach((id,index)=>{
        const v=basePos.get(id),radius=Math.hypot(v.x,v.y,v.z),u=normalize(v);
        const tangent=normalize(Math.abs(u.y)<.9?{x:-u.z,y:0,z:u.x}:{x:0,y:-u.z,z:u.y});
        const angle=(index-(ids.length-1)/2)*.16;
        basePos.set(id,{x:radius*(u.x*Math.cos(angle)+tangent.x*Math.sin(angle)),
          y:radius*(u.y*Math.cos(angle)+tangent.y*Math.sin(angle)),
          z:radius*(u.z*Math.cos(angle)+tangent.z*Math.sin(angle)),depth:v.depth});
      });
    }

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
      g.dataset.id=p.id;g.dataset.coordinateSource=p.coordinate_source||'seed';g.dataset.displayFallback=String(Boolean(basePos.get(p.id)?.displayFallback));g.dataset.geometryPending=String(Boolean(p.geometry_pending));
      const c=document.createElementNS(svgNS,'circle');
      c.setAttribute('cx',P.x);c.setAttribute('cy',P.y);c.setAttribute('r',radius(p)*clamp(P.scale*2.5,.72,1.35));
      if(/^#[0-9a-f]{6}$/.test(p.color||'')){
        const gradient=document.createElementNS(svgNS,'radialGradient'), gid='social-'+p.id;
        gradient.id=gid;gradient.setAttribute('cx','35%');gradient.setAttribute('cy','30%');gradient.setAttribute('r','70%');
        for(const [offset,color] of [['0%','#ffffff'],['38%',p.color],['100%','#101820']]){
          const stop=document.createElementNS(svgNS,'stop');stop.setAttribute('offset',offset);stop.setAttribute('stop-color',color);gradient.append(stop);
        }
        defs.append(gradient);c.style.fill=`url(#${gid})`;g.dataset.color=p.color;
      }
      const title=document.createElementNS(svgNS,'title');title.textContent=`${p.id} · ${p.coordinate_source||'seed'}${basePos.get(p.id)?.displayFallback?' · display direction fallback':''}${p.geometry_pending?' · recalculation pending':''}`;g.append(title);
      g.appendChild(c);
      g.addEventListener('mouseenter',()=>{card.hidden=false;card.innerHTML=`${escapeHtml(p.preview)}<span class="id">${escapeHtml(p.id)} · ${p.degree} links</span>`;});
      g.addEventListener('mousemove',e=>{const r=host.getBoundingClientRect();card.style.left=Math.min(e.clientX-r.left+16,r.width-360)+'px';card.style.top=Math.max(8,e.clientY-r.top+16)+'px';});
      g.addEventListener('mouseleave',()=>card.hidden=true);
      svg.appendChild(g);
    });
    host.replaceChildren(svg);
    document.getElementById('field-center-id').textContent=center.id;
    const signature=center.id+'|'+visible.map(p=>p.id).sort().join(',');
    if(signature!==visibleSignature){visibleSignature=signature;window.dispatchEvent(new CustomEvent('node06:field',{detail:{ids:visible.map(p=>p.id)}}));}
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
    if(document.querySelector('#point-picker:not([hidden])')) return;
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

  updateUrl({replace:true});
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
    if(startPage){startPage.hidden=Boolean(nextCenter);rootField.hidden=!nextCenter;}
    if(!nextCenter) return;
    center=nextCenter;
    openPoint=byId.get(q.get('open'))||null;
    renderMap();
    if(mode==='feed') showFeed(); else if(mode==='read'&&openPoint) showPoint(openPoint,false); else showEmptyPanel();
  });
})().catch(error=>{
  const message=document.createElement('p');message.setAttribute('role','alert');
  message.textContent=error.message||'Field unavailable';
  (document.querySelector('main')||document.body).prepend(message);
});
