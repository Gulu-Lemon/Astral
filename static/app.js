// Astral v0.6 Client
var COLORS=['#58a6ff','#f0883e','#2ea043','#a371f7','#db61a2','#56d4dd','#f85149','#f7b73f','#8b949e','#3fb950','#e553b2','#79c0ff'];
function el(s){return document.querySelector(s)}
function bind(s,e,f){var node=document.querySelector(s);if(node)node.addEventListener(e,f)}

var S={inPrologue:false,prologueStep:0,playersTurn:true,dialogueWith:null,npcData:[],_scene:'tianji_maze',_selectedCard:null,_cards:[],_cardWatch:null,debug:false};

// ====== INIT ======
document.addEventListener('DOMContentLoaded',function(){
  if(window.location.search.includes('debug=1')) S.debug = true;

  // Tab switching
  document.querySelectorAll('.tab-btn').forEach(function(b){
    b.addEventListener('click',function(){switchTab(b.dataset.tab)});
  });

  bind('#btn-send','click',function(){if(S.customAction){var e=document.createEvent('Event');e.initEvent('keydown',true,true);e.key='Enter';document.querySelector('#input-message').dispatchEvent(e)}else{sendDialogue()}});
  bind('#input-message','keydown',function(e){
    if(e.key==='Enter'){
      if(S.customAction){
        var msg=el('#input-message').value.trim();if(!msg)return;
         el('#input-message').value='';showLoading(true,'处理中...');
         fetch('/api/investigate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:msg})})
           .then(function(r){return r.json()}).then(function(d){
             addLog('narrative',d.description||'（自由行动）');
             el('#dialogue-box').style.display='none';S.customAction=false;nextRound();
           }).catch(function(){showLoading(false);el('#action-bar').innerHTML='<button class="action-btn" onclick="nextRound()">继续</button>';el('#action-bar').style.display=''});
      }else{sendDialogue()}
    }
  });
  bind('#btn-close-dialogue','click',closeDialogue);
  bind('#btn-save','click',showSaves);
  bind('#btn-save-manual','click',doSaveManual);
  bind('#btn-settings','click',function(){switchTab('settings')});
  bind('#btn-cfg-save','click',saveSettings);
  bind('#btn-cfg-test','click',testAPIConnectionFromSettings);
  bind('#btn-settings-close','click',restoreGameUI);
  bind('#btn-newgame','click',newGameConfirm);
  bind('#btn-close-save','click',function(){el('#save-panel').style.display='none'});
  bind('.panel-overlay','click',function(){el('#save-panel').style.display='none'});
  bind('#trial-proceed-btn','click',trialProceed);
  bind('#trial-vote-btn','click',trialVote);
  bind('#btn-vote-submit','click',submitVote);
  bind('#btn-vote-cancel','click',function(){el('#vote-panel').style.display='none'});
  document.querySelectorAll('.panel-tab').forEach(function(b){b.addEventListener('click',function(){switchPanelTab(b.dataset.panel)})});
  bind('#btn-skip','click',doSkipTime);
  bind('#btn-sleep','click',doSleep);
  bind('#ev-add-btn','click',addEvidenceItem);
  bind('#ev-input','keydown',function(e){if(e.key==='Enter')addEvidenceItem()});
  bind('#prologue-btn','click',prologueSubmit);
  bind('#prologue-field','keydown',function(e){if(e.key==='Enter')prologueSubmit()});
  document.querySelectorAll('.choice-btn').forEach(function(b){b.addEventListener('click',function(){prologueChoose(b.dataset.mode)})});
  bind('#btn-new-card','click',showCardEditor);
  bind('#btn-import-card','click',showImportDialog);
  bind('#btn-card-save','click',saveCardFromEditor);
  bind('#btn-card-cancel','click',hideCardEditor);
  bind('#btn-import-confirm','click',doImportCard);
  bind('#btn-import-cancel','click',hideImportDialog);
  bind('#import-card-file','change',handleImportFile);

  fetch('/api/scenes').then(function(r){return r.json()}).then(function(data){
    var list=el('#scene-list');
    if(!list)return;
    list.innerHTML=data.scenes.map(function(s){return '<div class="scene-card" onclick="useScene(\''+s.id+'\')"><div class="scene-name">'+s.name+'</div><div class="scene-desc">'+(s.desc||'')+'</div></div>'}).join('');
  });

  initCardWatch();

  // 直接获取卡片列表（SSE 回退）
  fetch('/api/cards').then(function(r){return r.json()}).then(function(d){
    if(!S._cards||S._cards.length===0){
      S._cards=d.cards||[];
      renderCardList(S._cards);
    }
  });

  fetch('/api/profiles').then(function(r){return r.json()}).then(function(pd){
    if((pd.profiles||[]).length===0||!pd.active){
      setTimeout(function(){switchTab('settings')},300);
    }else if(pd.active){
      testAPIConnectionFromSettings();
    }
  });

  fetch('/api/state').then(function(r){return r.json()}).then(function(s){
    if(s.player_created&&s.prologue_step>=7){
      hideMainTabs();
      if(s.scene_name)el('#scene-label').textContent=s.scene_name;
      renderNPCs(s.npcs);updateInfo(s);
    }else if(s.player_created&&s.prologue_step>0&&s.prologue_step<7){
      hideMainTabs();
      S.inPrologue=true;S.prologueStep=s.prologue_step;
      el('#prologue-screen').style.display='block';
      if(s.prologue_step>=4){
        addPrologueText('(继续游戏)');
        prologueContinue('继续探索');
      }else{
        addPrologueText('(续)');el('#prologue-field').placeholder='按确定...';el('#prologue-btn').textContent='继续';
        el('#prologue-field').dataset.step=String(s.prologue_step);el('#prologue-input').style.display='flex';
      }
    }else{
      switchTab('cards');
    }
  });
});

function hideMainTabs(){
  el('#main-tabs').style.display='none';
  el('#card-manager').style.display='none';
  el('#scene-screen').style.display='none';
  el('#settings-tab').style.display='none';
}

function restoreGameUI(){
  el('#settings-tab').style.display='none';
  el('#npc-panel').style.display='block';
  el('#map-strip').style.display='flex';
  el('#story-log').style.display='block';
  el('#action-bar').style.display='';
}

// ====== TAB SWITCH ======
function switchTab(tab){
  document.querySelectorAll('.tab-btn').forEach(function(b){b.classList.toggle('active',b.dataset.tab===tab)});
  el('#card-manager').style.display=tab==='cards'?'flex':'none';
  el('#scene-screen').style.display=tab==='scene'?'block':'none';
  el('#settings-tab').style.display=tab==='settings'?'block':'none';
  el('#prologue-screen').style.display='none';
  // 若游戏中打开设置，隐藏游戏 UI；关闭设置时恢复
  var inGame=el('#npc-panel').style.display!=='none';
  if(tab==='settings'&&inGame){
    el('#npc-panel').style.display='none';el('#map-strip').style.display='none';
    el('#story-log').style.display='none';el('#action-bar').style.display='none';
    el('#trial-banner').style.display='none';
  }
  if(tab==='cards'||tab==='scene'){
    el('#npc-panel').style.display='none';el('#map-strip').style.display='none';
    el('#story-log').style.display='none';el('#action-bar').style.display='none';
  }
  if(tab==='scene'){
    fetch('/api/scenes').then(function(r){return r.json()}).then(function(d){
      var list=el('#scene-list');if(!list)return;
      list.innerHTML=d.scenes.map(function(s){return '<div class="scene-card'+(S._scene===s.id?' current':'')+'" onclick="useScene(\''+s.id+'\')"><div class="scene-name">'+s.name+'</div><div class="scene-desc">'+(s.desc||'')+'</div></div>'}).join('');
    });
  }
  if(tab==='settings'){
    loadProfiles();
  }
}

function closeMainTabsAndShowPrologue(){
  hideMainTabs();
  el('#prologue-screen').style.display='block';
}

// ====== CARD WATCH (SSE hot reload) ======
function initCardWatch(){
  if(S._cardWatch){S._cardWatch.close();S._cardWatch=null}
  try {
    S._cardWatch = new EventSource('/api/cards/watch');
    S._cardWatch.addEventListener('cards_updated', function(e){
      try {
        var data = JSON.parse(e.data);
        S._cards = data.cards || [];
        renderCardList(S._cards);
        if(S._selectedCard){
          var found = S._cards.find(function(c){return c.name===S._selectedCard.name});
          if(!found){S._selectedCard=null;showCardPreviewEmpty()}
          else{S._selectedCard=found;showCardPreview()}
        }
      }catch(ex){}
    });
    // Fallback: handle messages without event type
    S._cardWatch.addEventListener('message', function(e){
      try {
        var data = JSON.parse(e.data);
        if(data.type==='cards_updated'){
          S._cards = data.cards || [];
          renderCardList(S._cards);
          if(S._selectedCard){
            var found = S._cards.find(function(c){return c.name===S._selectedCard.name});
            if(!found){S._selectedCard=null;showCardPreviewEmpty()}
            else{S._selectedCard=found;showCardPreview()}
          }
        }
      }catch(ex){}
    });
    S._cardWatch.onerror = function(){
      setTimeout(initCardWatch, 5000);
    };
  }catch(e){
    setTimeout(initCardWatch, 5000);
  }
}

// ====== CARD LIST ======
function renderCardList(cards){
  var list = el('#card-file-list');
  var count = el('#card-count');
  if(!list)return;
  if(!cards||cards.length===0){
    list.innerHTML='<div style="padding:12px;font-size:12px;color:var(--text2);">暂无角色卡</div>';
    if(count)count.textContent='0 张卡片';
    return;
  }
  list.innerHTML=cards.map(function(c,i){
    var active=S._selectedCard&&S._selectedCard.name===c.name?' active':'';
    var magicShort=c.magic?c.magic.replace(/\n/g,' ').substring(0,40):'';
    if(magicShort.length>=40)magicShort+='...';
    return '<div class="card-file-item'+active+'" onclick="selectCard('+i+')" ondblclick="useCard()">'
      +'<div class="cfi-name">'+escHtml(c.name)+'</div>'
      +'<div class="cfi-meta">'+(c.age||'?')+'岁 · '+escHtml(magicShort||'（无描述）')+'</div>'
      +'</div>';
  }).join('');
  if(count)count.textContent=cards.length+' 张卡片';
}

function selectCard(idx){
  if(idx>=0&&idx<S._cards.length){
    S._selectedCard=S._cards[idx];
    renderCardList(S._cards);
    showCardPreview();
  }
}

function escHtml(s){return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}

// ====== CARD PREVIEW ======
function showCardPreview(){
  var panel=el('#card-preview');
  if(!panel||!S._selectedCard)return;
  var c=S._selectedCard;
  var html='';
  html+='<div class="card-preview-header">';
  html+='<h2>'+escHtml(c.name)+'</h2>';
  html+='<div class="card-preview-meta">';
  html+='<span>'+escHtml(c.age||'?')+'岁</span>';
  html+='<span style="margin-left:8px;font-size:11px;color:var(--text2);">'+escHtml(c.filename||'')+'</span>';
  html+='</div>';
  html+='</div>';

  if(c.magic){
    html+='<div class="card-section"><h4>魔法</h4><div class="card-section-body">'+escHtml(c.magic)+'</div></div>';
  }
  if(c.appearance){
    html+='<div class="card-section"><h4>外貌</h4><div class="card-section-body">'+escHtml(c.appearance)+'</div></div>';
  }
  if(c.personality){
    var persText=c.personality;
    if(persText.length>500)persText=persText.substring(0,500)+'...';
    html+='<div class="card-section"><h4>性格</h4><div class="card-section-body">'+escHtml(persText)+'</div></div>';
  }
  if(c.background){
    var bgText=c.background;
    if(bgText.length>800)bgText=bgText.substring(0,800)+'...';
    html+='<div class="card-section"><h4>背景经历</h4><div class="card-section-body">'+escHtml(bgText)+'</div></div>';
  }
  if(c.dialogue_corpus){
    var dcText=c.dialogue_corpus;
    if(dcText.length>500)dcText=dcText.substring(0,500)+'...';
    html+='<div class="card-section"><h4>语料库</h4><div class="card-section-body">'+escHtml(dcText)+'</div></div>';
  }
  if(c.relationships){
    var relText=c.relationships;
    if(relText.length>300)relText=relText.substring(0,300)+'...';
    html+='<div class="card-section"><h4>重要关系</h4><div class="card-section-body">'+escHtml(relText)+'</div></div>';
  }
  if(c.boundaries){
    var bndText=c.boundaries;
    if(bndText.length>300)bndText=bndText.substring(0,300)+'...';
    html+='<div class="card-section"><h4>行为边界</h4><div class="card-section-body">'+escHtml(bndText)+'</div></div>';
  }
  var other=c.other_sections||{};
  var okeys=Object.keys(other);
  if(okeys.length>0){
    html+='<div class="card-section"><h4>其他</h4>';
    okeys.forEach(function(k){
      var oc=other[k]||'';
      if(oc.length>300)oc=oc.substring(0,300)+'...';
      html+='<div style="margin-bottom:8px;"><strong>'+escHtml(k)+'</strong></div><div class="card-section-body">'+escHtml(oc)+'</div>';
    });
    html+='</div>';
  }

  html+='<div class="card-preview-actions">';
  html+='<button class="mini-btn primary" onclick="editCard()">&#9998; 编辑</button>';
  html+='<button class="mini-btn danger" onclick="deleteCard()">&#128465; 删除</button>';
  html+='<button class="mini-btn accent" onclick="useCard()" style="background:var(--accent);color:#fff;">&#9654; 使用此卡开始</button>';
  html+='</div>';

  panel.innerHTML=html;
}

function showCardPreviewEmpty(){
  var panel=el('#card-preview');
  if(!panel)return;
  panel.innerHTML='<div class="card-preview-empty">'
    +'<div style="font-size:48px;margin-bottom:16px;">&#128196;</div>'
    +'<div>选择一张角色卡查看详情</div>'
    +'<div style="font-size:11px;color:var(--text2);margin-top:8px;">新建、导入或双击卡片使用</div>'
    +'</div>';
}

// ====== CARD CRUD ======
function editCard(){
  if(!S._selectedCard)return;
  showCardEditor();
}

function showCardEditor(){
  var card=S._selectedCard||{};
  el('#editor-title').textContent=card.name?'编辑角色卡 — '+card.name:'新建角色卡';
  el('#edit-name').value=card.name||'';
  el('#edit-age').value=card.age||'16';
  el('#edit-appearance').value=card.appearance||'';
  el('#edit-magic').value=card.magic||'';
  el('#edit-personality').value=(card.personality||'').length>200?card.personality.substring(0,200):(card.personality||'');
  el('#edit-raw-text').value=card.raw||'';
  el('#card-editor').style.display='block';
}
function hideCardEditor(){el('#card-editor').style.display='none'}

function saveCardFromEditor(){
  var name=el('#edit-name').value.trim();
  if(!name){alert('请输入名字');return}
  var body={name:name,age:el('#edit-age').value.trim(),appearance:el('#edit-appearance').value.trim(),magic:el('#edit-magic').value.trim(),personality:el('#edit-personality').value.trim(),raw_text:el('#edit-raw-text').value.trim()};
  fetch('/api/cards',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
    .then(function(r){return r.json()}).then(function(d){
      if(d.ok){hideCardEditor();S._selectedCard=null}
      else alert(d.error||'保存失败');
    });
}

function deleteCard(){
  if(!S._selectedCard)return;
  if(!confirm('确认删除角色卡 "'+S._selectedCard.name+'"？\n此操作不可撤销，将删除对应的 .txt 文件。'))return;
  var name=S._selectedCard.name;
  fetch('/api/cards/'+encodeURIComponent(name),{method:'DELETE'})
    .then(function(r){return r.json()}).then(function(d){
      if(!d.ok)alert('删除失败');
      S._selectedCard=null;
      showCardPreviewEmpty();
    });
}

function showImportDialog(){
  el('#import-card-text').value='';
  el('#import-card-file').value='';
  el('#import-card-status').style.display='none';
  el('#import-card-dialog').style.display='block';
}
function hideImportDialog(){el('#import-card-dialog').style.display='none'}

function handleImportFile(e){
  var file=e.target.files[0];
  if(!file)return;
  var reader=new FileReader();
  reader.onload=function(ev){
    el('#import-card-text').value=ev.target.result;
    el('#import-card-status').textContent='已加载: '+file.name;
    el('#import-card-status').style.display='block';
  };
  reader.readAsText(file,'UTF-8');
}

function doImportCard(){
  var text=el('#import-card-text').value.trim();
  if(!text){alert('请粘贴角色卡文本或选择文件');return}
  fetch('/api/cards',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:'_import_temp',age:'16',appearance:'',magic:'',personality:'',raw_text:text})})
    .then(function(r){return r.json()}).then(function(d){
      hideImportDialog();
      if(!d.ok&&d.error)alert('导入失败: '+d.error);
    });
}

