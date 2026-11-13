/* Display-only controls for the saved prediction formation map. */
(()=>{
'use strict';
const map=document.getElementById('ka-pace-board');
if(!map)return;
const tabs=[...map.querySelectorAll('[data-pace-stage]')];
const status=map.querySelector('#ka-pace-selected');
function resize(){
  try{window.parent.postMessage({isStreamlitMessage:true,type:'streamlit:setFrameHeight',
    height:Math.ceil(document.documentElement.getBoundingClientRect().height)},'*');}
  catch(_error){}
}
function activate(stage,focus){
  for(const button of tabs){
    const active=button.dataset.paceStage===stage;
    button.setAttribute('aria-selected',String(active));
    button.tabIndex=active?0:-1;
    const panel=map.querySelector('#ka-pace-scene-'+button.dataset.paceStage);
    if(panel)panel.hidden=!active;
    if(active&&focus)button.focus();
  }
  if(status)status.textContent='馬をタップすると馬名と位置予測を確認できます。';
  requestAnimationFrame(resize);
}
tabs.forEach((button,index)=>{
  button.addEventListener('click',()=>activate(button.dataset.paceStage,false));
  button.addEventListener('keydown',event=>{
    if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;
    event.preventDefault();
    const next=event.key==='Home'?0:event.key==='End'?tabs.length-1:
      (index+(event.key==='ArrowLeft'?-1:1)+tabs.length)%tabs.length;
    activate(tabs[next].dataset.paceStage,true);
  });
});
map.querySelectorAll('[data-pace-runner]').forEach(button=>{
  button.addEventListener('click',()=>{
    if(status)status.textContent=button.dataset.paceDescription || button.dataset.paceFullName || '位置予測未取得';
  });
});
})();
