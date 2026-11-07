from app.schemas import TaskInfo

# 任务存储：先用内存字典，以后换Redis/数据库只改这里
TASKS: dict[str, TaskInfo] = {}

def get_store() -> dict[str, TaskInfo]:
    return TASKS