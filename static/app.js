// Astral v0.5 Client
var COLORS=['#58a6ff','#f0883e','#2ea043','#a371f7','#db61a2','#56d4dd','#f85149','#f7b73f','#8b949e','#3fb950','#e553b2','#79c0ff'];
function el(s){return document.querySelector(s)}
function bind(s,e,f){document.querySelector(s).addEventListener(e,f)}

var S={inPrologue:false,prologueStep:0,playersTurn:true,dialogueWith:null,npcData:[],_scene:'tianji_maze',_selectedCard:null,debug:false};

// ====== INIT ======
document.addEventListener('DOMContentLoaded',function(){
  if(window.location.search.includes('debug=1')) S.debug = true;

  bind('#btn-start','click',startNewGame);
  bind('#input-name','keydown',function(e){if(e.key==='Enter')startNewGame()});
  bind('#btn-send','click',sendDialogue);
  bind('#input-message','keydown',function(e){if(e.key==='Enter')sendDialogue()});
  bind('#btn-close-dialogue','click',closeDialogue);
  bind('#btn-save','click',toggleSave);
  bind('#btn-settings','click',showSettings);
  bind('#btn-cfg-save','click',saveSettings);
  bind('#btn-cfg-test','click',testAPIConnectionFromSettings);
  bind('#btn-cfg-close','click',hideSettings);
  bind('#btn-newgame','click',newGameConfirm);
  bind('#btn-close-save','click',function(){el('#save-panel').style.display='none'});
  bind('.panel-overlay','click',function(){el('#save-panel').style.display='none'});
  bind('#trial-proceed-btn','click',trialProceed);
  bind('#prologue-btn','click',prologueSubmit);
  bind('#prologue-field','keydown',function(e){if(e.key==='Enter')prologueSubmit()});
  bind('#btn-back-scene','click',showSceneSelection);
  bind('#btn-new-card','click',showCardEditor);
  bind('#btn-card-save','click',saveCardFromEditor);
  bind('#btn-card-cancel','click',hideCardEditor);
  document.querySelectorAll('.choice-btn').forEach(function(b){b.addEventListener('click',function(){prologueChoose(b.dataset.mode)})});

  fetch('/api/scenes').then(function(r){return r.json()}).then(function(data){
    var list=el('#scene-list');
    if(!list)return;
    list.innerHTML=data.scenes.map(function(s){return '<div class="scene-card" onclick="selectScene(\''+s.id+'\')"><div class="scene-name">'+s.name+'</div><div class="scene-desc">'+(s.desc||'')+'</div></div>'}).join('');
  });

  fetch('/api/cards').then(function(r){return r.json()}).then(function(data){renderCards(data.cards)});

  // 检查 API 配置，无配置时自动弹出设置面板
  fetch('/api/profiles').then(function(r){return r.json()}).then(function(pd){
    if((pd.profiles||[]).length===0||!pd.active){
      setTimeout(function(){showSettings()},300);
    }else if(pd.active){
      // 有 active 配置，自动测试一次
      testAPIConnectionFromSettings();
    }
  });

  fetch('/api/state').then(function(r){return r.json()}).then(function(s){
    if(s.player_created&&s.prologue_step>=7){
      el('#scene-screen').style.display='none';el('#intro-screen').style.display='none';el('#prologue-screen').style.display='none';
      if(s.scene_name)el('#scene-label').textContent=s.scene_name;
      renderNPCs(s.npcs);updateInfo(s);
    }else if(s.player_created&&s.prologue_step>0&&s.prologue_step<7){
      el('#scene-screen').style.display='none';el('#intro-screen').style.display='none';
      S.inPrologue=true;S.prologueStep=s.prologue_step;
      el('#prologue-screen').style.display='block';
      if(s.prologue_step>=4){
        // 步骤 4+：用 continue 流恢复
        addPrologueText('(继续游戏)');
        prologueContinue('继续探索');
      }else{
        addPrologueText('(续)');el('#prologue-field').placeholder='按确定...';el('#prologue-btn').textContent='继续';
        el('#prologue-field').dataset.step=String(s.prologue_step);el('#prologue-input').style.display='flex';
      }
    }else{el('#scene-screen').style.display='block';el('#intro-screen').style.display='none';el('#prologue-screen').style.display='none'}
  });
});

// ====== API CONNECTION TEST ======
// 从设置面板中进行

// ====== SCENE ======
function selectScene(sid){
  showLoading(true,'场景切换中...');
  S._scene=sid;S._selectedCard=null;
  fetch('/api/select_scene',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({scene_id:sid})})
    .then(function(r){return r.json()}).then(function(d){
      showLoading(false);
      if(d.ok){el('#scene-label').textContent=d.scene_name||sid;el('#scene-title').textContent=d.scene_name||sid;el('#scene-screen').style.display='none';el('#intro-screen').style.display='block';el('#input-name').value='';el('#input-name').focus();fetch('/api/cards').then(function(r2){return r2.json()}).then(function(cd){renderCards(cd.cards)})}
    });
}
function showSceneSelection(){el('#intro-screen').style.display='none';el('#prologue-screen').style.display='none';el('#scene-screen').style.display='block'}

