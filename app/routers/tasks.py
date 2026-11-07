import uuid
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from app.runner import execute_task
from app.schemas import TaskCreate, TaskInfo
from app.store import get_store

router = APIRouter(prefix="/tasks", tags=["tasks"])


# 接口
@router.post("", response_model=TaskInfo, status_code=202)
def create_task(
    req: TaskCreate,
    background_tasks: BackgroundTasks,
    store: dict[str, TaskInfo] = Depends(get_store),
):
    """提交任务，立刻返回任务id, 不等Agent跑完"""
    task = TaskInfo(
        id=uuid.uuid4().hex[:8],
        instruction=req.instruction,
        status="pending",
        created_at=datetime.now(),
    )
    store[task.id] = task
    background_tasks.add_task(execute_task, task.id, req.max_steps)
    return task

@router.get("/{task_id}", response_model=TaskInfo)
def get_task(task_id: str, store: dict[str, TaskInfo] = Depends(get_store)):
    """查询任务状态和结果"""
    if task_id not in store:
        raise HTTPException(status_code=404, detail="任务不存在")
    return store[task_id]