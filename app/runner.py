import asyncio
import threading
from datetime import datetime

from app.store import TASKS
from phone_agent import run_agent

# 只有一台手机：同一时间只能跑一个任务，其余排队
DEVICE_LOCK = threading.Lock()

def execute_task(task_id: str, max_steps: int):
    """后台执行。注意是普通def: FastAPI 会把它放进线程池跑，
    不会卡住接口（run_agent里的大模型调用时同步阻塞的）"""
    task = TASKS[task_id]
    with DEVICE_LOCK:
        task.status = "running"
        try:
            answer, steps, tokens = asyncio.run(run_agent(task.instruction, max_steps))
            answer = answer or ""
            task.answer, task.steps, task.tokens = answer, steps, tokens
            task.status = "failed" if answer.startswith("⚠️超过最大步数") else "success"
        except Exception as e:
            task.status = "failed"
            task.answer = f"程序异常：{e}"
        finally:
            task.finished_at = datetime.now()