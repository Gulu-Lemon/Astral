"""Fix snow_train prologue prompts"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
path = r"E:\dd\文档们\AI互动小说计划\Astral\scenarios\snow_train.py"

with open(path, "r", encoding="utf-8") as f:
    content = f.read()

# Fix PROLOGUE_CAMP - use appearance instead of names
old_camp = """PROLOGUE_CAMP = \"\"\"
{player_name}推开宿舍门，沿着狭窄走廊来到会客大厅。

大厅里有11名少女，分散在古典风格的房间里——深红天鹅绒窗帘、温暖壁炉。有的在沙发上交谈，有的独自观察环境。当最后一人踏入时，所有人看向门口。

请选择2-3名性格冲突的NPC创作一个微型场景：
- 佐藤艾拉[No.01]：拿着记事本试图清点人数
- 暮石莉莉安[No.02]：在角落用纸牌变魔术戏弄人
- 叶裁夜子[No.06]：一脸凶相但手里端着饼干盘

玩家出现后场景中断。150-200字。
\"\"\""""

new_camp = """PROLOGUE_CAMP = \"\"\"
{player_name}推开宿舍门，沿着走廊来到观景lounge。

宽大的车窗映出窗外无尽的白色雪原。暖色灯光下，11名少女散落各处。当最后一人踏入时，所有人看向门口。

请选择2-3名性格冲突的NPC创作一个微型场景，用外貌特征描述：
- 黑发齐肩戴半框眼镜、拿着记事本的少女：试图清点人数
- 短发穿男式西装、戴单片眼镜的少女：在角落用纸牌变魔术戏弄人
- 狼尾发型、眼神锐利像不良的少女：一脸凶相但手里端着饼干盘

玩家出现后场景中断。用外貌特征描写，不要用名字。150-200字。
\"\"\""""

# Fix PROLOGUE_EXPLORE - remove [No.XX] and duplicate ending
old_explore = """PROLOGUE_EXPLORE = \"\"\"
一位温和的声音建议分头探索这列列车。

少女们分成几组：
• 佐藤艾拉[No.01]、桐生亚子[No.03]、御方怜奈[No.09]
• 暮石莉莉安[No.02]、鹿贺暮夜[No.05]、桃井奈奈[No.08]
• 艾琳娜[No.04]、樱井坂那[No.07]、藏原千华[No.11]
• 叶裁夜子[No.06]、姬川铃[No.10]、田中美树[No.12]

你可以选择跟随其中一组，或独自探索某个方向。
\"\"\""""

new_explore = """PROLOGUE_EXPLORE = \"\"\"
一位温和的声音建议分头探索这列列车。

少女们分成几组：
• 戴眼镜拿着记事本的、连帽衫睡不醒的、高挑肌肉线条阳光型的 — 检查厨房和储藏
• 穿西装戴单片眼镜的、哥特萝莉装抱着兔子的、粉色双马尾拿自拍杆的 — 探索图书温室
• 银发碧眼外国风的、短发面无表情的、手上沾颜料艺术气质的 — 查看无线电和动力
• 狼尾发型一脸凶相的、软绵绵治愈系微笑的、毫无特征大众脸的 — 检查宿舍
\"\"\""""

if old_camp in content:
    content = content.replace(old_camp, new_camp)
    print("CAMP fixed")
if old_explore in content:
    content = content.replace(old_explore, new_explore)
    print("EXPLORE fixed")

with open(path, "w", encoding="utf-8") as f:
    f.write(content)
print("Done")
