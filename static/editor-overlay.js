/* Draft over every map. External publication is explicitly confirmed on the trusted host. */
'use strict';
(() => {
  const body=document.body;if(body.dataset.page!=='field')return;
  let dialog,frame,channel,returnPath,timeout,opener,peerOrigin;
  const own=body.dataset.hosted==='true'&&!body.dataset.searchSite&&body.dataset.managementOrigin===location.origin;
  function remove(){clearTimeout(timeout);timeout=null;dialog?.close();dialog?.remove();dialog=null;frame=null;opener?.focus();}
  function offerDiscard(force=false){
    if(dialog.querySelector('.editor-discard'))return;
    const row=document.createElement('div');row.className='editor-discard';
    const warning=document.createElement('p');warning.textContent='Close editor and discard the local draft? A pending publication may already have succeeded.';
    for(const [label,discard] of [['Keep editing',false],['Discard draft',true]]){
      const button=document.createElement('button');button.type='button';button.textContent=label;
      button.addEventListener('click',()=>{row.remove();if(discard){if(force)remove();else frame.contentWindow.postMessage({protocol:'node06-editor/1',channel,kind:'close-discard'},peerOrigin);}});row.append(button);
    }
    row.prepend(warning);dialog.prepend(row);
  }
  function requestClose(){
    if(!dialog||timeout)return;
    if(!frame){remove();return;}
    frame.contentWindow.postMessage({protocol:'node06-editor/1',channel,kind:'close-request'},peerOrigin);
    timeout=setTimeout(()=>{timeout=null;if(!own){offerDiscard(true);return;}if(confirm('Editor is not responding. Close it and discard any unsaved text?'))remove();},2000);
  }
  async function open(url,source){
    if(dialog)return;
    opener=source;channel=crypto.randomUUID().replaceAll('-','');
    returnPath=url.searchParams.get('return_to')||window.node06ReturnPath?.()||'/';
    if(!/^(?:\/|\/sites\/s_[0-9a-f]{32}\/)$/.test(returnPath))returnPath='/';
    dialog=document.createElement('dialog');dialog.id='point-editor-overlay';dialog.setAttribute('aria-label','Point editor');
    const head=document.createElement('div');head.className='editor-overlay-heading';
    const title=document.createElement('span');title.textContent='Point editor';
    const close=document.createElement('button');close.type='button';close.textContent='×';close.setAttribute('aria-label','Close editor');close.addEventListener('click',requestClose);
    head.append(title,close);dialog.append(head);body.append(dialog);dialog.addEventListener('cancel',event=>{event.preventDefault();requestClose();});dialog.showModal();
    const current=dialog;
    try {
      if(!own){
        const config=await window.node06EditorConnection();if(dialog!==current)return;
        if(!config||url.searchParams.has('p'))throw new Error('EXTERNAL_EDIT_UNAVAILABLE');
        const from=url.searchParams.get('from');
        url=new URL(`/compose/v1/${config.siteId}/`,config.embedOrigin);
        if(from)url.searchParams.set('from',from);
        url.searchParams.set('parent_origin',location.origin);
      }
      peerOrigin=url.origin;url.searchParams.set('return_to',returnPath);url.searchParams.set('editor_channel',channel);
      frame=document.createElement('iframe');frame.title='Point editor';frame.src=url.href;dialog.append(frame);
    } catch(_) {
      if(dialog!==current)return;
      const p=document.createElement('p');p.textContent='Editor unavailable. Close and retry, or open the trusted editor: ';
      const a=document.createElement('a');a.href=source.href;a.textContent='Open editor';a.target='_blank';a.rel='noopener noreferrer';p.append(a);dialog.append(p);
    }
  }
  document.addEventListener('click',event=>{
    if(event.defaultPrevented||event.button!==0||event.ctrlKey||event.metaKey||event.shiftKey||event.altKey)return;
    const link=event.target.closest('a');if(!link)return;
    const url=new URL(link.href), management=window.node06ManagementOrigin?.()||body.dataset.managementOrigin;
    if(url.origin!==management||url.pathname!=='/editor/')return;
    event.preventDefault();void open(url,link);
  });
  window.addEventListener('message',async event=>{
    const message=event.data;
    if(!frame||event.origin!==peerOrigin||event.source!==frame.contentWindow||message?.protocol!=='node06-editor/1'||message.channel!==channel)return;
    clearTimeout(timeout);timeout=null;
    if(message.kind==='close-dirty')offerDiscard();
    if(message.kind==='close-cancel'&&!own&&!dialog.querySelector('.editor-close-status')){
      const p=document.createElement('p');p.className='editor-close-status';p.setAttribute('role','status');p.textContent='Close the publication confirmation window first, then close the editor.';dialog.prepend(p);
    }
    if(message.kind==='closed')remove();
    if(message.kind==='published'&&/^p_[0-9a-f]{32}$/.test(message.id||'')){
      // Stay on the original static site/full iframe, never follow a child-supplied URL.
      const path=own?returnPath:body.dataset.fieldPath||'/';
      const href=path+'?'+new URLSearchParams({p:message.id,open:message.id});remove();location.assign(href);
    }
  });
})();
