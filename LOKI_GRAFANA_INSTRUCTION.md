# Подробная инструкция: Loki + Grafana + отправка логов из FastAPI

Данная инструкция рассчитана под текущий репозиторий `Actions` (FastAPI + GitHub Actions + деплой по SSH).

## Содержание

- [1. Цель](#1-цель)
- [2. Общая архитектура](#2-общая-архитектура)
- [3. Подготовка файлов в репозитории](#3-подготовка-файлов-в-репозитории)
- [4. Конфигурация Loki](#4-конфигурация-loki)
- [5. Конфигурация Grafana (provisioning)](#5-конфигурация-grafana-provisioning)
- [6. Дашборд Grafana](#6-дашборд-grafana)
- [7. Docker Compose](#7-docker-compose)
- [8. Интеграция логирования в FastAPI-приложение](#8-интеграция-логирования-в-fastapi-приложение)
- [9. Обновление GitHub Actions для деплоя всего стека](#9-обновление-github-actions-для-деплоя-всего-стека)
- [10. Деплой на сервер](#10-деплой-на-сервер)
- [11. Настройка Grafana вручную/автоматически](#11-настройка-grafana-вручнуюавтоматически)
- [12. Проверка логов и панелей](#12-проверка-логов-и-панелей)
- [13. Траблшутинг](#13-траблшутинг)
- [14. Чек-лист по заданию](#14-чек-лист-по-заданию)

## 1. Цель

Выполнить все 3 части задания:

1. Поднять `loki` и `grafana` через `docker-compose` на сервере, убедиться что контейнеры `running`, Grafana доступна на `http://<IP>:3000`. Подключить Data Source `Loki` (`http://loki:3100`).
2. Создать дашборд с двумя панелями: таблица последних логов по метке `{app="my_app"}` и круговая диаграмма распределения по `level`.
3. Добавить в приложение функцию `send_log_to_loki`, отправку логов в Loki по `POST /loki/api/v1/push` (middleware + ручной `POST /log`).

## 2. Общая архитектура

```text
[FastAPI app:8000] --(HTTP POST /loki/api/v1/push)--> [Loki:3100] <--(query LogQL)--> [Grafana:3000]
                        ^                                       ^
                        |                                       |
                        \__________ общая docker-сеть __________/
```

Важное условие: `app`, `loki`, `grafana` должны находиться в **одной** docker-сети. Именно поэтому переводим деплой на `docker-compose`.

## 3. Подготовка файлов в репозитории

В корне репозитория добавить следующую структуру:

```text
Actions/
├── docker-compose.yml
├── loki-config.yaml
├── grafana/
│   ├── provisioning/
│   │   ├── datasources/
│   │   │   └── loki.yml
│   │   └── dashboards/
│   │       └── dashboards.yml
│   └── dashboards/
│       └── app-logs.json
├── main.py
├── requirements.txt
└── .github/workflows/docker-deploy.yml
```

## 4. Конфигурация Loki

**Файл:** `loki-config.yaml`

```yaml
auth_enabled: false

server:
  http_listen_port: 3100
  grpc_listen_port: 9096

common:
  instance_addr: 127.0.0.1
  path_prefix: /loki
  storage:
    filesystem:
      chunks_directory: /loki/chunks
      rules_directory: /loki/rules
  replication_factor: 1
  ring:
    kvstore:
      store: inmemory

query_range:
  results_cache:
    cache:
      embedded_cache:
        enabled: true
        max_size_mb: 100

schema_config:
  configs:
    - from: 2020-10-24
      store: boltdb-shipper
      object_store: filesystem
      schema: v11
      index:
        prefix: index_
        period: 24h

ruler:
  alertmanager_url: http://localhost:9093

analytics:
  reporting_enabled: false
```

## 5. Конфигурация Grafana (provisioning)

**Файл:** `grafana/provisioning/datasources/loki.yml`

```yaml
apiVersion: 1

datasources:
  - name: Loki
    type: loki
    access: proxy
    url: http://loki:3100
    isDefault: true
    editable: true
    version: 1
    jsonData:
      maxLines: 1000
```

**Файл:** `grafana/provisioning/dashboards/dashboards.yml`

```yaml
apiVersion: 1

providers:
  - name: 'app-logs'
    orgId: 1
    folder: 'Logs'
    type: file
    disableDeletion: false
    updateIntervalSeconds: 10
    allowUiUpdates: true
    options:
      path: /var/lib/grafana/dashboards
      foldersFromFilesStructure: true
```

## 6. Дашборд Grafana

**Файл:** `grafana/dashboards/app-logs.json`

Автопровиженится в папке `Logs` как `App Logs (my_app)`. Содержит две панели:
1. `Таблица последних логов по метке {app="my_app"}` (тип `logs`)
2. `Распределение логов по уровню (level)` (тип `piechart`) с запросом `sum by (level) (count_over_time({app="my_app"} [$__range]))`

## 7. Docker Compose

**Файл:** `docker-compose.yml`

Сервисы: `loki`, `grafana`, `app` в общей сети `logging`. Grafana проброшен на `3000`, Loki на `3100`, приложение на `8000`. Приложению задана переменная `LOKI_PUSH_URL=http://loki:3100/loki/api/v1/push`.

## 8. Интеграция логирования в FastAPI-приложение

**requirements.txt** - добавить `httpx>=0.27.0`

**main.py**:
- Функция `send_log_to_loki(message, level, extra, app_name="my_app")` - формирует payload Loki push API (`streams[].stream` с метками `app`, `level`, `values` с `timestamp_ns`), делает `POST` на `LOKI_PUSH_URL` через `httpx.Client`.
- Middleware `loki_logging_middleware` - логирует каждый HTTP-запрос, определяет `level` по статус-коду (5xx error, 4xx warning, 2xx info).
- Эндпоинты `/`, `/time`, `/date` вызывают `send_log_to_loki`.
- `POST /log` принимает JSON `{message, level, extra}`, отправляет в фоновой задаче `BackgroundTasks` через `log_to_loki_bg`.

## 9. Обновление GitHub Actions для деплоя всего стека

**.github/workflows/docker-deploy.yml**:
- Копирует `docker-compose.yml`, `loki-config.yaml`, `grafana/` на сервер в `~/app-stack` через `scp-action`
- На сервере останавливает старый контейнер `fastapi-time` (если был запущен `docker run`)
- Заменяет `image: ghcr.io/.../actions:local-compose` на образ из GHCR с SHA
- Выполняет `docker compose pull loki grafana` (и app при необходимости), `docker compose up -d`
- Чистит образы, логаутится из GHCR

## 10. Деплой на сервер

### Вариант A. Через GitHub Actions (рекомендуемый)
```bash
git add .
git commit -m "Setup Loki+Grafana stack with log shipping and provisioning"
git push origin main
```
Дождаться успешного прогона workflow `Build and Deploy`.

### Вариант B. Вручную на сервере
```bash
ssh <SSH_USER>@<SSH_HOST>
mkdir -p ~/app-stack
cd ~/app-stack

# Скопировать файлы с локальной машины
scp docker-compose.yml loki-config.yaml <SSH_USER>@<SSH_HOST>:~/app-stack/
scp -r grafana <SSH_USER>@<SSH_HOST>:~/app-stack/

# На сервере
docker compose up -d
docker ps
```

## 11. Настройка Grafana вручную/автоматически

После старта стека:
1. Открыть `http://<IP_СЕРВЕРА>:3000` (логин/пароль `admin/admin`)
2. Data Source `Loki` должен появиться автоматически (provisioning) с URL `http://loki:3100`
3. Дашборд `Dashboards → Logs → App Logs (my_app)` должен появиться автоматически
4. Если Data Source не подтянулся - добавить вручную: `Connections → Add new connection → Loki`, URL `http://loki:3100`, `Save & test`

## 12. Проверка логов и панелей

Генерируем логи:
```bash
curl http://<IP_СЕРВЕРА>:8000/
curl http://<IP_СЕРВЕРА>:8000/time
curl http://<IP_СЕРВЕРА>:8000/date

curl -X POST http://<IP_СЕРВЕРА>:8000/log -H "Content-Type: application/json" -d '{"message": "тестовый лог", "level": "info"}'
curl -X POST http://<IP_СЕРВЕРА>:8000/log -H "Content-Type: application/json" -d '{"message": "предупреждение", "level": "warning"}'
curl -X POST http://<IP_СЕРВЕРА>:8000/log -H "Content-Type: application/json" -d '{"message": "ошибка", "level": "error"}'
```

Проверка:
- `Explore → Loki` → запрос `{app="my_app"}` - должны отображаться логи
- `Dashboards → Logs → App Logs (my_app)` - панель с логами и круговая диаграмма по `level`

## 13. Траблшутинг

| Проблема | Причина | Решение |
|---|---|---|
| Loki не доступен из app/grafana | Разные сети | Все в `logging` сети в docker-compose |
| Дашборд не появился | Неправильный путь провиженинга | Проверить монтирования `./grafana/provisioning` и `./grafana/dashboards` |
| Логи не доходят | Неверный `LOKI_PUSH_URL` | В app: `http://loki:3100/loki/api/v1/push` |
| Старый контейнер мешает | Остался после старого деплоя | Workflow останавливает/удаляет `fastapi-time` перед `docker compose up -d` |

Проверка на сервере:
```bash
docker ps
docker logs loki --tail 10
docker logs grafana --tail 10
docker logs fastapi-time --tail 20
```

## 14. Чек-лист по заданию

- [ ] **Часть 1**: `docker-compose` с `loki` и `grafana` поднят, оба контейнера в состоянии `running`
- [ ] **Часть 1**: Grafana открывается на `http://<IP>:3000`
- [ ] **Часть 1**: Data Source `Loki` подключён по `http://loki:3100`, `Save & test` успешен
- [ ] **Часть 2**: Дашборд с панелью таблицы последних логов по `{app="my_app"}`
- [ ] **Часть 2**: Дашборд с панелью круговой диаграммы распределения по `level`
- [ ] **Часть 3**: В приложении реализована функция `send_log_to_loki`, отправляющая `POST` на `/loki/api/v1/push`
- [ ] **Часть 3**: Логи реально отображаются в Grafana