// ====== CARDS ======
function renderCards(cards){
  var list=el('#card-list');
  if(!list)return;
  if(!S._selectedCard && cards.length>0) S._selectedCard=cards[0];
  list.innerHTML=cards.map(function(c,i){
    var sel=S._selectedCard&&S._selectedCard.name===c.name?' selected':'';
    var extra=c.personality?' <span style="font-size:10px;color:var(--text2)">['+c.personality+']</span>':'';
    return '<div class="card-item'+sel+'" onclick="selectCard('+i+')"><div class="ci-name">'+c.name+'</div><div class="ci-magic">'+c.magic+extra+'</div></div>';
  }).join('');
}
function selectCard(idx){
  fetch('/api/cards').then(function(r){return r.json()}).then(function(data){
    var cards=data.cards;
    if(idx>=0&&idx<cards.length)S._selectedCard=cards[idx];
    renderCards(cards);
  });
}
function startWithCard(){
  if(!S._selectedCard){startNewGame();return}
  showLoading(true,'角色载入中...');
  var card=S._selectedCard;
  fetch('/api/start_with_card',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({card_name:card.name})})
    .then(function(r){return r.json()}).then(function(d){
      if(!d.ok){startNewGame();return}
      // 跳过镜子魔法步骤，直接进难度选择
      el('#intro-screen').style.display='none';el('#prologue-screen').style.display='block';
      S.inPrologue=true;S.prologueStep=1;
      showLoading(false);
      clearPrologueText();
      addPrologueText(d.intro_text+'\n\n你的能力: '+d.magic);
      el('#prologue-field').dataset.step='3';el('#prologue-input').style.display='none';el('#prologue-choices').style.display='flex';
    });
}

// ====== CARD EDITOR ======
function showCardEditor(){
  var card=S._selectedCard||{};
  el('#editor-title').textContent=card.name?'编辑角色卡':'新建角色卡';
  el('#edit-name').value=card.name||'';
  el('#edit-age').value=card.age||'16';
  el('#edit-appearance').value=card.appearance||'';
  el('#edit-magic').value=card.magic||'';
  el('#edit-personality').value=card.personality||'';
  el('#card-editor').style.display='block';
}
function hideCardEditor(){el('#card-editor').style.display='none'}
function saveCardFromEditor(){
  var name=el('#edit-name').value.trim();var age=el('#edit-age').value.trim();var appear=el('#edit-appearance').value.trim();var magic=el('#edit-magic').value.trim();var personality=el('#edit-personality').value.trim();
  if(!name){alert('请输入名字');return}
  fetch('/api/cards',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:name,age:age,appearance:appear,magic:magic,personality:personality})})
    .then(function(r){return r.json()}).then(function(d){
      if(d.ok){S._selectedCard={name:name,age:age,appearance:appear,magic:magic,personality:personality};renderCards(d.cards);hideCardEditor()}
      else alert(d.error||'保存失败');
    });
}

// ====== NEW GAME ======
function startNewGame(){
  if(S._selectedCard){startWithCard();return}
  var name=el('#input-name').value.trim()||'玩家';
  el('#intro-screen').style.display='none';el('#prologue-screen').style.display='block';
  S.inPrologue=true;S.prologueStep=0;
  prologueStep1(name);
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
      el('#prologue-field').dataset.step='5';showPrologueInput('按确定继续...','继续');
    }
  });
}

function showPrologueOptions(opts){
  var choices=el('#prologue-choices');
  choices.innerHTML=opts.map(function(o,i){
    var label=String.fromCharCode(65+i); // A, B, C, D
    return '<button class="choice-btn prologue-opt" data-choice="'+esc(o)+'">'+label+'. '+o+'</button>';
  }).join('');
  choices.style.display='flex';
  el('#prologue-input').style.display='none';
  document.querySelectorAll('.prologue-opt').forEach(function(b){
    b.addEventListener('click',function(){prologueContinue(b.dataset.choice)});
  });
}

function prologueContinue(choice){
  showLoading(true,'推进中...');
  fetch('/api/prologue/continue',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({choice:choice})})
    .then(function(r){return r.json()}).then(function(d){
      showLoading(false);
      if(d.finished){prologueFinish();return}
    addPrologueText(d.text);
    if(d.rule){addRuleText(d.rule)}
    if(d.options&&d.options.length>0){
      showPrologueOptions(d.options);
    }else{
      el('#prologue-field').dataset.step=String(d.step||4);
      showPrologueInput('输入你的行动或按确定继续...','继续');
    }
    });
}

