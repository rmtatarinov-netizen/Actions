from datetime import datetime
from fastapi import FastAPI

app = FastAPI(title="Тестовый API времени")

@app.get("/")
def root():
    return {"message": "Используй /time для получения текущего времени сервера"}

@app.get("/time")
def get_time():
    now = datetime.now()
    return {
        "current_time": now.strftime("%Y-%m-%d %H:%M:%S"),
        "isoformat": now.isoformat(),
        "timestamp": now.timestamp()
    }
