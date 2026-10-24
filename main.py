import json
import os
import time
from datetime import datetime
from typing import Optional

import httpx
from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI(title="Тестовый API времени")

LOKI_PUSH_URL = os.getenv("LOKI_PUSH_URL", "http://loki:3100/loki/api/v1/push")
APP_NAME = os.getenv("APP_NAME", "my_app")
LOG_LEVEL_DEFAULT = os.getenv("LOG_LEVEL", "info")


def send_log_to_loki(
    message: str,
    level: str = "info",
    extra: Optional[dict] = None,
    app_name: str = APP_NAME,
) -> bool:
    """
    Отправляет лог-сообщение в Loki через POST /loki/api/v1/push
    """
    try:
        timestamp_ns = str(time.time_ns())

        log_payload = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "app": app_name,
            "level": level,
            "message": message,
        }
        if extra:
            log_payload.update(extra)

        stream_labels = {"app": app_name, "level": level}
        values = [[timestamp_ns, json.dumps(log_payload, ensure_ascii=False)]]

        body = {"streams": [{"stream": stream_labels, "values": values}]}

        with httpx.Client(timeout=3.0) as client:
            resp = client.post(LOKI_PUSH_URL, json=body)
            if resp.status_code >= 300:
                print(f"[LOKI] push failed: status={resp.status_code} body={resp.text}")
                return False
        return True
    except Exception as e:
        print(f"[LOKI] send_log_to_loki error: {e}")
        return False


async def log_to_loki_bg(
    message: str,
    level: str = "info",
    extra: Optional[dict] = None,
):
    try:
        send_log_to_loki(message=message, level=level, extra=extra)
    except Exception as e:
        print(f"[LOKI] bg log error: {e}")


@app.middleware("http")
async def loki_logging_middleware(request: Request, call_next):
    start_time = time.time()
    method = request.method
    path = request.url.path

    try:
        response = await call_next(request)
        status_code = response.status_code
        process_time_ms = round((time.time() - start_time) * 1000, 2)

        if status_code >= 500:
            level = "error"
        elif status_code >= 400:
            level = "warning"
        elif status_code >= 200:
            level = "info"
        else:
            level = "debug"

        msg = f"http_request method={method} path={path} status={status_code} duration_ms={process_time_ms}"
        try:
            send_log_to_loki(
                message=msg,
                level=level,
                extra={
                    "method": method,
                    "path": path,
                    "status": status_code,
                    "duration_ms": process_time_ms,
                    "type": "http_access",
                },
            )
        except Exception as e:
            print(f"[LOKI] middleware log error: {e}")

        return response
    except Exception as e:
        process_time_ms = round((time.time() - start_time) * 1000, 2)
        msg = f"http_request_exception method={method} path={path} error={str(e)} duration_ms={process_time_ms}"
        try:
            send_log_to_loki(
                message=msg,
                level="error",
                extra={
                    "method": method,
                    "path": path,
                    "error": str(e),
                    "duration_ms": process_time_ms,
                    "type": "http_exception",
                },
            )
        except Exception as ex:
            print(f"[LOKI] middleware exception log error: {ex}")
        raise


@app.get("/")
def root():
    send_log_to_loki("root endpoint called", level="info", extra={"endpoint": "/"})
    return {"message": "Используй /time для получения текущего времени сервера и /date для текущей даты"}


@app.get("/time")
def get_time():
    now = datetime.now()
    send_log_to_loki("get_time endpoint called", level="info", extra={"endpoint": "/time"})
    return {
        "current_time": now.strftime("%Y-%m-%d %H:%M:%S"),
        "isoformat": now.isoformat(),
        "timestamp": now.timestamp(),
    }


@app.get("/date")
def get_date():
    today = datetime.now().date()
    weekdays = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
    send_log_to_loki("get_date endpoint called", level="info", extra={"endpoint": "/date"})
    return {
        "current_date": today.strftime("%Y-%m-%d"),
        "isoformat": today.isoformat(),
        "year": today.year,
        "month": today.month,
        "day": today.day,
        "weekday": weekdays[today.weekday()],
    }


@app.post("/log")
async def create_log(background_tasks: BackgroundTasks, request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}

    message = body.get("message") or "test log from /log endpoint"
    level = body.get("level") or "info"
    extra = body.get("extra") or {}

    background_tasks.add_task(log_to_loki_bg, message=message, level=level, extra={"type": "manual", **extra})

    return JSONResponse(
        content={
            "status": "accepted",
            "sent_to": LOKI_PUSH_URL,
            "app": APP_NAME,
            "level": level,
            "message": message,
        }
    )