function prologueStep5(){prologueContinue('继续探索');}
function prologueStep6(){prologueContinue('确认进入');}

function prologueFinish(){
  hidePrologueInput();
  fetch('/api/prologue/finish',{method:'POST'}).then(function(){S.inPrologue=false;el('#prologue-screen').style.display='none';refreshState();nextRound()});
}

function prologueSubmit(){
  var f=el('#prologue-field');var step=f.dataset.step;var val=f.value.trim();
  if(step==='1a'){if(!val)return;showLoading(true,'生成角色中...');fetch('/api/prologue/mirror',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:f.dataset.name,age:'16',appearance:val})}).then(function(r){return r.json()}).then(function(d){showLoading(false);clearPrologueText();addPrologueText(d.text);prologueStep1b()})}
  else if(step==='2'){if(!val)return;prologueStep2(val)}
  else if(step.startsWith('4')||step==='5'||step==='6'){prologueContinue(val||'继续探索')}
  else if(step==='7'){prologueFinish()}
}

// ====== NPC ======
function renderNPCs(npcs){
  S.npcData=npcs;
  el('#alive-count').textContent='('+npcs.length+')';
  el('#npc-list').innerHTML=npcs.map(function(n,i){
    var dead=!n||n.dead;
    return '<div class="npc-card '+(n.nearby?'nearby':'')+' '+(dead?'dead':'')+'" id="npc-'+n.agent_id+'" onclick="'+(dead?'':'talkToNPC(\''+n.agent_id+'\')')+'">'
      +'<div class="dot" style="background:'+COLORS[i]+'"></div>'
      +'<div class="info"><div class="name">'+n.name+'</div><div class="loc">'+n.location+'</div>'
      +'<div class="aff-row"><div class="aff-bar"><div class="aff-fill" style="width:'+n.affection+'%;background:'+COLORS[i]+'"></div></div><span class="aff-label">'+affLabel(n.affection)+'</span></div></div></div>';
  }).join('');
  renderInventory();
}
function affLabel(v){if(v>=80)return '恋人';if(v>=60)return '知己';if(v>=50)return '友人';if(v>=40)return '相识';if(v>=30)return '陌生';if(v>=20)return '冷淡';if(v>=10)return '敌对';return '仇恨'}
function updateCardStatus(id,s){var c=document.getElementById('npc-'+id);if(!c)return;c.classList.toggle('thinking',s==='thinking');c.classList.toggle('done',s==='done')}
function clearNPCHighlights(){document.querySelectorAll('.npc-card').forEach(function(c){c.classList.remove('thinking','done')})}

// ====== INVENTORY ======
function renderInventory(){
  var sd=window._state||{};
  var inv=sd.inventory||[];
  var el2=document.getElementById('player-inventory');
  if(el2)el2.textContent=inv.length?'背包: '+inv.join(', '):'';
}

// ====== DIALOGUE ======
function talkToNPC(id){
  var npc=S.npcData.find(function(n){return n.agent_id===id});
  if(!npc||!npc.nearby){addStory('system',(npc?npc.name:id)+' 不在这里。');return}
  S.dialogueWith=id;
  el('#dialogue-target').textContent='@ '+npc.name;
  el('#dialogue-box').style.display='flex';
  el('#input-message').value='';
  el('#input-message').focus();
  // 先显示占位符，防止按钮位置跳跃导致误点
  var hints=el('#dialogue-hints');
  if(hints) hints.innerHTML='<span class="sug-placeholder">正在分析对话建议...</span>';
  // 异步获取上下文相关的建议
  fetch('/api/dialogue_suggestions',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({agent_id:id,player_name:(window._state&&window._state.player_name)||''})})
    .then(function(r){return r.json()}).then(function(d){
      if(!d.ok||!(d.suggestions||[]).length){if(hints)hints.innerHTML='';return;}
      var sug=d.suggestions||[];
      if(hints) hints.innerHTML=sug.map(function(s){return '<button class="sug-btn" onclick="sendSuggestion(\''+esc(s)+'\')">'+s+'</button>'}).join('');
    });
}
function sendSuggestion(s){
  el('#input-message').value=s;
  sendDialogue();
}
function closeDialogue(){S.dialogueWith=null;el('#dialogue-box').style.display='none';el('#dialogue-hints').innerHTML='';}