function useCard(){
  if(!S._selectedCard)return;
  if(!S._scene||S._scene==='tianji_maze'){
    switchTab('scene');
    setTimeout(function(){alert('请先在上方选择场景，再使用角色卡。')},200);
    return;
  }
  startWithCard();
}

function useScene(sid){
  showLoading(true,'场景切换中...');
  S._scene=sid;
  fetch('/api/select_scene',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({scene_id:sid})})
    .then(function(r){return r.json()}).then(function(d){
      showLoading(false);
      if(d.ok){
        el('#scene-label').textContent=d.scene_name||sid;
        switchTab('cards');
      }
    });
}

// ====== START GAME ======
function startNewGame(){
  if(S._selectedCard){startWithCard();return}
  var name=el('#input-name')?el('#input-name').value.trim()||'玩家':'玩家';
  closeMainTabsAndShowPrologue();
  S.inPrologue=true;S.prologueStep=0;
  prologueStep1(name);
}

function startWithCard(){
  if(!S._selectedCard){startNewGame();return}
  var card=S._selectedCard;
  showLoading(true,'角色载入中...');
  closeMainTabsAndShowPrologue();
  S.inPrologue=true;S.prologueStep=0;
  clearPrologueText();

  // 镜像步骤：自动填入卡片的外貌
  fetch('/api/start_with_card',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({card_name:card.name})})
    .then(function(r){return r.json()}).then(function(d){
      showLoading(false);
      if(!d.ok){startNewGame();return}
      addPrologueText(d.intro_text+'\n\n你的能力: '+d.magic);
      // 不跳过难度选择
      el('#prologue-field').dataset.step='3';
      el('#prologue-input').style.display='none';
      el('#prologue-choices').style.display='flex';
    });
}

