# Тестовый FastAPI бэкенд: время сервера и логи в Loki

Простое приложение на FastAPI, которое возвращает текущее время и дату сервера,
а также отправляет свои логи в Loki. Логи визуализируются в Grafana.

## Возможности

- `GET /`, `GET /time`, `GET /date` — базовые эндпоинты.
- `POST /log` — ручная отправка лог-сообщения в Loki.
- Middleware логирует каждый HTTP-запрос (метод, путь, статус, длительность)
  и отправляет запись в Loki.
- Отправка реализована функцией `send_log_to_loki` (`main.py`): `POST` на
  `/loki/api/v1/push` в формате Loki streams.

## Структура проекта

```text
main.py                              # FastAPI-приложение и отправка логов в Loki
requirements.txt                     # зависимости Python
Dockerfile                           # образ приложения
docker-compose.yml                   # app + Loki + Grafana
loki-config.yaml                     # конфигурация Loki
grafana/
  provisioning/datasources/loki.yml  # datasource Loki
  provisioning/dashboards/dashboards.yml
  dashboards/app-logs.json           # дашборд App Logs (my_app)
.github/workflows/docker-deploy.yml  # сборка образа и деплой
Deployment.md                        # подробная инструкция по деплою
```

## Переменные окружения

| Переменная | По умолчанию | Назначение |
|---|---|---|
| `LOKI_PUSH_URL` | `http://loki:3100/loki/api/v1/push` | URL приёма логов Loki |
| `APP_NAME` | `my_app` | Имя приложения в метках Loki |
| `LOG_LEVEL` | `info` | Уровень логирования по умолчанию |

## Локальный запуск

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

Приложение будет доступно по адресу: http://localhost:8000

Если Loki запущен локально, укажите его адрес:

```bash
LOKI_PUSH_URL=http://localhost:3100/loki/api/v1/push uvicorn main:app --reload
```

Если Loki недоступен, приложение продолжает работать: ошибки отправки логов
только пишутся в stdout и не прерывают запросы.

## Запуск в Docker

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f app
docker compose down
```

Сервисы и порты:

| Сервис | Контейнер | Порты | Описание |
|---|---|---|---|
| `app` | `fastapi-time` | `8120:8000` | FastAPI-приложение |
| `grafana` | `grafana` | `3010:3000` | Grafana UI |
| `loki` | `loki` | `3100` (только внутри сети) | Хранилище логов |

Приложение и Grafana обращаются к Loki по внутреннему адресу `http://loki:3100`
в docker-сети `logging`. Наружу порт `3100` не публикуется.

## Эндпоинты

- `GET /` — приветственное сообщение.
- `GET /time` — текущее время сервера.
- `GET /date` — текущая дата сервера.
- `POST /log` — отправка лог-сообщения в Loki.

### Пример ответа с `/time`

```json
{
  "current_time": "2026-10-17 12:34:56",
  "isoformat": "2026-10-17T12:34:56.123456",
  "timestamp": 1760689296.123456
}
```

### Пример ответа с `/date`

```json
{
  "current_date": "2026-10-23",
  "isoformat": "2026-10-23",
  "year": 2026,
  "month": 10,
  "day": 23,
  "weekday": "пятница"
}
```

### Пример запроса к `/log`

```bash
curl -X POST http://localhost:8120/log \
  -H "Content-Type: application/json" \
  -d '{"message": "проверка логирования", "level": "info"}'
```

```json
{
  "status": "accepted",
  "sent_to": "http://loki:3100/loki/api/v1/push",
  "app": "my_app",
  "level": "info",
  "message": "проверка логирования"
}
```

## API документация

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Grafana

Grafana доступна по адресу `http://<SERVER_IP>:3010`.

Логин — `admin`. Пароль задаётся в `docker-compose.yml`
(`GF_SECURITY_ADMIN_PASSWORD`) и **обязательно меняется** после первого входа.

При старте автоматически создаются:

- datasource `Loki` (`http://loki:3100`, по умолчанию);
- дашборд `App Logs (my_app)` с таблицей последних логов и распределением по уровню.

Пример запроса в Loki: `{app="my_app"}`.

Если provisioning не загрузился, проверьте, что файлы `grafana/` читаются
пользователем контейнера (UID 472):

```bash
chmod -R u+rwX,go+rX grafana   # каталоги 755, файлы 644
docker compose restart grafana
```

## Деплой

Деплой выполняется через GitHub Actions: при push в `main` (или вручную)
собирается образ `ghcr.io/<owner>/<repo>:<commit-sha>` и по SSH разворачивается
на сервере в каталоге `~/app-stack`.

Секреты репозитория (`Settings` → `Secrets and variables` → `Actions`):

| Секрет | Обязательный | Назначение |
|---|---|---|
| `SSH_HOST` | да | IP-адрес или домен сервера |
| `SSH_USER` | да | пользователь для SSH |
| `SSH_PRIVATE_KEY` | да | приватный SSH-ключ |
| `SSH_PORT` | нет | порт SSH (по умолчанию `22`) |

Требования к серверу: Docker и плагин Docker Compose, SSH-доступ по ключу,
открытые порты приложения (`8120`) и Grafana (`3010`).

Пример проверенной конфигурации: Ubuntu 26.04, Docker 29.1.3,
Docker Compose 2.40.3, каталог стека `/root/app-stack`.

Подробное описание шагов, откат и траблшутинг — в [Deployment.md](Deployment.md).

## Проверка после запуска

```bash
docker compose ps
curl http://localhost:8120/time
curl -s http://localhost:3010/api/health
docker exec loki wget -qO- http://localhost:3100/loki/api/v1/labels
```

Ожидается: контейнеры `fastapi-time`, `grafana`, `loki` в статусе `Up`,
ответ API с текущим временем, health Grafana `database: ok`, метки Loki
`app` и `level`.

## Безопасность

- SSH-доступ только по ключу: `PasswordAuthentication no`,
  `PermitRootLogin prohibit-password`.
- Перед изменением `sshd_config` делайте бэкап конфигурации.
- Смените пароль Grafana после первого входа; не публикуйте `admin/admin`.
- Не коммитьте приватные ключи и токены. Для CI/CD используйте секреты
  репозитория.
- Закрывайте неиспользуемые порты firewall'ом; наружу публикуйте только
  необходимые сервисы.
