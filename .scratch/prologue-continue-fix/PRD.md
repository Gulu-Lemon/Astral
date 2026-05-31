# PrologueContinue 硬编码覆盖问题

Status: resolved (v1.1)

## 问题

`prologue_continue()` 的 free/grouping 阶段 prompt 硬编码在 `session.py:357-413`，完全绕过 `_scene_prompt()` 模板系统。三个场景在这些阶段收到完全相同的 LLM 指令文本，唯一的差异仅是 `_room_features()` 和 `_npc_profile_roster()` 的输出。

### 影响链

```
场景模块精心编写 PROLOGUE_CAMP/EXPLORE/FREE 模板
  ↓
_session_prompt() 可读取但从未被 prologue_continue() 调用
  ↓
prologue_continue() 使用自己的硬编码 prompt
  ↓ 缺失场景语境（"你在列车上" vs "你在迷宫中"）
  │ 缺失可用房间列表
  │ 缺失场景物理约束
  ↓
LLM 丧失场景锚点 → 默认套用"奇幻迷宫"范式编造
  ↓
_payer_action_prefix() 将编造内容写入 _player_action_log
  ↓ 下轮 prompt 注入编造内容作为"事实"
滚雪球放大
```

### 具体证据

1. **free 阶段** (`session.py:357-364`): 硬编码 prompt 只包含 `_room_features()` + `_npc_profile_roster()`。不区分场景。不注入 `SCENE_TONE`、`SCENE_NAME`、可用房间列表。

2. **grouping 阶段** (`session.py:399-413`): 同样硬编码。描述了一个通用的"分组探索"场景模板，不区分迷宫/酒店/列车。

3. **tianji_maze 的 PROLOGUE_FREE** (`tianji_maze.py:83-99`): 是一个完整的自由导航模板，含 `{room}`/`{room_features}`/`{npc_profiles}`/`{npc_statuses}` 占位符。但从未被读取——`add_module()` 未注册 `prologue_free` key，`prologue_continue()` 也不调用 `_scene_prompt("free")`。

4. **_player_action_prefix() 自循环**: 每轮把 `_player_action_log` 注入 prompt 作为"玩家行动轨迹"。如果 LLM 在 free 阶段编造了"石廊""密室"，这些文本会通过 `_player_action_prefix()` 出现在下轮 prompt 头部，被视为已确认事实。

## 解决方案

### 1. 注册 prologue_free 到场景系统

`scenarios/__init__.py:add_module()`:
```python
"prologue_free": getattr(module, "PROLOGUE_FREE", ""),
```

### 2. 新增 `_scene_context()` 方法

`session.py`:
```python
def _scene_context(self) -> str:
    name = self.scenario.get("name", "")
    tone = self.scenario.get("scene_tone", "")
    fr = self.scenario.get("floor_rooms", {})
    current_floor = self.world.current_floor
    rooms_here = fr.get(current_floor, [])
    rooms_str = "、".join(rooms_here[:8]) if rooms_here else self.player_location
    gm = self.scenario.get("gm_name", "")
    return (
        f"场景：{name}\n"
        f"基调：{tone}\n"
        f"当前位置：{self.player_location}\n"
        f"此区域可前往：{rooms_str}\n"
        f"GM角色（未登场前禁止出现）：{gm}"
    )
```

### 3. 重写 `prologue_continue()` 的 free 和 grouping 阶段 prompt

将硬编码 prompt 改为通过 `_scene_prompt()` 读取场景模板，并注入 `_scene_context()`。

**free 阶段改为：**
```python
if self._prologue_phase == "free":
    if self._prologue_turn >= 3:
        self._prologue_phase = "admin"
if self._prologue_phase == "free":
    scene_template = self._scene_prompt("free", default="")
    if scene_template:
        prompt = scene_template.format(
            room=self.player_location,
            room_features=self._room_features(self.player_location),
            npc_profiles=self._npc_profile_roster(),
            player_choice=player_choice,
            story_prefix=story_prefix,
            scene_context=self._scene_context(),
        )
    else:
        prompt = f"""{self._scene_context()}

{story_prefix}玩家选择：{player_choice}

描述接下来发生的事情。保持直接叙述。【当前房间设施】{self._room_features(self.player_location)}。禁止让{gm_name}出现。NPC 用外貌特征描述。

NPC 档案如下，请严格按其外貌、性格、行为特征撰写：
{self._npc_profile_roster()}

重要约束：严格按照【场景基调】描写环境。禁止编造场景中不存在的区域、建筑、设施或自然景观。所有人物在当前可前往的区域内活动。200-300字。

末尾输出4个选项：【选项】A. ... B. ... C. ... D. ..."""
```

**grouping 阶段改为：**
```python
elif self._prologue_phase == "grouping":
    scene_template = self._scene_prompt("explore", default="")
    if scene_template:
        prompt = scene_template.format(
            story_prefix=story_prefix,
            scene_context=self._scene_context(),
            player_name=self.player_name,
        )
    else:
        prompt = f"""{self._scene_context()}

{story_prefix}玩家对规则做出了反应。

随后，一位有领导气质的NPC站了出来，提议大家分组探索这个场所以提高效率。其他人立刻开始争论——有人想和熟人一组，有人坚持独自行动，有人试图拉拢强者。在争论中逐渐形成了2-3个小组，另有1-2人选择独自探索。

NPC 用外貌特征描述。NPC 档案如下，请严格按其外貌、性格、行为特征撰写：
{self._npc_profile_roster()}

重要约束：严格按照【场景基调】描写环境和分组探索。禁止编造不存在的区域。

同一组的成员在争论后会进行简短的自我介绍——自然地写出1-2句互报姓名和基本情况的对话。用外貌特征引入角色，通过对话揭示姓名。

末尾生成4个选项：
- 前2-3个选项是各组的特征简述
- 最后一个选项始终是"（独自探索）"

格式：【选项】A. ... B. ... C. ... D. ...
300-400字。"""
```

### 4. 打破 self-feedback 循环

`_player_action_prefix()` 中，对于自由探索阶段的条目，截断为仅保留玩家选择（不含 LLM 叙述内容）或添加过滤标记，避免编造内容回流。

### 5. 为各场景补充 `PROLOGUE_FREE` 模板

| 场景 | 当前 | 处理后 |
|------|------|--------|
| tianji_maze | 已有但未注册 | 注册并使用 |
| cloud_holiday | 缺失 | 新增 `PROLOGUE_FREE` 模板，注入酒店语境 |
| snow_train | 缺失 | 新增 `PROLOGUE_FREE` 模板，注入列车语境 |

### 影响文件

| 文件 | 变更 |
|------|------|
| `scenarios/__init__.py` | +1 行，注册 `prologue_free` |
| `session.py` | +15 行 `_scene_context()`，重写 ~60 行 `prologue_continue()` free/grouping 分支 |
| `scenarios/cloud_holiday.py` | +20 行 `PROLOGUE_FREE` 模板 |
| `scenarios/snow_train.py` | +20 行 `PROLOGUE_FREE` 模板 |

## 关联

P0 优先级。这是序章胡编乱造的根因——不是某个场景没写好，而是结构性地绕过了场景模板系统。
