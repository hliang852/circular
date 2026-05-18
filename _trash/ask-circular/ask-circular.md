# Ask Circular — removed feature

Keyword-based chatbot navigation bar. Removed from CA module per design decision.

## HTML (was at bottom of main, above </main>)

```html
<div class="chat-bar">
  <div class="chat-inner">
    <span class="chat-label">Ask Circular</span>
    <div class="chat-input-wrap">
      <div id="chatResponse" class="chat-response">
        <div id="chatLoading" class="cr-loading">Thinking…</div>
        <div id="chatText" class="cr-text"></div>
        <button id="chatJump" class="cr-jump" style="display:none"></button>
      </div>
      <input id="chatInput" class="chat-input" type="text" placeholder="e.g. Which stocks are buying below their VWAP? or Show me upcoming AGMs">
      <button class="chat-send" onclick="sendChat()">
        <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2L2 7l5 2 2 5z" stroke-linecap="round" stroke-linejoin="round"/></svg>
      </button>
    </div>
  </div>
</div>
```

## CSS

```css
.chat-bar{position:fixed;bottom:0;left:0;right:0;background:var(--sf);border-top:1px solid var(--bd);z-index:200;padding:12px 20px}
.chat-inner{max-width:1160px;margin:0 auto;display:flex;gap:10px;align-items:center}
.chat-input-wrap{flex:1;position:relative}
.chat-input{width:100%;background:var(--sf2);border:1px solid var(--bd2);border-radius:20px;color:var(--tx);font-size:13px;padding:9px 44px 9px 16px;font-family:var(--sans);outline:none;transition:border-color .15s}
.chat-input:focus{border-color:var(--accent)}.chat-input::placeholder{color:var(--tx3)}
.chat-send{position:absolute;right:6px;top:50%;transform:translateY(-50%);background:var(--accent);border:none;border-radius:50%;width:28px;height:28px;cursor:pointer;display:flex;align-items:center;justify-content:center}
.chat-send svg{color:#fff}
.chat-label{font-size:11px;color:var(--tx3);white-space:nowrap}
.chat-response{display:none;background:var(--sf2);border:1px solid var(--bd);border-radius:var(--rl);padding:12px 16px;margin-bottom:10px}
.chat-response.visible{display:block}
.cr-text{font-size:13px;color:var(--tx2);line-height:1.6;margin-bottom:8px}
.cr-jump{display:inline-flex;align-items:center;gap:6px;background:rgba(88,166,255,.12);border:1px solid rgba(88,166,255,.3);color:var(--accent);font-size:12px;font-weight:500;padding:5px 12px;border-radius:10px;cursor:pointer}
.cr-loading{display:none;font-size:12px;color:var(--tx3);font-style:italic}
.cr-loading.visible{display:block}
```

## JS

```js
const chatNav={
  'conviction buys':{view:'ideas',subtab:'cb',label:'Open Conviction Buys →'},
  'mandate renewer':{view:'ideas',subtab:'mr',label:'Open Mandate Renewers →'},
  'agm':{view:'calendar',label:'Open Calendar →'},
  'league':{view:'league',label:'Open League Table →'},
  'last session':{view:'lastsession',label:'Open Last Session →'},
  'tencent':{view:'stock',code:'00700',label:'View Tencent →'},
  'hsbc':{view:'stock',code:'00005',label:'View HSBC →'},
  'alibaba':{view:'stock',code:'09988',label:'View Alibaba →'},
  'vwap':{view:'ideas',subtab:'cb',label:'Open Conviction Buys →'},
};
async function sendChat(){
  const inp=document.getElementById('chatInput'),q=inp.value.trim();
  if(!q) return;
  const resp=document.getElementById('chatResponse'),loading=document.getElementById('chatLoading'),textEl=document.getElementById('chatText'),jump=document.getElementById('chatJump');
  resp.classList.add('visible');loading.classList.add('visible');textEl.textContent='';jump.style.display='none';
  await new Promise(r=>setTimeout(r,400));
  loading.classList.remove('visible');
  const ql=q.toLowerCase();
  let matched=null;
  for(const k of Object.keys(chatNav)){if(ql.includes(k)){matched=chatNav[k];break;}}
  textEl.textContent=matched?`Navigating you to the most relevant section for "${q}".`:`Try: "Conviction Buys", "Mandate Renewers", "AGM calendar", "League Table", or a stock name like "Tencent".`;
  if(matched){
    jump.textContent=matched.label;jump.style.display='inline-flex';
    jump.onclick=()=>{
      if(matched.view==='stock'&&matched.code){const s=league.find(r=>r.c===matched.code);if(s)goToStock(s.c,s.n);}
      else{const vbIdx={home:0,league:1,lastsession:2,ideas:3,calendar:4};const idx=vbIdx[matched.view];const btn=idx!==undefined?document.querySelectorAll('.vtog .vb')[idx]:null;switchView(matched.view,btn);if(matched.subtab){const ib=document.querySelectorAll('.ist-btn')[matched.subtab==='cb'?0:1];switchIdeasTab(matched.subtab,ib);}}
      window.scrollTo({top:0,behavior:'smooth'});
    };
  } else {jump.style.display='none';}
  inp.value='';
}
```
