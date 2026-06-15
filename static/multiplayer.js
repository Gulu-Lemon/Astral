/**
 * multiplayer.js — 联机模式前端 (Socket.IO 客户端)
 */
var M = {
    socket: null,
    roomId: '',
    agentId: '',
    playerName: '',
    connected: false,
    inLobby: false,
    waitingForIntent: false,
    narrativeText: '',
    lastOptions: [],
};

function el(s) { return document.getElementById(s); }

// ========== 入口 ==========

function showMultiplayer() {
    if (!io) { alert('Socket.IO 未加载，请检查网络'); return; }
    M.playerName = el('mp-player-name').value.trim() || ('玩家' + Math.floor(Math.random() * 9000 + 1000));
    el('mp-player-name').value = M.playerName;
    el('mp-lobby').style.display = 'flex';
    el('mp-lobby-join').style.display = 'block';
    el('mp-lobby-room').style.display = 'none';
    el('mp-lobby-title').textContent = '\uD83C\uDF10 联机大厅';
}

function hideMultiplayer() {
    el('mp-lobby').style.display = 'none';
    el('mp-intent-panel').style.display = 'none';
    el('mp-game-overlay').style.display = 'none';
    M.inLobby = false;
    if (M.socket) { M.socket.disconnect(); M.socket = null; }
    M.connected = false;
}

// ========== Socket.IO 连接 ==========

function mpConnect() {
    if (M.socket && M.socket.connected) return;
    M.socket = io({ transports: ['websocket', 'polling'] });

    M.socket.on('connect', function () {
        M.connected = true;
        console.log('[MP] 已连接');
    });

    M.socket.on('disconnect', function (reason) {
        M.connected = false;
        console.log('[MP] 断开:', reason);
        if (M.inLobby) {
            el('mp-status-line') && (el('mp-status-line').textContent = '连接断开...');
        }
    });

    M.socket.on('error', function (d) {
        console.error('[MP] 错误:', d.message);
        alert(d.message || '服务器错误');
    });

    // ---- 房间事件 ----
    M.socket.on('room_created', onRoomCreated);
    M.socket.on('room_joined', onRoomJoined);
    M.socket.on('player_joined', onPlayerJoined);
    M.socket.on('player_left', onPlayerLeft);
    M.socket.on('slot_updated', onSlotUpdated);

    // ---- 游戏事件 ----
    M.socket.on('game_starting', onGameStarting);
    M.socket.on('window_start', onWindowStart);
    M.socket.on('intent_request', onIntentRequest);
    M.socket.on('intent_confirmed', onIntentConfirmed);
    M.socket.on('ready_status', onReadyStatus);
    M.socket.on('narrative_chunk', onNarrativeChunk);
    M.socket.on('narrative_done', onNarrativeDone);
    M.socket.on('player_options', onPlayerOptions);
    M.socket.on('round_end', onRoundEnd);

    // ---- 对话事件 ----
    M.socket.on('dialogue_received', onDialogueReceived);
    M.socket.on('dialogue_result', onDialogueResult);
    M.socket.on('dialogue_broadcast', onDialogueBroadcast);
}

// ========== 房间回调 ==========

function onRoomCreated(d) {
    M.roomId = d.room_id;
    M.agentId = d.host_agent_id;
    el('mp-lobby-join').style.display = 'none';
    el('mp-lobby-room').style.display = 'block';
    el('mp-room-display').textContent = d.room_id;
    el('mp-room-scene').textContent = '场景: ' + (d.scene_id || 'tianji_maze');
    M.inLobby = true;
    renderSlotList(d.slots);
    el('mp-lobby-title').textContent = '\uD83C\uDFE0 房间 ' + d.room_id;
}

function onRoomJoined(d) {
    M.roomId = d.room_id;
    M.agentId = d.agent_id;
    el('mp-lobby-join').style.display = 'none';
    el('mp-lobby-room').style.display = 'block';
    el('mp-room-display').textContent = d.room_id;
    M.inLobby = true;
    renderSlotList(d.slots);
    el('mp-lobby-title').textContent = '\uD83C\uDFE0 房间 ' + d.room_id;
}

