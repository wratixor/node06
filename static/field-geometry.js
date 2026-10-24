/* Anonymous geometry in hosted, embedded and static fields; no private state. */
"use strict";
(() => {
  if(document.body.dataset.page!=="field")return;
  let ids=[],ticket=0,timer;
  const status=document.createElement("p"), label=document.createElement("span"), refresh=document.createElement("button");
  status.className="field-geometry-status";label.setAttribute("role","status");refresh.type="button";refresh.textContent="↻";refresh.title="Refresh geometry";refresh.setAttribute("aria-label","Refresh geometry");
  status.append(label);
  const controls=document.getElementById("field-controls");if(controls)controls.append(refresh);
  refresh.id="field-refresh";
  async function load(){
    const sequence=++ticket, targets=[...ids];
    if(!targets.length||!window.readNode06Public||!window.applyNode06Geometry)return;
    const host=document.getElementById("field-map");if(!status.isConnected)host.before(status);
    if(targets.length>1024){label.textContent="Geometry capacity exceeded; current layout retained.";return;}
    refresh.disabled=true;label.textContent="Geometry: loading…";
    try{
      let snapshot,records=[],pending=false;
      // Do not mix runs, silently truncate a field, or accept stale center responses.
      for(let i=0;i<targets.length;i+=64){
        const group=targets.slice(i,i+64),result=await window.readNode06Public("points.geometry",{point_ids:group});
        if(sequence!==ticket)return;
        if(result.schema!=="node06-geometry/1"||!Array.isArray(result.items)||result.items.length!==group.length||
          result.items.some(row=>!group.includes(row.id))||new Set(result.items.map(row=>row.id)).size!==result.items.length)throw new Error("INVALID_RESPONSE");
        if(i&&result.snapshot_id!==snapshot)throw new Error("SNAPSHOT_CHANGED");
        snapshot=result.snapshot_id;records.push(...result.items);pending ||= result.pending||result.items.some(row=>row.pending);
      }
      window.applyNode06Geometry(records);
      label.textContent=pending?"Geometry: recalculation pending.":"";
    }catch(_){if(sequence===ticket)label.textContent="Geometry unavailable; layout retained.";}
    finally{if(sequence===ticket)refresh.disabled=false;}
  }
  window.addEventListener("node06:field",event=>{ids=event.detail.ids;++ticket;clearTimeout(timer);timer=setTimeout(load,120);});
  refresh.addEventListener("click",load);
  window.addEventListener("node06:reaction",()=>void load());
  window.addEventListener("focus",()=>{if(status.getClientRects().length)void load();});
  ids=[...document.querySelectorAll("#field-map .node")].map(node=>node.dataset.id);if(ids.length)void load();
})();