// ====== PROLOGUE ======
function showPrologueInput(p,btn){el('#prologue-input').style.display='flex';el('#prologue-choices').style.display='none';var f=el('#prologue-field');f.value='';f.placeholder=p;f.focus();if(btn)el('#prologue-btn').textContent=btn}
function hidePrologueInput(){el('#prologue-input').style.display='none';el('#prologue-choices').style.display='none'}
function addPrologueText(t){if(!t)return;var b=el('#prologue-text');b.innerHTML+=t+'<br>';b.scrollTop=b.scrollHeight}
function clearPrologueText(){el('#prologue-text').innerHTML=''}

function addRuleText(t){
  if(!t)return;
  var b=el('#prologue-text');
  var r=document.createElement('div');r.className='rule-box';r.textContent=t;
  b.appendChild(r);b.scrollTop=b.scrollHeight;
}

function prologueStep1(name){
  clearPrologueText();
  addPrologueText('你在陌生的房间中醒来。桌上有一面银框镜子，映出了你的模样。\n\n请描述你的外貌和年龄。');
  var f=el('#prologue-field');f.placeholder='外貌特征...';f.dataset.step='1a';f.dataset.name=name;el('#prologue-btn').textContent='下一步';f.value='';f.focus();
}

function prologueStep1b(){
  clearPrologueText();addPrologueText('请描述你的魔法能力。\n\n将手放在胸前，感受体内的力量……');
  el('#prologue-field').placeholder='我的魔法是...';el('#prologue-field').dataset.step='2';el('#prologue-btn').textContent='确定';
}