function onPlayerJoined(d) {
    // Will be updated when slot_updated fires
}

function onPlayerLeft(d) {
    // Will be updated when slot_updated fires
}

function onSlotUpdated(d) {
    renderSlotList(d.slots);
}

function renderSlotList(slots) {
    var container = el('mp-slot-list');
    if (!container) return;
    var html = '';
    var humanCount = 0;
    var keys = Object.keys(slots).sort();
    for (var i = 0; i < keys.length; i++) {
        var s = slots[keys[i]];
        var isHost = s.agent_id === M.agentId;
        var isMe = s.player_sid === (M.socket && M.socket.id);
        var cls = 'mp-slot';
        if (s.is_human && s.connected) {
            if (isMe) cls += ' mp-slot-me';
            humanCount++;
            html += '<div class="' + cls + '" data-aid="' + s.agent_id + '">';
            html += '<span class="mp-slot-id">' + s.agent_id + '</span> ';
            html += '<span class="mp-slot-name">' + escHtml(s.player_name || '玩家') + '</span>';
            if (isHost) html += ' <span class="mp-slot-badge">房主</span>';
            if (isMe) html += ' <span class="mp-slot-badge mp-slot-you">你</span>';
            if (!s.connected) html += ' <span style="color:var(--danger);font-size:10px;">离线</span>';
            html += '</div>';
        } else if (!s.is_human) {
            html += '<div class="' + cls + ' mp-slot-ai" data-aid="' + s.agent_id + '" onclick="mpSelectSlot(\'' + s.agent_id + '\')">';
            html += '<span class="mp-slot-id">' + s.agent_id + '</span> ';
            html += '<span class="mp-slot-name" style="color:var(--text2);">[AI 可用]</span>';
            html += '</div>';
        } else {
            html += '<div class="' + cls + ' mp-slot-offline" data-aid="' + s.agent_id + '">';
            html += '<span class="mp-slot-id">' + s.agent_id + '</span> ';
            html += '<span class="mp-slot-name" style="color:var(--danger);">离线</span>';
            html += '</div>';
        }
    }
    container.innerHTML = html;
    if (el('mp-player-count')) el('mp-player-count').textContent = humanCount + '/12 人';
}

function mpSelectSlot(agentId) {
    if (!M.socket || !M.connected) return;
    M.socket.emit('select_slot', { room_id: M.roomId, agent_id: agentId });
}

// ========== 游戏流程回调 ==========

function onGameStarting(d) {
    el('mp-lobby').style.display = 'none';
    el('mp-game-overlay').style.display = 'block';
    el('mp-status-line').textContent = '游戏开始！';
    el('mp-narrative-stream').style.display = 'none';
    M.inLobby = false;
}

function onWindowStart(d) {
    el('mp-game-overlay').style.display = 'block';
    el('mp-status-line').textContent = '时间窗口 (' + d.window_minutes + '分钟) — 准备你的行动';
    el('mp-narrative-stream').style.display = 'none';
    el('mp-narrative-stream').textContent = '';
    M.narrativeText = '';
}

function onIntentRequest(d) {
    M.waitingForIntent = true;
    el('mp-game-overlay').style.display = 'block';

    var perc = '';
    perc += '位置: ' + (d.location || '未知') + ' | ';
    perc += '情绪: ' + (d.emotional_state || '平静') + ' | ';
    perc += '威胁: ' + (d.threat_level || 0).toFixed(1) + '\n';
    if (d.nearby_npcs && d.nearby_npcs.length > 0) {
        perc += '附近: ';
        for (var i = 0; i < d.nearby_npcs.length; i++) {
            perc += d.nearby_npcs[i].name + '(' + d.nearby_npcs[i].id + ') ';
        }
    } else {
        perc += '附近: 无人';
    }
    el('mp-perception').textContent = perc;

    el('mp-intent-panel').style.display = 'flex';
    el('mp-intent-title').textContent = '\uD83C\uDFAD ' + (d.agent_name || d.agent_id) + ' 的行动';
    el('mp-intent-type').value = 'rest';
    el('mp-intent-target').value = '';
    el('mp-intent-loc').value = '';
    el('mp-intent-dialogue').value = '';
    el('mp-intent-prose').value = '';
    el('mp-intent-internal').value = '';
    el('mp-intent-reason').value = '';
    el('mp-intent-duration').value = '10';
}