function sendDialogue(){
  if(!S.dialogueWith)return;
  showLoading(true,'对话中...');
  var inp=el('#input-message');var msg=inp.value.trim()||'你好。';inp.value='';inp.disabled=true;
  addStory('dialogue','你: '+msg,'#c9d1d9');
  fetch('/api/dialogue',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({agent_id:S.dialogueWith,message:msg})})
    .then(function(r){return r.json()}).then(function(d){
      inp.disabled=false;
      if(d.ok){
        var c=COLORS[S.npcData.findIndex(function(n){return n.agent_id===S.dialogueWith})]||'#58a6ff';
        addStory('dialogue',d.agent_name+': '+d.response,c);
        if(d.micro_narrative) addStory('gm',d.micro_narrative);
        refreshState()
      }
      else addStory('system',d.error||'对话失败');
      showLoading(false);
      inp.focus();
    });
}

// ====== ROUND ======
function nextRound(){
  if(S.inPrologue)return;
  if(!S.playersTurn)return;
  S.playersTurn=false;
  disableActions(true);showLoading(true,'Agent 思考中...');clearNPCHighlights();
  var src=new EventSource('/api/round');var done=false;
  src.onmessage=function(e){
    if(done)return;
    try{var evt=JSON.parse(e.data)}catch(ex){return}
    if(evt.type==='round_start'){setLoadingText('第'+evt.round+'轮...')}
    else if(evt.type==='agent_done'){updateCardStatus(evt.agent_id,'done');setLoadingText('Agent('+evt.completed+'/'+evt.total+')')}
    else if(evt.type==='arbiter_start'){setLoadingText('仲裁官判定中...')}
    else if(evt.type==='arbiter_done'){
      setLoadingText('仲裁完成');
      if(S.debug){renderDebugRulings(evt.rulings)}
    }
    else if(evt.type==='narrative_start'){setLoadingText('GM 叙述中...')}
    else if(evt.type==='narrative_done'){addStory('gm',evt.text);renderActions(evt.options)}
    else if(evt.type==='npc_approaches'){
      evt.npcs.forEach(function(n){
        if(n.opener){
          addStory('npc','「'+n.opener.replace(/^[「『""]|[」』""]$/g,'')+'」——'+n.agent_name);
        }else{
          addStory('system','💬 '+n.agent_name+' 走了过来。');
        }
      });
      if(evt.npcs.length===1){
        setTimeout(function(){talkToNPC(evt.npcs[0].agent_id)},500);
      }
    }
    else if(evt.type==='round_end'){
      if(evt.rule_text){addStory('system','\n【游戏规则】\n'+evt.rule_text)}
      updateInfo(evt);if(evt.in_trial)showTrialBanner();else hideTrialBanner();src.close();showLoading(false);S.playersTurn=true;disableActions(false);refreshState()
    }
    else if(evt.type==='error'){src.close();showLoading(false);S.playersTurn=true;disableActions(false);addStory('system','错误: '+evt.message)}
  };
  src.onerror=function(){if(!done){src.close();showLoading(false);S.playersTurn=true;disableActions(false)}done=true};
}

// ====== ACTIONS ======
function renderActions(opts){
  el('#action-bar').innerHTML=(opts||[]).map(function(o,i){
    if(typeof o==='string')return '<button onclick="doAction(\''+esc(o)+'\')">'+o+'</button>';
    var label=o.label||'';var letters='ABCD';
    return '<button class="act-btn act-'+ (o.type||'')+'" onclick="doStructured(\''+esc(JSON.stringify(o))+'\')">'+letters.charAt(i)+'. '+label+'</button>';
  }).join('')
    +'<span class="free-input-wrap"><input type="text" id="free-input" placeholder="自由输入..." maxlength="200" onkeydown="if(event.key===\'Enter\')submitFree()"><button onclick="submitFree()">→</button></span>'
    +'<button onclick="nextRound()" style="border-color:#7ee787;color:#7ee787;">▶ 推进</button>';
}

