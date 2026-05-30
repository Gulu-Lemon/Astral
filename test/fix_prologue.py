"""Update prologue prompts in tianji_maze.py"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
path = r"E:\dd\文档们\AI互动小说计划\Astral\scenarios\tianji_maze.py"

with open(path, "r", encoding="utf-8") as f:
    content = f.read()

old = """PROLOGUE_CAMP = \"\"\"
场景：{player_name} 推开石室的门，来到起始营地中央。

营地里有12名少女，她们都已苏醒，正在各自打量环境和彼此。
选择2-3名性格冲突的NPC，围绕她们创作一个微型冲突场景：
- 菊池露娜[No.01]：领袖型，正义感强，正在试图组织大家
- 赤城莉莎[No.08]：情绪爆炸，蹲在角落用力敲打地面制造噪音
- 黑泽香具矢[No.10]：独来独往，靠在墙边冷眼旁观

玩家作为最后一个醒来的人出现，场景中断。所有人注意到玩家的到来。

150-200字。文学性描写，只写玩家看到的。
\"\"\"

PROLOGUE_EXPLORE = \"\"\"
少女们分成了几组开始探索这座迷宫：
• 菊池露娜[No.01]、香川可可萝[No.03]、花守彩香[No.06]
• 柳和奈[No.04]、藤宫爱丽丝[No.05]、中岛瑞秋[No.11]
• 水濑柔[No.07]、赤城莉莎[No.08]、索拉[No.12]
• 绵贯小鸠[No.09]、黑泽香具矢[No.10]

你可以选择跟随其中一组行动，或独自探索某个方向。
\"\"\""""

new = """PROLOGUE_CAMP = \"\"\"
场景：{player_name} 推开石室的门，来到起始营地中央。

营地里有12名少女，她们都已苏醒，正在各自打量环境和彼此。
选择2-3名性格冲突的NPC，围绕她们创作一个微型冲突场景：
- 栗色与银色相间长发、戴着黑色发带高马尾的少女：正在试图组织大家
- 火红短发、脖子手腕缠满绷带、戴着巨大耳机的少女：蹲在角落用力敲打地面
- 黑色不对称短发、眼神冷冽的少女：靠在墙边冷眼旁观

玩家作为最后一个醒来的人出现，场景中断。所有人注意到玩家的到来。

注意：用外貌特征描述，不要直接使用名字。150-200字。文学性描写，只写玩家看到的。
\"\"\"

PROLOGUE_EXPLORE = \"\"\"
一位温和的声音建议分头调查这座迷宫。

少女们分成了几组开始探索：
• 栗色长发马尾的少女、金色短发向日葵发卡的少女、黄色麻花辫穿洛丽塔裙的少女
• 浅棕色波浪长发的辣妹、深紫色长直发的优雅少女、金色卷发的贵族气息少女
• 浅蓝长发的温柔大姐姐、火红短发的吵闹少女、银色长发乱糟糟穿白大褂的少女
• 灰色连帽衫缩成一团的少女、黑色短发的冷酷少女

你可以选择跟随其中一组行动，或独自探索某个方向。
\"\"\""""

if old in content:
    content = content.replace(old, new)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("Updated successfully")
else:
    print("Old text not found - checking for PROLOGUE_CAMP...")
    idx = content.find("PROLOGUE_CAMP")
    if idx >= 0:
        print(repr(content[idx:idx+400]))