function onIntentConfirmed(d) {
    el('mp-intent-panel').style.display = 'none';
    M.waitingForIntent = false;
    el('mp-status-line').textContent = '已提交，等待其他玩家...';
}

function onReadyStatus(d) {
    if (!el('mp-ready-list')) return;
    var html = '';
    var total = 0, ready = 0;
    for (var i = 0; i < d.players.length; i++) {
        var p = d.players[i];
        total++;
        if (p.ready) ready++;
        var color = p.ready ? 'var(--accent)' : p.connected ? 'var(--text2)' : 'var(--danger)';
        var icon = p.ready ? '\u2714' : p.connected ? '\u23F3' : '\u2716';
        html += '<span style="color:' + color + ';font-size:10px;padding:2px 4px;">' + icon + ' ' + escHtml(p.player_name || p.agent_id) + '</span>';
    }
    el('mp-ready-list').innerHTML = html;
    if (total > 0) {
        el('mp-status-line').textContent = '已提交: ' + ready + '/' + total;
    }
}

function onNarrativeChunk(d) {
    M.narrativeText += d.text;
    var stream = el('mp-narrative-stream');
    if (stream) {
        stream.style.display = 'block';
        stream.textContent += d.text;
        stream.scrollTop = stream.scrollHeight;
    }
}

function onNarrativeDone(d) {
    M.narrativeText = d.text || M.narrativeText;
}

function onPlayerOptions(d) {
    M.lastOptions = d.options || [];
    renderMpOptions(d.options);
}

function renderMpOptions(options) {
    var bar = el('action-bar');
    if (!bar) return;
    bar.innerHTML = '';
    if (!options || options.length === 0) {
        bar.innerHTML = '<button class="action-btn" onclick="mpQuickAction(\'rest\')">\u25B6 待机</button>';
        return;
    }
    for (var i = 0; i < options.length; i++) {
        (function (o) {
            var btn = document.createElement('button');
            btn.className = 'action-btn';
            btn.textContent = o.label;
            btn.onclick = function () {
                mpDoOption(o);
            };
            bar.appendChild(btn);
        })(options[i]);
    }
}

function mpDoOption(o) {
    var intentData = {
        room_id: M.roomId,
        intent_type: o.type === 'explore' ? 'explore' : o.type === 'dialogue' ? 'socialize' : o.type === 'custom' ? 'rest' : 'investigate',
        target_id: o.target || null,
        target_location: o.room || null,
        dialogue: o.type === 'dialogue' ? o.label : '',
        prose: '',
        reasoning: o.label,
        duration: 10,
    };
    M.socket.emit('submit_intent', intentData);
}

function mpQuickAction(type) {
    M.socket.emit('submit_intent', {
        room_id: M.roomId,
        intent_type: type,
        target_id: null,
        target_location: null,
        reasoning: '快速行动',
        duration: 10,
    });
}

function onRoundEnd(d) {
    el('mp-status-line').textContent = '第' + d.day + '天 ' + d.time + ' | ' + d.location;
    // Update NPC panel if it exists
    if (typeof renderNPCs === 'function' && d.npcs) {
        var npcData = [];
        for (var i = 0; i < d.npcs.length; i++) {
            var n = d.npcs[i];
            npcData.push({
                agent_id: n.agent_id,
                name: n.name,
                location: n.location,
                nearby: n.nearby ? 1 : 0,
                emotion: n.emotion || '平静',
                alive: n.alive,
                affection: 50,
            });
        }
        try { renderNPCs(npcData); } catch (e) { }
    }
    // Update time info
    if (typeof updateInfo === 'function') {
        try {
            updateInfo({
                day: d.day, time: d.time, location: d.location,
                phase: d.phase, floor: 1, npcs: [],
                scene_name: '', in_trial: false, ending_resolved: false,
            });
        } catch (e) { }
    }
}