function doStructured(jsonStr){
  try{var opt=JSON.parse(jsonStr)}catch(e){return}
  if(opt.type==='dialogue'&&opt.target){
    // 真正的 NPC agent 对话
    talkToNPC(opt.target);
    return;
  }
  if(opt.type==='explore'&&opt.room){
    exploreRoom(opt.room);
    return;
  }
  if(opt.type==='investigate'){
    investigateAction(opt.label);
    return;
  }
  // custom 或其他 → 自由输入式调查，但先尝试匹配附近 NPC
  doAction(opt.label||'');
}
function submitFree(){var inp=document.getElementById('free-input');if(!inp)return;var t=inp.value.trim();if(!t)return;inp.value='';inp.blur();doAction(t)}
function disableActions(v){document.querySelectorAll('#action-bar button').forEach(function(b){b.disabled=v});var inp=document.getElementById('free-input');if(inp)inp.disabled=v}
function doAction(a){
  disableActions(true);
  // Meta-instruction detection
  if(a.match(/指令[：:]|\(指令[：:]/)){
    var cmd = a.replace(/.*?指令[：:]/,'').replace(/[）)]/,'').trim();
    if(!cmd) cmd = '检查所有角色';
    showLoading(true,'查询中...');
    fetch('/api/meta',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({command:cmd})})
      .then(function(r){return r.json()}).then(function(d){
        showLoading(false);
        if(d.ok){addStory('system',d.result);refreshState()}
        else addStory('system',d.error||'指令失败');
        disableActions(false);
      });
    return;
  }
  // Combined options (e.g. "B……A" or "A+B")
  if(a.includes('……')||a.includes('..')){
    var parts = a.split(/……|\.\./);
    doActionChain(parts,0);
    return;
  }
  // Combined single letters (e.g. "AC" or "B D")
  if(/^[A-D]\s*[A-D]$/.test(a.replace(/\s/g,''))){ // Not doing this automatically, too ambiguous
    // fall through to normal handling
  }
  // 检查是否为旧格式字符串（兼容）
  if(a.includes('交谈')&&a.includes('与')){var n=S.npcData.find(function(x){return a.includes(x.name)||a.includes(x.agent_id)});if(n)talkToNPC(n.agent_id);else addStory('system','找不到');disableActions(false);return}
  if(a.includes('前往')){exploreRoom(a.replace('前往','').replace('探索','').trim());return}
  // 尝试匹配附近 NPC
  var nearby=S.npcData.filter(function(x){return x.nearby});
  var matchedNpc=null;
  for(var i=0;i<nearby.length;i++){
    var n=nearby[i];
    if(a.includes(n.name)||a.includes(n.agent_id)){matchedNpc=n;break}
  }
  if(matchedNpc){talkToNPC(matchedNpc.agent_id);disableActions(false);return}
  if(nearby.length===1){talkToNPC(nearby[0].agent_id);disableActions(false);return}
  freeNarrativeAction(a);
}

function doActionChain(parts,idx){
  if(idx >= parts.length){ disableActions(false); refreshState(); return; }
  var a = parts[idx].trim();
  if(!a){ doActionChain(parts, idx+1); return; }
  disableActions(true);
  // Try as NPC dialogue first
  var nearby=S.npcData.filter(function(x){return x.nearby});
  var matchedNpc=null;
  for(var i=0;i<nearby.length;i++){
    if(a.includes(nearby[i].name)||a.includes(nearby[i].agent_id)){matchedNpc=nearby[i];break}
  }
  if(matchedNpc && S.dialogueWith !== matchedNpc.agent_id){
    // Just open dialogue with this NPC, don't send message yet unless a is a full sentence
    if(a.length > matchedNpc.name.length+2){
      addStory('system','你: '+a);
      fetch('/api/dialogue',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({agent_id:matchedNpc.agent_id,message:a})})
        .then(function(r){return r.json()}).then(function(d){
          if(d.ok){
            var c=COLORS[S.npcData.findIndex(function(n){return n.agent_id===matchedNpc.agent_id})]||'#58a6ff';
            addStory('dialogue',d.agent_name+': '+d.response,c);
            if(d.micro_narrative) addStory('gm',d.micro_narrative);
          }
          doActionChain(parts,idx+1);
        }).catch(function(){ doActionChain(parts,idx+1); });
      return;
    }
    else { talkToNPC(matchedNpc.agent_id); doActionChain(parts,idx+1); return; }
  }
  freeNarrativeAction(a);
  doActionChain(parts,idx+1);
}

function investigateAction(a){
  addStory('system','你: '+a);
  showLoading(true,'处理中...');
  fetch('/api/investigate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:a})})
    .then(function(r){return r.json()}).then(function(d){
      showLoading(false);
      if(d.ok&&d.description)addStory('gm',d.description);
      if(d.trial_evidence)addStory('system','[证据] '+d.description);
      if(d.inventory&&window._state){window._state.inventory=d.inventory;renderInventory()}
      disableActions(false)
    });
}

function freeNarrativeAction(a){
  addStory('system','你: '+a);
  showLoading(true,'叙述中...');
  fetch('/api/free_narrative',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:a})})
    .then(function(r){return r.json()}).then(function(d){
      showLoading(false);
      if(d.ok){
        if(d.narrative)addStory('gm',d.narrative);
        if(d.options&&d.options.length>0)renderActions(d.options);
      }else addStory('system',d.error||'处理失败');
      disableActions(false)
    });
}
function exploreRoom(room){
  addStory('system','前往 '+room);
  showLoading(true,'前往中...');
  fetch('/api/explore',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({room})})
    .then(function(r){return r.json()}).then(function(d){
      if(d.ok){addStory('gm',d.description);refreshState()}else addStory('system',d.error||'无法前往');
      showLoading(false);
      nextRound();
    });
}