function prologueStep2(magic){
  hidePrologueInput();showLoading(true,'确认魔法中...');
  fetch('/api/prologue/magic',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({magic})})
    .then(function(r){return r.json()}).then(function(d){showLoading(false);addPrologueText(d.text);el('#prologue-field').dataset.step='3';el('#prologue-input').style.display='none';el('#prologue-choices').style.display='flex'});
}

function prologueChoose(mode){
  document.querySelectorAll('.choice-btn').forEach(function(b){b.classList.remove('selected')});
  document.querySelector('.choice-btn[data-mode="'+mode+'"]').classList.add('selected');
  hidePrologueInput();showLoading(true,'确认难度...');
  fetch('/api/prologue/difficulty',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mode})})
    .then(function(r){return r.json()}).then(function(d){showLoading(false);addPrologueText(d.text);setTimeout(function(){prologueStep4()},800)});
}

function prologueStep4(){
  showLoading(true,'生成场景...');
  fetch('/api/prologue/camp').then(function(r){return r.json()}).then(function(d){
    showLoading(false);
    addPrologueText(d.text);
    if(d.options&&d.options.length>0){
      showPrologueOptions(d.options);
    }else{
      prologueContinue(d.text||'');
    }
  });
}

function prologueSubmit(){
  var f=el('#prologue-field');var step=f.dataset.step;var val=f.value.trim();
  if(!val)return;
  if(step==='1a'){
    S.prologueStep=1;f.dataset.step='1b';f.dataset.appear=val;f.value='';
    showLoading(true,'确认外貌中...');
    var name=f.dataset.name||'无名';
    fetch('/api/prologue/mirror',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:name,age:'18',appearance:val})})
      .then(function(r){return r.json()}).then(function(d){showLoading(false);addPrologueText(d.text);prologueStep1b()});
  }else if(step==='1b'){
    f.dataset.magic=val;f.value='';f.dataset.step='2';hidePrologueInput();prologueStep2(val);
  }else if(step==='2'){
    prologueStep2(val);
  }
}

function showPrologueOptions(options){
  var container=el('#prologue-choices');
  container.innerHTML=options.map(function(o,i){
    var label=['A','B','C','D'][i]||String(i+1);
    return '<button class="prologue-option-btn" onclick="prologueFromOption(\''+(o.label||o).replace(/'/g,"&#39;")+'\',\''+label+'\')"><span class="opt-label">'+label+'.</span> '+escHtml(o.label||o)+'</button>';
  }).join('');
  container.style.display='flex';
}

function prologueFromOption(choice,label){
  hidePrologueInput();
  showLoading(true,'处理中...');
  fetch('/api/prologue/continue',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({choice:choice})})
    .then(function(r){return r.json()}).then(function(d){
      showLoading(false);
      if(d.error){addPrologueText('[错误] '+d.error);return}
      if(d.finished){prologueFinish()}else{
        addPrologueText(d.text);
        if(d.rule){addRuleText(d.rule)}
        if(d.options&&d.options.length>0){showPrologueOptions(d.options)}
        else{prologueContinue(d.text||'')}
      }
    });
}
function prologueContinue(text){
  fetch('/api/prologue/continue',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({choice:text})})
    .then(function(r){return r.json()}).then(function(d){
      if(d.error){addPrologueText('[错误] '+d.error);return}
      if(d.finished){prologueFinish()}else{
        addPrologueText(d.text);
        if(d.rule){addRuleText(d.rule)}
        if(d.options&&d.options.length>0){showPrologueOptions(d.options)}
        else{prologueContinue(d.text||'')}
      }
    });
}

function prologueFinish(){
  showLoading(true,'完成序章...');
  fetch('/api/prologue/finish',{method:'POST'}).then(function(r){return r.json()}).then(function(d){
    fetch('/api/state').then(function(r){return r.json()}).then(function(s){
      showLoading(false);
      S.inPrologue=false;
      el('#prologue-screen').style.display='none';
      hideMainTabs();
      el('#npc-panel').style.display='block';
      el('#map-strip').style.display='flex';
      el('#story-log').style.display='block';
      el('#action-bar').style.display='';
      if(s.scene_name)el('#scene-label').textContent=s.scene_name;
      addLog('narrative','序章结束。新的故事即将开始……');
      renderNPCs(s.npcs);updateInfo(s);
      nextRound();
    });
  });
}

// ====== NPC ======
function renderNPCs(npcs){
  var list=el('#npc-list');if(!list)return;
  list.innerHTML=npcs.map(function(n){
    var aff=n.affection||50;var affLabel=getAffectionLabel(aff);var affW=aff+'%';
    var near=n.nearby?'<span class="nearby-marker">&#9679; 附近</span>':'';
    var emotion=n.emotion||'';
    var deadStyle=!n.alive?'style="opacity:.3"':'';
    return '<div class="npc-card" onclick="S.npcDialogue=true;talkToNPC(\''+escHtml(n.agent_id)+'\')" '+deadStyle+'>'
      +'<div class="npc-name">'+escHtml(n.name)+' '+near+'</div>'
      +(emotion?'<div class="npc-emotion">'+escHtml(emotion)+'</div>':'')
      +'<div class="npc-location">'+escHtml(n.location||'')+'</div>'
      +'<div class="aff-bar"><div class="aff-fill" style="width:'+affW+'"></div></div>'
      +'<div class="aff-label">'+affLabel+' ('+aff+')</div></div>';
  }).join('');
}

function getAffectionLabel(v){
  if(v>=80)return '恋人';if(v>=60)return '知己';if(v>=50)return '友人';
  if(v>=40)return '相识';if(v>=30)return '陌生';if(v>=20)return '冷淡';
  if(v>=10)return '敌对';return '仇恨';
}

