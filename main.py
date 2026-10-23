from datetime import datetime
from fastapi import FastAPI

app = FastAPI(title="Тестовый API времени")

@app.get("/")
def root():
    return {"message": "Используй /time для получения текущего времени сервера и /date для текущей даты"}

@app.get("/time")
def get_time():
    now = datetime.now()
    return {
        "current_time": now.strftime("%Y-%m-%d %H:%M:%S"),
        "isoformat": now.isoformat(),
        "timestamp": now.timestamp()
    }

@app.get("/date")
def get_date():
    today = datetime.now().date()
    weekdays = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
    return {
        "current_date": today.strftime("%Y-%m-%d"),
        "isoformat": today.isoformat(),
        "year": today.year,
        "month": today.month,
        "day": today.day,
        "weekday": weekdays[today.weekday()]
    }