// ====== TRIAL ======
function showTrialBanner(){el('#trial-banner').style.display='flex';updateTrialPhases()}
function hideTrialBanner(){el('#trial-banner').style.display='none'}
function updateTrialPhases(){
  fetch('/api/trial/state').then(function(r){return r.json()}).then(function(d){
    var map={'investigation':'搜查','court_statement':'陈述','court_debate':'辩论','closing':'论告','voting':'投票','execution':'处刑'};
    el('#trial-info').textContent='⚖ '+ (map[d.phase]||d.phase);
    document.querySelectorAll('.trial-phase-tag').forEach(function(t){t.classList.toggle('active',t.dataset.phase===d.phase)});
    el('#trial-proceed-btn').textContent=d.phase==='closing'?'进入投票':d.phase==='execution'?'结果':'推进';
  });
}
function trialProceed(){
  fetch('/api/trial/proceed',{method:'POST'}).then(function(r){return r.json()}).then(function(d){
    if(d.error){addStory('system','审判: '+d.error);return}
    if(d.phase==='closing'&&!d.error){
      addStory('system','发表论告: 完整阐述动机/手法/证据链。输入后再次点击推进。');
      el('#trial-proceed-btn').textContent='提交论告并投票';
      // Show argument input
      showArgumentInput();
      return;
    }
    if(d.text)addStory('trial',d.text);
    if(d.phase==='execution'){el('#story-log').lastElementChild.className='story-block execution';addStory('system','审判结束。');hideTrialBanner();refreshState()}
    updateTrialPhases();
  });
}
function showArgumentInput(){
  var bar=el('#action-bar');
  bar.innerHTML='<span style="flex:1;display:flex;gap:4px;"><input type="text" id="arg-input" placeholder="你的论告..." style="flex:1;padding:6px 10px;background:var(--bg);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:13px;"><button onclick="submitArgument()" style="padding:6px 14px;background:var(--warn);border:none;border-radius:6px;color:#000;font-weight:600;cursor:pointer;">提交</button></span>';
  el('#arg-input').focus();
}
function submitArgument(){
  var arg=el('#arg-input');if(!arg||!arg.value.trim())return;
  addStory('system','你的论告: '+arg.value.trim());
  fetch('/api/trial/argue',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({argument:arg.value.trim()})}).then(function(){
    el('#trial-proceed-btn').textContent='进入投票';
    el('#action-bar').innerHTML='<button onclick="nextRound()" style="border-color:#7ee787;color:#7ee787;">▶ 推进</button>';
  });
}

// ====== UI ======
function addStory(type,text,color){
  var log=el('#story-log');
  var d=document.createElement('div');
  d.className='story-block '+type;
  if(color)d.style.borderColor=color;
  if(text.indexOf('\n\n')>=0){
    d.innerHTML=text.split('\n\n').map(function(p){return'<p>'+p.replace(/\n/g,'<br>')+'</p>'}).join('');
  }else if(text.length>300&&text.indexOf('\n')<0){
    var chunks=[];var s=text;while(s.length>250){
      var cut=s.lastIndexOf('。',250);if(cut<120)cut=s.indexOf('。',250);if(cut<0)cut=250;
      chunks.push(s.slice(0,cut+1));s=s.slice(cut+1);
    }
    if(s)chunks.push(s);
    d.innerHTML=chunks.map(function(p){return'<p>'+p+'</p>'}).join('');
  }else{
    d.innerHTML=text.replace(/\n/g,'<br>');
  }
  log.appendChild(d);
  log.parentElement.scrollTop=log.parentElement.scrollHeight;
}
function updateInfo(s){
  window._state=s;
  el('#game-info').textContent='第'+s.day+'天 '+s.time+' · '+(s.location||'');
  var db=el('#difficulty-badge');db.textContent={story:'剧情',normal:'正常',witch:'魔女'}[s.difficulty]||'';db.className=s.difficulty||'';
  var fb=el('#floor-badge');fb.textContent=s.floor?s.floor+'F':'';
  if(s.alive_count)el('#alive-count').textContent='('+s.alive_count+')';
  renderInventory();
}
function refreshState(){
  fetch('/api/state').then(function(r){return r.json()}).then(function(d){
    if(d.npcs)renderNPCs(d.npcs);
    updateInfo(d);
    if(d.map_data)renderMap(d.map_data);
    if(d.in_trial)showTrialBanner();else hideTrialBanner();
  });
}
function showLoading(v,t){el('#loading-overlay').style.display=v?'flex':'none';if(t)setLoadingText(t)}
function setLoadingText(t){el('#loading-text').textContent=t}