// ====== GAME LOOP ======
function nextRound(keepLog){
  showLoading(true,'推演中...');
  var es=new EventSource('/api/round');
  es.addEventListener('round_start',function(e){});
  es.addEventListener('agent_done',function(e){
    try{var d=JSON.parse(e.data);el('#loading-progress').textContent='Agent '+d.completed+'/'+d.total;}catch(ex){}
  });
  es.addEventListener('arbiter_start',function(e){el('#loading-progress').textContent='仲裁中...'});
  es.addEventListener('arbiter_done',function(e){el('#loading-progress').textContent='叙述中...'});
  var _streamDiv=null;
  es.addEventListener('narrative_start',function(e){
    showLoading(false);
    _streamDiv=document.createElement('div');
    _streamDiv.className='log-block log-narrative';
    _streamDiv.style.whiteSpace='pre-wrap';_streamDiv.style.lineHeight='1.8';
    el('#story-log').appendChild(_streamDiv);
  });
  es.addEventListener('narrative_chunk',function(e){
    var d=JSON.parse(e.data);
    if(_streamDiv){_streamDiv.textContent+=d.text;el('#story-log').scrollTop=el('#story-log').scrollHeight}
  });
  es.addEventListener('options_start',function(e){
    el('#action-bar').innerHTML='<span style="color:var(--text2);font-size:12px;">正在生成选项……</span>';el('#action-bar').style.display='';
  });
  es.addEventListener('narrative_done',function(e){
    var d=JSON.parse(e.data);var t=d.text||'';
    if(_streamDiv){_streamDiv.textContent=t;_streamDiv=null}
    else{addLog('narrative',t)}
    renderOptions(d.options);
  });
  es.addEventListener('round_end',function(e){
    try{
      var d=JSON.parse(e.data);
      updateInfo(d);
      if(S.debug)renderDebugRulings(d);
      if(d.in_trial){
        fetch('/api/trial/state').then(function(r){return r.json()}).then(function(ts){
          if(ts.active){showTrialBanner(ts.victim_name||'?',ts.phase);_trialRemaining=ts.timer_remaining||60;}
        });
      }
    }catch(ex){}
    es.close();
  });
  es.addEventListener('npc_approaches',function(e){
    try{var d=JSON.parse(e.data);if(d.npcs){d.npcs.forEach(function(n){addLog('system',n.agent_name+'走向你，想与你交谈。')})}}catch(ex){}
  });
  es.onmessage=function(e){
    try{var d=JSON.parse(e.data);if(d.type==='error'){showLoading(false);addLog('system','推演出错：'+(d.message||''));try{es.close()}catch(ex){}}}catch(ex){}
  };
  es.addEventListener('error',function(e){
    showLoading(false);
    try{var d=JSON.parse(e.data);if(d.message){addLog('system','推演出错：'+d.message)}else{addLog('system','推演出错，请重试。')}}catch(ex){addLog('system','推演出错，请重试。')}
    try{es.close()}catch(ex){}
    el('#action-bar').innerHTML='<button class="action-btn" onclick="nextRound()">重试</button>';el('#action-bar').style.display='';
  });
}

function clearLog(){}

function renderOptions(options){
  el('#action-bar').innerHTML='';el('#action-bar').style.display='';
  
  // 审判调查阶段：添加证物输入
  fetch('/api/trial/state').then(function(r){return r.json()}).then(function(ts){
    if(ts.active&&ts.phase==='investigation'){
      var evWrap=document.createElement('span');
      evWrap.className='ev-add-wrap';
      evWrap.innerHTML='<input id="ev-input" placeholder="添加证物..." maxlength="100"><button id="ev-add-btn">保存</button>';
      el('#action-bar').appendChild(evWrap);
      bind('#ev-add-btn','click',addEvidenceItem);
      bind('#ev-input','keydown',function(e){if(e.key==='Enter')addEvidenceItem()});
    }
  });
  if(!options||!options.length){
    ['继续观察周围','与附近的人交谈','探索这个区域','（自定义行动）'].forEach(function(l,i){
      var btn=document.createElement('button');btn.className='action-btn';
      btn.textContent=l;
      btn.onclick=function(){
        document.querySelectorAll('.action-btn').forEach(function(b){b.disabled=true});
        var t=i<3?'investigate':'custom';doStructured({label:l,type:t,target:null,room:null});hideActionBar();
        if(t!=='custom')showLoading(true,'推演中...');
      };
      el('#action-bar').appendChild(btn);
    });
    return;
  }
  options.forEach(function(o){
    var btn=document.createElement('button');btn.className='action-btn';
    btn.textContent=(o.label||o.text||'行动');
    btn.onclick=function(){
      if(o.type==='dialogue'){
        document.querySelectorAll('.action-btn').forEach(function(b){b.disabled=true});
      }
      doStructured(o);hideActionBar();
      if(o.type!=='dialogue'&&o.type!=='custom')showLoading(true,'推演中...');
    };
    el('#action-bar').appendChild(btn);
  });
}

function doStructured(o){
  if(!o||typeof o!=='object')return;
  var t=o.type||'';var target=o.target;var room=o.room;
  if(t==='dialogue'&&target){showLoading(false);S.npcDialogue=false;talkToNPC(target)}
  else if(t==='explore'&&room){exploreRoom(room)}
  else if(t==='investigate'&&o.label){doAction({action:o.label})}
  else if(t==='custom'){showLoading(false);S.customAction=true;el('#dialogue-box').style.display='block';el('#dialogue-target').textContent='自由行动';el('#dialogue-hints').innerHTML='';el('#input-message').value='';el('#input-message').placeholder='输入你想做的事情...';el('#input-message').focus()}
  else{nextRound()}
}

function hideActionBar(){el('#action-bar').innerHTML=''}
function updateInfo(s){
  if(s.day)el('#game-info').textContent='第'+s.day+'天 '+s.time+(s.location?' · '+s.location:'');
  if(s.phase)el('#difficulty-badge').textContent={blackout:'熄灯时刻',undercurrent:'暗流涌动',hunting:'猎杀时刻'}[s.phase]||s.phase;
  if(s.floor)el('#floor-badge').textContent='L'+s.floor;
  if(s.npcs)renderNPCs(s.npcs);
  if(s.scene_name)el('#scene-label').textContent=s.scene_name;
  // Show skip/sleep when game is active
  var inGame=!S.inPrologue&&s.day;
  el('#btn-skip').style.display=inGame?'inline-block':'none';
  el('#btn-sleep').style.display=inGame?'inline-block':'none';
}

// ====== DIALOGUE ======
function talkToNPC(aid){
  el('#dialogue-box').style.display='block';
  S.dialogueWith=aid;
  el('#dialogue-target').textContent='与 '+aid+' 对话';
  el('#dialogue-hints').innerHTML='<span style="color:var(--text2);font-size:11px;">正在生成对话建议……</span>';
  fetch('/api/dialogue_suggestions',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({agent_id:aid})})
    .then(function(r){return r.json()}).then(function(d){
      var hints=el('#dialogue-hints');
      if(d.suggestions&&d.suggestions.length>0){
        hints.innerHTML=d.suggestions.map(function(s){return '<button class="hint-chip" onclick="sendSuggestion(\''+s.replace(/'/g,"&#39;")+'\')">'+escHtml(s)+'</button>'}).join('');
      }else{hints.innerHTML=''}
    });
  el('#input-message').focus();
}

