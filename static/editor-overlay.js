/* Same-origin authenticated editor only. External embeds keep trusted navigation. */
"use strict";
(() => {
  const body=document.body;
  if(body.dataset.page!=="field"||body.dataset.hosted!=="true"||body.dataset.searchSite||body.dataset.managementOrigin!==location.origin)return;
  let dialog,frame,channel,returnPath,timeout,opener;
  function remove(){clearTimeout(timeout);dialog?.close();dialog?.remove();dialog=null;frame=null;opener?.focus();}
  function requestClose(){
    if(!dialog||timeout)return;
    frame.contentWindow.postMessage({protocol:'node06-editor/1',channel,kind:'close-request'},location.origin);
    timeout=setTimeout(()=>{timeout=null;if(confirm('Editor is not responding. Close it and discard any unsaved text?'))remove();},2000);
  }
  function open(url,source){
    if(dialog)return;
    opener=source;channel=crypto.randomUUID().replaceAll('-','');
    returnPath=url.searchParams.get('return_to')||window.node06ReturnPath?.()||'/';
    if(!/^(?:\/|\/sites\/s_[0-9a-f]{32}\/)$/.test(returnPath))returnPath='/';
    url.searchParams.set('return_to',returnPath);url.searchParams.set('editor_channel',channel);
    dialog=document.createElement('dialog');dialog.id='point-editor-overlay';dialog.setAttribute('aria-label','Point editor');
    const head=document.createElement('div');head.className='editor-overlay-heading';
    const title=document.createElement('span');title.textContent='Point editor';
    const close=document.createElement('button');close.type='button';close.textContent='×';close.setAttribute('aria-label','Close editor');close.addEventListener('click',requestClose);
    head.append(title,close);frame=document.createElement('iframe');frame.title='Point editor';frame.src=url.href;
    dialog.append(head,frame);body.append(dialog);dialog.addEventListener('cancel',event=>{event.preventDefault();requestClose();});dialog.showModal();
  }
  document.addEventListener('click',event=>{
    if(event.defaultPrevented||event.button!==0||event.ctrlKey||event.metaKey||event.shiftKey||event.altKey)return;
    const link=event.target.closest('a');if(!link)return;
    const url=new URL(link.href);if(url.origin!==location.origin||url.pathname!=='/editor/')return;
    event.preventDefault();open(url,link);
  });
  window.addEventListener('message',event=>{
    const message=event.data;
    if(!dialog||event.origin!==location.origin||event.source!==frame.contentWindow||message?.protocol!=='node06-editor/1'||message.channel!==channel)return;
    clearTimeout(timeout);timeout=null;
    if(message.kind==='closed')remove();
    if(message.kind==='published'&&/^p_[0-9a-f]{32}$/.test(message.id)){
      const href=returnPath+'?'+new URLSearchParams({p:message.id,open:message.id});remove();location.assign(href);
    }
  });
})();
