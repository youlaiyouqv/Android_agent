# 批量评测脚本：依次运行tasks.json里的所有任务，自动记录结果
# 用法：python run_eval.py round1
import io
import sys
import csv
import json
import time
import asyncio
import subprocess
from pathlib import Path
from contextlib import redirect_stdout
from phone_agent import run_agent


RESET_PACKAGES = [
    "com.android.settings",
    "com.google.android.deskclock",
    "com.android.chrome",
    "com.google.android.calculator",
    "com.google.android.contacts",
]

def reset_device():
    """把手机恢复到初始状态：关掉相关应用，回到桌面
    为什么：上一个任务停在哪个页面，会影响下一个任务，导致结果不公平"""
    for pkg in RESET_PACKAGES:
        subprocess.run(["adb", "shell", "am", "force-stop", pkg], capture_output=True)
    subprocess.run(["adb", "shell", "input", "keyevent", "3"], capture_output=True)
    time.sleep(1.5)

def reset_environment():
    """每轮评测开始前，把会被任务修改的系统设置恢复到初始值"""
    cmds = [
        ["adb", "shell", "cmd", "uimode", "night", "no"],                            # 关闭深色主题
        ["adb", "shell", "settings", "put", "system", "screen_brightness_mode", "0"],  # 关闭自动亮度
        ["adb", "shell", "settings", "put", "system", "screen_brightness", "200"],     # 亮度调回较高
    ]
    for c in cmds:
        subprocess.run(c, capture_output=True)
    print("已自动恢复：深色主题关闭、亮度调高")
    input("请手动删除多余的闹钟（只保留 8:30、9:00）和所有 Tom 联系人，完成后按回车开始评测……")

async def main(round_name):
    reset_environment()
    with open("tasks.json", encoding="utf-8") as f:
        tasks = json.load(f)

    out_dir = Path("eval_results") / round_name
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    csv_path = out_dir / f"results_{round_name}.csv"
    for t in tasks:
        reset_device()
        print(f"\n➡️ [{t['id']}] {t['task']}")

        log_buffer = io.StringIO()
        start = time.time()
        try:
            with redirect_stdout(log_buffer):
                answer, steps, tokens = await run_agent(t["task"])
        except Exception as e:
            answer, steps, tokens = f"程序异常: {e}", -1, 0
        seconds = round(time.time() - start, 1)
        answer = answer or ""

        # 每个任务的完整过程存成一个log文件，分析失败时看它
        log_path = out_dir / f"{t['id']:02d}.log"
        log_path.write_text(log_buffer.getvalue() + f"\n最终回答：{answer}\n", encoding="utf-8")

        # 自动判定：有关键词的任务，检查最终回答里有没有
        check = t.get("check")
        if check:
            auto = "通过" if str(check) in answer else "未通过"
        else:
            auto = "需人工"
            

        rows.append({
            "id": t["id"],
            "type": t["type"],
            "task": t["task"],
            "steps": steps,
            "tokens": tokens,
            "seconds": seconds,
            "answer": answer.replace("\n", " "),
            "auto_check": auto,
            "manual_pass": "",
            "failure_type": "",
        })
        save_csv(rows, csv_path)

        print(f" {steps}步 / {tokens} tokens / {seconds} 秒 / 自动判定：{auto}")
    
    print(f"\n全部完成，结果已保存到 {csv_path}")

    # 写成 CSV。utf-8-sig 编码保证用 Excel 或 Numbers 打开时中文不乱码
    # csv_path = out_dir / f"results_{round_name}.csv"
    # with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
    #     writer = csv.DictWriter(f, fieldnames=rows[0].keys())
    #     writer.writeheader()
    #     writer.writerows(rows)
    # print(f"\n全部完成，结果已保存到{csv_path}")

def save_csv(rows, csv_path):
    """把目前已完成的结果写进 CSV。每跑完一条就调用一次，中途出错也不会丢数据"""
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    round_name = sys.argv[1] if len(sys.argv) > 1 else "round1"
    asyncio.run(main(round_name))