function sendSuggestion(msg){el('#input-message').value=msg;sendDialogue()}
function sendDialogue(){
  var aid=S.dialogueWith;if(!aid)return;
  var msg=el('#input-message').value.trim();if(!msg)return;
  el('#input-message').value='';
  S.dialogueWith=null;
  el('#dialogue-box').style.display='none';
  addLog('dialogue','你：'+msg);
  var ph=document.createElement('div');ph.className='log-block log-system';ph.id='_reply_ph';ph.textContent='互动中……';el('#story-log').appendChild(ph);el('#story-log').scrollTop=el('#story-log').scrollHeight;
  fetch('/api/dialogue',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({agent_id:aid,message:msg})})
    .then(function(r){return r.json()}).then(function(d){
      var p=el('#_reply_ph');if(p)p.remove();
      if(d.ok){addLog('dialogue',d.agent_name+'：'+d.response);fetch('/api/state').then(function(r){return r.json()}).then(function(s){renderNPCs(s.npcs)})}
      else{alert(d.error||'对话失败')}
      nextRound();
    });
}
function closeDialogue(){el('#dialogue-box').style.display='none';S.dialogueWith=null;S.customAction=false;S.npcDialogue=false}

// ====== EXPLORE / INVESTIGATE ======
function exploreRoom(room){
  return fetch('/api/explore',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({room:room})})
    .then(function(r){return r.json()}).then(function(d){
      if(d.ok){addLog('narrative',d.description);renderMap(d);nextRound()}
      else{alert(d.error||'移动失败');el('#action-bar').innerHTML='<button class="action-btn" onclick="nextRound()">继续</button>';el('#action-bar').style.display='';showLoading(false)}
    });
}

function doAction(data){
  return fetch('/api/investigate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)})
    .then(function(r){return r.json()}).then(function(d){
      if(d.ok){addLog('narrative',d.description);nextRound()}
      else{alert(d.error||'行动失败');el('#action-bar').innerHTML='<button class="action-btn" onclick="nextRound()">继续</button>';el('#action-bar').style.display='';showLoading(false)}
    });
}

// ====== TRIAL ======
function showTrialBanner(victim,phase){
  el('#trial-banner').style.display='flex';
  el('#trial-info').textContent='魔女审判 — 被害者：'+victim;
  highlightTrialPhase(phase);
  if(phase==='investigation'||phase==='court_debate'){
    startTrialTimer(phase);
  }
  renderEvidencePanel();
  el('#panel-tab-ev').style.display='inline-block';
}

function hideTrialBanner(){
  el('#trial-banner').style.display='none';
  stopTrialTimer();
}

function highlightTrialPhase(phase){
  document.querySelectorAll('.trial-phase-tag').forEach(function(t){
    t.classList.toggle('active',t.dataset.phase===phase);
  });
}

var _trialTimer=null;
var _trialRemaining=0;

function startTrialTimer(phase){
  stopTrialTimer();
  el('#trial-timer').style.display='inline';
  _trialTimer=setInterval(function(){
    if(_trialRemaining<=0){
      el('#trial-timer').textContent='0:00';
      el('#trial-timer').className='critical';
      return;
    }
    _trialRemaining--;
    var m=Math.floor(_trialRemaining/60);
    var s=_trialRemaining%60;
    el('#trial-timer').textContent=m+':'+(s<10?'0':'')+s;
    if(_trialRemaining<=60) el('#trial-timer').className='warning';
    if(_trialRemaining<=15) el('#trial-timer').className='critical';
  },1000);
}

function stopTrialTimer(){
  if(_trialTimer){clearInterval(_trialTimer);_trialTimer=null;}
  el('#trial-timer').style.display='none';
  el('#trial-timer').className='';
}

function trialProceed(){
  showLoading(true,'推进审判...');
  fetch('/api/trial/proceed',{method:'POST'}).then(function(r){return r.json()}).then(function(d){
    showLoading(false);
    if(!d.ok){alert(d.error||'推进失败');return;}
    if(d.phase==='court_statement'){
      addLog('trial',d.text||'');
      highlightTrialPhase('court_statement');
    }else if(d.phase==='court_debate'){
      addLog('trial',d.text||'');
      highlightTrialPhase('court_debate');
      if(d.stream_url) startDebateStream(d.stream_url);
    }else if(d.phase==='execution'){
      addLog('execution',d.text||'');
      hideTrialBanner();
      nextRound();
    }
  }).catch(function(){showLoading(false);});
}

function startDebateStream(url){
  showLoading(true,'辩论中...');
  var es=new EventSource(url);
  var _debateDiv=null;
  es.addEventListener('narrative_chunk',function(e){
    showLoading(false);
    try{
      var d=JSON.parse(e.data);
      if(!_debateDiv){
        _debateDiv=document.createElement('div');
        _debateDiv.className='log-block log-narrative';
        _debateDiv.style.whiteSpace='pre-wrap';
        el('#story-log').appendChild(_debateDiv);
      }
      _debateDiv.textContent+=d.text;
      el('#story-log').scrollTop=el('#story-log').scrollHeight;
    }catch(ex){}
  });
  es.addEventListener('error',function(e){
    showLoading(false);
    try{es.close()}catch(ex){}
    el('#trial-proceed-btn').disabled=false;
  });
  es.onmessage=function(e){
    try{es.close()}catch(ex){}
    // SSE done - check results via state
    updateTrialState();
  };
}

function updateTrialState(){
  fetch('/api/trial/state').then(function(r){return r.json()}).then(function(d){
    if(!d.active){hideTrialBanner();return;}
    highlightTrialPhase(d.phase);
    if(d.timer_remaining>0) _trialRemaining=d.timer_remaining;
    renderEvidencePanel();
  });
}

function trialVote(){
  fetch('/api/trial/state').then(function(r){return r.json()}).then(function(d){
    if(!d.active)return;
    fetch('/api/state').then(function(r2){return r2.json()}).then(function(s){
      var npcs=s.npcs||[];
      var html='';
      npcs.forEach(function(n){
        if(!n.alive||n.agent_id===d.victim_id)return;
        html+='<div class="vote-choice" data-aid="'+n.agent_id+'" onclick="selectVoteTarget(this)"><span class="vc-name">'+escHtml(n.name||n.agent_id)+'</span><span class="vc-id">'+n.agent_id+'</span></div>';
      });
      el('#vote-choices').innerHTML=html;
      el('#vote-panel').style.display='block';
      S._voteTarget=null;
    });
  });
}

function selectVoteTarget(el2){
  document.querySelectorAll('.vote-choice').forEach(function(c){c.classList.remove('selected')});
  el2.classList.add('selected');
  S._voteTarget=el2.dataset.aid;
}

function submitVote(){
  if(!S._voteTarget){alert('请选择嫌疑犯');return;}
  fetch('/api/trial/vote',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({vote_for:S._voteTarget,reason:el('#vote-reason').value.trim()})
  }).then(function(r){return r.json()}).then(function(d){
    el('#vote-panel').style.display='none';
    if(d.ok){
      addLog('trial','投票结果：'+d.text);
      if(d.phase==='execution'){addLog('execution',d.text||'');hideTrialBanner();nextRound();}
    }
  });
}