// ====== MAP ======
function renderMap(md){
  var strip=el('#map-strip');
  if(!md||!md.cars||md.cars.length<2){strip.style.display='none';return}
  strip.style.display='flex';
  var isTrain=S._scene==='snow_train';
  var cars=md.cars;
  var html='';
  for(var i=0;i<cars.length;i++){
    var c=cars[i];
    if(i>0){
      var prev=cars[i-1];
      var tr=null;
      for(var j=0;j<md.transitions.length;j++){
        var t=md.transitions[j];
        if(t.from_floor===prev.floor&&t.to_floor===c.floor){tr=t;break}
      }
      if(tr){
        html+='<span class="map-arrow" onclick="exploreRoom(\''+tr.via_room+'\')">▶</span>';
      }else if(c.locked){
        html+='<span class="map-arrow locked">🔒</span>';
      }else{
        html+='<span class="map-arrow">·</span>';
      }
    }
    var cls='map-car'+(c.has_player?' active':'')+(c.locked?' locked':'');
    html+='<div class="'+cls+'">';
    var unit=isTrain?'车':'层';
    html+='<span class="map-car-label">'+(c.locked?'🔒 ':'')+unit+c.floor+'</span>';
    var roomsShort=c.rooms.slice(0,3).join('·');
    if(c.rooms.length>3)roomsShort+='等';
    html+='<span class="map-car-sublabel">'+roomsShort+'</span>';
    html+='<div class="map-rooms">';
    for(var k=0;k<c.rooms.length;k++){
      var explored=c.explored.indexOf(c.rooms[k])>=0;
      var here=c.has_player&&md.player_room===c.rooms[k];
      html+='<span class="map-dot'+(explored?' explored':'')+(here?' here':'')+'"></span>';
    }
    html+='</div></div>';
  }
  strip.innerHTML=html;
}

// ====== SAVE ======
function toggleSave(){
  var p=el('#save-panel');
  p.style.display=p.style.display==='none'?'block':'none';
  if(p.style.display==='block')refreshSlots();
}
function newGameConfirm(){
  if(!confirm('确认开始新游戏？当前进度将丢失（可先存档）。'))return;
  fetch('/api/new_game',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({scene_id:S._scene})})
    .then(function(r){return r.json()}).then(function(d){
      if(!d.ok)return;
      // 重置前端状态
      S.inPrologue=false;S.prologueStep=0;S.playersTurn=true;S.dialogueWith=null;S._selectedCard=null;
      el('#story-log').innerHTML='';
      el('#scene-label').textContent=d.scene_name||'';
      el('#scene-title').textContent=d.scene_name||'';
      el('#scene-screen').style.display='block';
      el('#intro-screen').style.display='none';
      el('#prologue-screen').style.display='none';
      el('#npc-list').innerHTML='';
      el('#action-bar').innerHTML='';
      el('#game-info').textContent='';
      hideTrialBanner();
      // 重新加载场景和卡片
      fetch('/api/scenes').then(function(r2){return r2.json()}).then(function(sd){
        var list=el('#scene-list');
        if(list)list.innerHTML=sd.scenes.map(function(s){return '<div class="scene-card" onclick="selectScene(\''+s.id+'\')"><div class="scene-name">'+s.name+'</div><div class="scene-desc">'+(s.desc||'')+'</div></div>'}).join('');
      });
      fetch('/api/cards').then(function(r3){return r3.json()}).then(function(cd){renderCards(cd.cards)});
    });
}
function refreshSlots(){
  fetch('/api/slots').then(function(r){return r.json()}).then(function(d){
    var html='<div class="save-slot auto"><div class="slot-desc">自动存档</div><div>'+(d.slots&&d.slots.find(function(x){return x.slot==='auto'})?'<span class="slot-time">有存档</span>':'<span class="slot-time" style="color:var(--text2)">空</span>')+' <button onclick="saveGame(\'auto\')">保存</button>'+(d.slots&&d.slots.find(function(x){return x.slot==='auto'})?'<button onclick="loadGame(\'auto\')">读档</button>':'')+'</div></div>';
    for(var s=1;s<=6;s++){
      var slot=d.slots&&d.slots.find(function(x){return x.slot===s});
      html+='<div class="save-slot"><div><div class="slot-desc">槽位 '+s+'</div>'+(slot?'<div class="slot-time">第'+slot.round_count+'轮</div>':'')+'</div><div><button onclick="saveGame('+s+')">保存</button>'+(slot?'<button onclick="loadGame('+s+')">读档</button>':'')+'</div></div>';
    }
    el('#save-slots').innerHTML=html;
  });
}
function saveGame(s){showLoading(true,'保存中...');fetch('/api/save/'+s,{method:'POST'}).then(function(r){return r.json()}).then(function(d){showLoading(false);refreshSlots()})}
function loadGame(s){
  showLoading(true,'读档中...');
  fetch('/api/load/'+s,{method:'POST'}).then(function(r){return r.json()}).then(function(d){
    showLoading(false);
    if(!d.ok){alert(d.error||'读档失败');refreshSlots();return}
    el('#save-panel').style.display='none';el('#intro-screen').style.display='none';el('#story-log').innerHTML='';el('#prologue-screen').style.display='none';
    S.inPrologue=false;
    var log=d.narrative_log||[];
    log.forEach(function(entry){
      if(typeof entry==='string'){addStory('gm',entry)}
      else{addStory(entry.type||'gm',entry.text||entry,entry.color)}
    });
    renderNPCs(d.npcs);updateInfo(d);S.playersTurn=true;S._selectedCard=null;hideTrialBanner();
    nextRound();
  }).catch(function(e){
    showLoading(false);
    alert('读档失败：'+e.message);
  });
}
function esc(s){return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/'/g,'&#39;').replace(/"/g,'&quot;')}

function shutdownServer(){
  if(!confirm('确认关闭程序？'))return;
  fetch('/api/shutdown').catch(function(){});
  document.body.innerHTML='<div style="display:flex;align-items:center;justify-content:center;height:100vh;color:var(--text2);font-size:16px;">程序已关闭。请关闭此页面。</div>';
}

// ====== SETTINGS ======
var _cfgTestDone=false;
function showSettings(){_cfgTestDone=false;loadProfiles();el('#settings-panel').style.display='block'}
function hideSettings(){el('#settings-panel').style.display='none'}

function loadProfiles(){
  fetch('/api/profiles').then(function(r){return r.json()}).then(function(d){
    var list=el('#profile-list');if(!list)return;
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
        +'<div class="profile-info"><span class="profile-name">'+p.name+'</span> <span style="font-size:11px;color:var(--text2);">'+p.base_url+' / '+p.model+'</span><br><span style="font-size:10px;color:var(--text2);">temp:'+(p.temperature||1.0)+' top_p:'+(p.top_p||0.95)+subStr+'</span> <span style="font-size:10px;color:'+(p.has_key?'var(--accent2)':'var(--warn)')+';">'+keyS+'</span>'+act+'</div>'
        +'<div class="profile-actions">'
        +'<button onclick="activateProfile(\''+esc(p.name)+'\')" class="mini-btn">选择</button>'
        +'<button onclick="editProfile(\''+esc(p.name)+'\')" class="mini-btn">编辑</button>'
        +'<button onclick="deleteProfile(\''+esc(p.name)+'\')" class="mini-btn danger">删除</button>'
        +'</div></div>';
    });
    list.innerHTML=html;
    // 如果已有配置且未测试过，自动测试
    if(ps.length>0&&!_cfgTestDone&&d.active)testAPIConnectionFromSettings();
  });
}

