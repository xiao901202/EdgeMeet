from fastapi import FastAPI
from app import routes

app = FastAPI(title="Conference Assistant API")

# 掛載路由
app.include_router(routes.router)

# 啟動指令： uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
