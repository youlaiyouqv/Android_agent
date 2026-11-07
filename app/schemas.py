from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# 数据模型，相当于Java的DTO
class TaskCreate(BaseModel):
    """POST /tasks 的请求体"""
    instruction: str = Field(min_length=1, description="自然语言指令，如：打开设置，告诉我Androi版本号")
    max_steps: int = Field(default=30, ge=1, le=50, description="最大步数")

class TaskInfo(BaseModel):
    """返回给前端的任务信息"""
    id: str
    instruction: str
    status: Literal["pending", "running", "success", "failed"]
    answer: str | None = None
    steps: int | None = None
    tokens: int | None = None
    created_at: datetime
    finished_at: datetime | None = None