function activateProfile(name){
  fetch('/api/profiles/activate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:name})})
    .then(function(r){return r.json()}).then(function(d){
      if(d.ok){_cfgTestDone=false;loadProfiles();testAPIConnectionFromSettings()}
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
        // 保存后自动激活为新配置
        activateProfileFromSave(name);
      }
    });
}
function activateProfileFromSave(name){
  fetch('/api/profiles/activate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:name})})
    .then(function(r){return r.json()}).then(function(d){
      if(d.ok){loadProfiles();_cfgTestDone=false;testAPIConnectionFromSettings()}
    });
}

function testAPIConnectionFromSettings(){
  var status=el('#cfg-status');if(!status)return;
  status.style.display='block';status.textContent='测试连接中...';status.className='conn-checking';
  fetch('/api/test_connection').then(function(r){return r.json()}).then(function(d){
    if(d.ok){status.textContent='\u2713 连接正常 ('+d.model+' \u00b7 '+d.latency_ms+'ms)';status.className='conn-ok';_cfgTestDone=true}
    else{status.textContent='\u2717 '+d.error;status.className='conn-fail';_cfgTestDone=false}
  });
}

// ====== DEBUG ======
function renderDebugRulings(rulings){
  var panel = el('#debug-panel'); if(!panel) return;
  panel.style.display = 'block';
  var body = el('#debug-rulings'); if(!body) return;
  var now = new Date().toLocaleTimeString();
  var html = '<div class="debug-round-header">--- '+now+' ---</div>';
  rulings.forEach(function(r){
    var icon = r.approved && r.success ? '✓' : '✗';
    var color = r.approved && r.success ? 'var(--accent2)' : (r.approved ? 'var(--warn)' : 'var(--danger)');
    html += '<div class="debug-line"><span style="color:'+color+'">'+icon+'</span> '+r.agent_name+': '+r.description+(r.downgraded?' →降级为'+r.downgraded:'')+'</div>';
  });
  body.innerHTML = body.innerHTML + html;
  body.parentElement.scrollTop = body.parentElement.scrollHeight;
}
function toggleDebugPanel(){
  var body = el('#debug-panel .debug-body');
  if(body) body.style.display = body.style.display === 'none' ? 'block' : 'none';
}
