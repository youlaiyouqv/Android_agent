from fastapi import FastAPI

from app.routers import tasks

# from phone_agent import run_agent

app = FastAPI(title="Android Agent API")
app.include_router(tasks.router)