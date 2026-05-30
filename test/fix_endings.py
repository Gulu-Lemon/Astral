"""Remove duplicate ending lines from PROLOGUE_EXPLORE in all scenarios"""
import sys, os, glob
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

scenarios_dir = r"E:\dd\文档们\AI互动小说计划\Astral\scenarios"
for fname in ["tianji_maze.py", "cloud_holiday.py", "snow_train.py"]:
    path = f"{scenarios_dir}\\{fname}"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Remove "你可以选择跟随其中一组行动，或独自探索某个方向。" from explore prompt
    endings = [
        "你可以选择跟随其中一组行动，或独自探索某个方向。",
        "你可以选择跟随其中一组，或独自探索某个方向。",
    ]
    modified = False
    for end in endings:
        if end in content:
            content = content.replace("\n" + end, "")
            modified = True
    
    if modified:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Fixed {fname}")
    else:
        print(f"No change in {fname}")
