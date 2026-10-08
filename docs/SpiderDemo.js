let paused=false,index=0;
const cards=[...document.querySelectorAll('article')];
const ui=new GemSpiderUI({onPause:()=>{paused=!paused;ui.update({paused});},onClose:()=>{paused=true;ui.destroy();}});
function step(){if(paused||document.hidden)return;const visible=cards.filter(c=>{const r=c.getBoundingClientRect();return r.top>0&&r.top<innerHeight-150;});if(!visible.length)return;const card=visible[index%visible.length];ui.go(card.getBoundingClientRect(),'Demo · following the evidence');ui.update({read:++index,leads:0,status:'Playground only. No data is collected.'});}
step();setInterval(step,3500);