// ========== 对话 ==========

function onDialogueReceived(d) {
    alert(d.from_name + ' 对你说：' + d.message);
}

function onDialogueResult(d) {
    // Handled by dialogue system
}

function onDialogueBroadcast(d) {
    // Could show in narrative area
}

// ========== 提交意图 ==========

function mpSubmitIntent() {
    if (!M.socket || !M.connected) return;

    var data = {
        room_id: M.roomId,
        intent_type: el('mp-intent-type').value,
        target_id: el('mp-intent-target').value.trim() || null,
        target_location: el('mp-intent-loc').value.trim() || null,
        dialogue: el('mp-intent-dialogue').value.trim(),
        prose: el('mp-intent-prose').value.trim(),
        internal: el('mp-intent-internal').value.trim(),
        reasoning: el('mp-intent-reason').value.trim(),
        risk: '',
        scene_hint: '',
        duration: parseInt(el('mp-intent-duration').value) || 10,
    };

    M.socket.emit('submit_intent', data);
}

// ========== 按钮事件绑定 ==========

function mpCreateRoom() {
    mpConnect();
    M.playerName = el('mp-player-name').value.trim() || ('玩家' + Math.floor(Math.random() * 9000 + 1000));
    el('mp-player-name').value = M.playerName;

    if (!M.socket.connected) {
        M.socket.on('connect', function () {
            M.socket.emit('create_room', { scene_id: (S._scene || 'tianji_maze'), player_name: M.playerName });
        });
    } else {
        M.socket.emit('create_room', { scene_id: (S._scene || 'tianji_maze'), player_name: M.playerName });
    }
}

function mpJoinRoom() {
    var code = el('mp-room-code').value.trim().toUpperCase();
    if (!code) { alert('请输入房间码'); return; }
    mpConnect();
    M.playerName = el('mp-player-name').value.trim() || ('玩家' + Math.floor(Math.random() * 9000 + 1000));

    if (!M.socket.connected) {
        M.socket.on('connect', function () {
            M.socket.emit('join_room', { room_id: code, player_name: M.playerName });
        });
    } else {
        M.socket.emit('join_room', { room_id: code, player_name: M.playerName });
    }
}

function mpStartGame() {
    if (!M.socket || !M.connected) return;
    M.socket.emit('start_game', { room_id: M.roomId });
}

function mpLeaveRoom() {
    if (M.socket) {
        M.socket.emit('leave_room', { room_id: M.roomId });
        M.socket.disconnect();
    }
    hideMultiplayer();
}

function escHtml(s) {
    if (!s) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// ========== 绑定 DOM 事件 ==========

document.addEventListener('DOMContentLoaded', function () {
    var btnMp = el('btn-multiplayer');
    if (btnMp) btnMp.onclick = showMultiplayer;

    var btnMpCreate = el('btn-mp-create');
    if (btnMpCreate) btnMpCreate.onclick = mpCreateRoom;

    var btnMpJoin = el('btn-mp-join');
    if (btnMpJoin) btnMpJoin.onclick = mpJoinRoom;

    var btnMpStart = el('btn-mp-start');
    if (btnMpStart) btnMpStart.onclick = mpStartGame;

    var btnMpLeave = el('btn-mp-leave');
    if (btnMpLeave) btnMpLeave.onclick = mpLeaveRoom;

    var btnMpSubmit = el('btn-mp-submit-intent');
    if (btnMpSubmit) btnMpSubmit.onclick = mpSubmitIntent;

    // Close lobby on overlay click
    var lobbyOverlay = document.querySelector('#mp-lobby .panel-overlay');
    if (lobbyOverlay) lobbyOverlay.onclick = hideMultiplayer;

    // Close intent panel on overlay click
    var intentOverlay = document.querySelector('#mp-intent-panel .panel-overlay');
    if (intentOverlay) intentOverlay.onclick = function () {
        el('mp-intent-panel').style.display = 'none';
    };
});