// ====== EVIDENCE ======
var S_evidenceTab='npc';
function switchPanelTab(tab){
  S_evidenceTab=tab;
  document.querySelectorAll('.panel-tab').forEach(function(b){b.classList.toggle('active',b.dataset.panel===tab)});
  el('#npc-list').style.display=tab==='npc'?'block':'none';
  el('#evidence-list').style.display=tab==='evidence'?'block':'none';
  if(tab==='evidence') renderEvidencePanel();
}

function renderEvidencePanel(){
  fetch('/api/trial/evidence').then(function(r){return r.json()}).then(function(d){
    var list=el('#evidence-list');
    var items=d.evidence||[];
    el('#ev-count').textContent='('+items.length+')';
    if(!items.length){list.innerHTML='<div style="font-size:11px;color:var(--text2);padding:8px;">（暂无证物）</div>';return;}
    list.innerHTML=items.map(function(e){
      var cls=e.is_key_evidence?' key':'';
      return '<div class="evidence-item'+cls+'"><div class="ev-name">'+escHtml(e.name)+'</div><div class="ev-meta">'+escHtml(e.location)+' &middot; '+escHtml(e.found_by||'未知')+'</div></div>';
    }).join('');
  });
}

function addEvidenceItem(){
  var desc=el('#ev-input').value.trim();
  if(!desc)return;
  el('#ev-input').value='';
  fetch('/api/trial/evidence/add',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({item:desc})})
    .then(function(r){return r.json()}).then(function(d){
      if(d.ok){
        addLog('system','证物：'+d.narrative);
        renderEvidencePanel();
      }else{alert(d.error||'添加证物失败')}
    });
}

// ====== MAP ======
function renderMap(data){
  var strip=el('#map-strip');if(!strip)return;
  strip.style.display='flex';
  var cars=data&&data.map_data?data.map_data.cars:(data&&data.cars?data.cars:[]);
  if(!cars||cars.length===0){strip.innerHTML='';return}
  strip.innerHTML=cars.map(function(car){
    var dots=car.rooms.map(function(r){
      var cls='map-dot';if(r===data.player_room||r===data.location)cls+=' player';else if(car.explored&&car.explored.indexOf(r)>=0)cls+=' explored';
      return '<span class="'+cls+'">'+r+'</span>';
    }).join('');
    var lock=car.locked?' <span style="color:var(--warn);">&#128274;</span>':'';
    return '<div class="map-car"><div class="map-car-label">L'+car.floor+lock+'</div>'+dots+'</div>';
  }).join('');
}

// ====== SAVE / LOAD ======
function showSaves(){
  el('#save-panel').style.display='block';
  renderSaveList();
}
function renderSaveList(){
  fetch('/api/slots').then(function(r){return r.json()}).then(function(d){
    var list=el('#save-slots');
    if(!list)return;
    var slots=d.slots||[];
    if(slots.length===0){
      list.innerHTML='<div style="font-size:12px;color:var(--text2);padding:8px;">（暂无存档）</div>';
      return;
    }
    var html='';
    slots.forEach(function(s){
      var icon=s.auto?'&#128194;':'&#128196;';
      var label=s.auto?'<span style="color:var(--accent2);font-size:10px;">自动</span>':'<span style="color:var(--text2);font-size:10px;">手动</span>';
      var ts=s.timestamp?s.timestamp.substring(0,16).replace('T',' '):'';
      var meta=[];
      if(s.description)meta.push(s.description);
      if(s.round_count)meta.push(s.round_count+'轮');
      meta.push(s.alive_count+'/'+s.total_npc+' NPC存活');
      html+='<div class="save-item">'
        +'<div class="save-item-info">'
        +'<div class="save-item-name">'+icon+' '+escHtml(s.filename)+' '+label+'</div>'
        +'<div class="save-item-meta">'+ts+' · '+meta.join(' · ')+'</div>'
        +'</div>'
        +'<div class="save-item-actions">'
        +'<button class="mini-btn" onclick="doLoadSave(\''+escJs(s.filename)+'\')">&#9654; 读取</button>'
        +(s.auto?'':'<button class="mini-btn danger" onclick="doDeleteSave(\''+escJs(s.filename)+'\')">&#10005;</button>')
        +'</div></div>';
    });
    list.innerHTML=html;
  });
}
function doSaveManual(){
  fetch('/api/save',{method:'POST'}).then(function(r){return r.json()}).then(function(d){
    if(d.ok){renderSaveList()}else alert(d.error||'保存失败');
  });
}
function doLoadSave(filename){
  showLoading(true,'读取存档...');
  fetch('/api/load/'+encodeURIComponent(filename),{method:'POST'}).then(function(r){return r.json()}).then(function(d){
    showLoading(false);
    if(d.ok){
      el('#save-panel').style.display='none';
      hideMainTabs();
      el('#npc-panel').style.display='block';
      el('#map-strip').style.display='flex';
      el('#story-log').style.display='block';
      el('#action-bar').style.display='';
      if(d.scene_name||d.scene_id)el('#scene-label').textContent=d.scene_name||d.scene_id;
      if(d.narrative_log&&d.narrative_log.length>0){
        d.narrative_log.slice(-20).forEach(function(n){addLog(n.type||'narrative',n.text||'')});
      }
      renderNPCs(d.npcs||[]);
      updateInfo(d);
      renderOptions(d.options||[]);
    }else alert(d.error||'读档失败');
  });
}
function doDeleteSave(filename){
  if(!confirm('确认删除 '+filename+'?'))return;
  fetch('/api/save/'+encodeURIComponent(filename),{method:'DELETE'}).then(function(r){return r.json()}).then(function(d){
    if(d.ok){renderSaveList()}else alert('删除失败');
  });
}

// ====== SETTINGS ======
function showSettings(){switchTab('settings')}

function loadProfiles(){
  fetch('/api/profiles').then(function(r){return r.json()}).then(function(d){
    var list=el('#profile-list-inline');if(!list)return;
    var html='<div style="font-size:12px;color:var(--text2);margin-bottom:6px;">已保存的配置：</div>';
    var ps=d.profiles||[];
    if(ps.length===0)html+='<div style="font-size:12px;color:var(--text2);padding:8px;">（暂无配置，请添加）</div>';
    ps.forEach(function(p){
      var act=p.active?'<span style="color:var(--accent2);font-size:11px;"> ✓ 当前</span>':'';
      var keyS=p.has_key?'✓ Key 已设':'✗ Key 未设';
      var subModels=[];
      if(p.agent_model) subModels.push('Agent:'+p.agent_model);
      if(p.arbiter_model) subModels.push('Arb:'+p.arbiter_model);
      if(p.gm_model) subModels.push('GM:'+p.gm_model);
      var subStr=subModels.length?' | '+subModels.join(' '):'';
      html+='<div class="profile-item'+(p.active?' active':'')+'">'
        +'<div class="profile-info"><span class="profile-name">'+escHtml(p.name)+'</span> <span style="font-size:11px;color:var(--text2);">'+escHtml(p.base_url)+' / '+escHtml(p.model)+'</span><br><span style="font-size:10px;color:var(--text2);">temp:'+(p.temperature||1.0)+' top_p:'+(p.top_p||0.95)+subStr+'</span> <span style="font-size:10px;color:'+(p.has_key?'var(--accent2)':'var(--warn)')+';">'+keyS+'</span>'+act+'</div>'
        +'<div class="profile-actions">'
        +'<button onclick="activateProfile(\''+escJs(p.name)+'\')" class="mini-btn">选择</button>'
        +'<button onclick="editProfile(\''+escJs(p.name)+'\')" class="mini-btn">编辑</button>'
        +'<button onclick="deleteProfile(\''+escJs(p.name)+'\')" class="mini-btn danger">删除</button>'
        +'</div></div>';
    });
    list.innerHTML=html;
    if(ps.length>0&&!window._cfgTestDone&&d.active)testAPIConnectionFromSettings();
  });
}

function escJs(s){return (s||'').replace(/'/g,"\\'")}
function activateProfile(name){
  fetch('/api/profiles/activate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:name})})
    .then(function(r){return r.json()}).then(function(d){
      if(d.ok){window._cfgTestDone=false;loadProfiles();testAPIConnectionFromSettings()}
    });
}
function editProfile(name){
  fetch('/api/profiles').then(function(r){return r.json()}).then(function(d){
    var p=(d.profiles||[]).find(function(x){return x.name===name});
    if(p){el('#cfg-name').value=p.name;el('#cfg-url').value=p.base_url;el('#cfg-key').value='';el('#cfg-model').value=p.model;el('#cfg-key').placeholder='(留空不修改)';
      el('#cfg-agent-model').value=p.agent_model||'';el('#cfg-arbiter-model').value=p.arbiter_model||'';el('#cfg-gm-model').value=p.gm_model||'';
      el('#cfg-temp').value=p.temperature||1.0;el('#cfg-temp-val').textContent=p.temperature||1.0;
      el('#cfg-topp').value=p.top_p||0.95;el('#cfg-topp-val').textContent=p.top_p||0.95;}
  });
}
function deleteProfile(name){
  if(!confirm('确认删除 "'+name+'"？'))return;
  fetch('/api/profiles/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:name})})
    .then(function(r){return r.json()}).then(function(d){loadProfiles()});
}
function saveSettings(){
  var name=el('#cfg-name').value.trim(),url=el('#cfg-url').value.trim(),key=el('#cfg-key').value.trim(),model=el('#cfg-model').value.trim();
  if(!name){alert('请输入配置名');return}if(!url){alert('请输入接口地址');return}
  if(!model)model='deepseek-v4-pro';
  var body={name:name,base_url:url,model:model,
    temperature:parseFloat(el('#cfg-temp').value),top_p:parseFloat(el('#cfg-topp').value),
    agent_model:el('#cfg-agent-model').value.trim(),
    arbiter_model:el('#cfg-arbiter-model').value.trim(),
    gm_model:el('#cfg-gm-model').value.trim()};
  if(key)body.api_key=key;
  el('#cfg-status').style.display='block';el('#cfg-status').textContent='保存中...';el('#cfg-status').className='conn-checking';
  fetch('/api/profiles',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
    .then(function(r){return r.json()}).then(function(d){
      if(d.ok){
        loadProfiles();
        el('#cfg-name').value='';el('#cfg-url').value='';el('#cfg-key').value='';el('#cfg-model').value='';
        el('#cfg-agent-model').value='';el('#cfg-arbiter-model').value='';el('#cfg-gm-model').value='';
        activateProfileFromSave(name);
      }
    });
}
function activateProfileFromSave(name){
  fetch('/api/profiles/activate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:name})})
    .then(function(r){return r.json()}).then(function(d){
      if(d.ok){loadProfiles();window._cfgTestDone=false;testAPIConnectionFromSettings()}
    });
}
function testAPIConnectionFromSettings(){
  el('#cfg-status').style.display='block';el('#cfg-status').textContent='测试中...';el('#cfg-status').className='conn-checking';
  window._cfgTestDone=true;
  fetch('/api/test_connection').then(function(r){return r.json()}).then(function(d){
    if(d.ok){el('#cfg-status').textContent='✓ 已连接 — '+d.model+' ('+d.latency_ms+'ms)';el('#cfg-status').className='conn-ok'}
    else{el('#cfg-status').textContent='✗ 连接失败 — '+d.error;el('#cfg-status').className='conn-fail'}
  }).catch(function(){el('#cfg-status').textContent='✗ 连接失败';el('#cfg-status').className='conn-fail'});
}

// ====== UTILS ======
function showLoading(on,text){var o=el('#loading-overlay');if(on){o.style.display='flex';el('#loading-text').textContent=text||'思考中...';el('#loading-progress').textContent=''}else{o.style.display='none'}}
function hideSettings(){switchTab('cards')}
function newGameConfirm(){if(confirm('开始新游戏？当前进度将丢失。')){fetch('/api/new_game',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({scene_id:'tianji_maze'})}).then(function(){location.reload()})}}
function shutdownServer(){if(confirm('确认关闭服务端？')){document.body.innerHTML='<div style="display:flex;align-items:center;justify-content:center;height:100vh;background:#0d1117;color:#c9d1d9;font-size:20px;flex-direction:column;font-family:Segoe UI,Microsoft YaHei,sans-serif;"><div style="font-size:48px;">&#9632;</div><div style="margin-top:20px;font-weight:600;">Astral 已关闭</div><div style="font-size:13px;color:#8b949e;margin-top:10px;">请关闭此窗口</div></div>';fetch('/api/shutdown')}}
function toggleDebugPanel(){var p=el('#debug-panel');var b=p.querySelector('.debug-body');b.style.display=b.style.display==='none'?'block':'none'}
function renderDebugRulings(d){if(!d||!d.rulings)return;el('#debug-rulings').innerHTML=d.rulings.map(function(r){return '<div>'+r[0]+' '+r[1]+'</div>'}).join('')}

// ====== SKIP / SLEEP ======
function doSkipTime(){
  var curHour=Math.floor((Date.now()/1000%86400)/3600)||0;
  fetch('/api/skip_time',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({hour:((new Date()).getHours()+1)%24})})
    .then(function(r){return r.json()}).then(function(d){
      if(d.ok){
        addLog('system','时间推进至 '+d.time);
        nextRound();
      }
    });
}
function doSleep(){
  showLoading(true,'睡眠中...');
  fetch('/api/sleep',{method:'POST'}).then(function(r){return r.json()})
    .then(function(d){
      showLoading(false);
      if(d.ok){addLog('system',d.result);nextRound();}
    });
}
