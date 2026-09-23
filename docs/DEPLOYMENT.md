# Развёртывание и подключение LLM

Этот документ закрывает внешние ворота релиза: живой LLM, публичный URL и
CIDR проверяющего. Код готов; здесь — точные шаги, которые нужно выполнить с
реальными учётными данными и инфраструктурой.

## 1. Подключение реального LLM

Прокси использует OpenAI-совместимые нестриминговые chat-завершения. Заполните
в `.env` (не коммитьте его):

```dotenv
LLM_BASE_URL=https://api.openai.com/v1   # включая /v1, если требуется
LLM_API_KEY=sk-...                        # реальный ключ
LLM_MODEL=gpt-4o-mini                     # имя модели провайдера
LLM_TIMEOUT=30
LLM_CA_BUNDLE=                            # путь к PEM корпоративного CA, если требуется
ALLOW_HTTP_LLM=false                      # HTTPS обязателен, кроме одобренного локального HTTP
```

По умолчанию клиент использует системное хранилище доверенных CA. Если endpoint
подписан приватным корпоративным CA, сохраните только публичную цепочку CA в PEM,
смонтируйте файл в контейнер только для чтения и задайте контейнерный путь через
`LLM_CA_BUNDLE`. Не отключайте проверку TLS и не помещайте клиентские приватные
ключи в этот файл.

Поставляемый Compose уже задаёт `/app/config/ca/russian-trusted-root.pem` для
текущей цепочки AlfaGen. Ожидаемый SHA-1 thumbprint корневого сертификата (только
для идентификации) — `8FF915CCAB7BC16F8C5C8099D53E0E115B3AEC2F`; тест блокирует
незаметную замену файла. При ротации CA обновите файл только из официального
источника и измените ожидаемый отпечаток после независимой проверки.

Для сетевого allowlist владелец AlfaGen должен разрешить исходящий публичный
IP/CIDR машины или NAT-шлюза, с которого контейнер обращается к endpoint по TCP
443. Локальные адреса `127.0.0.1`, адрес контейнера и `BENCHMARK_CIDRS` для этого
не подходят: `BENCHMARK_CIDRS` защищает входящий `/process`, а LLM allowlist
контролирует отдельный исходящий канал. После добавления адреса проверьте, что
`POST {LLM_BASE_URL}/chat/completions` больше не возвращает 403 от WAF/шлюза.

Проверка после перезапуска:

```sh
curl -X POST http://127.0.0.1:8000/v1/chat \
  -H "Authorization: Bearer $DEMO_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"request_id":"demo-1","message":"Summarize: Клиент: Иванов Иван; Email: demo@example.org"}'
```

Ожидается `{"request_id":"demo-1","answer":"..."}`. Если `LLM_BASE_URL` пуст,
`/v1/chat` возвращает 503 (fail-closed) — это корректно.

### Совместимость с провайдером
- Адаптер шлёт `POST {base}/chat/completions` с `{"model", "stream": false,
  "messages": [...]}`.
- Если провайдер требует другой путь или формат, поправьте `src/alfa_pii/llm.py`
  (единственное место сетевого протокола).
- HTTPS обязателен; перенаправления и фоновые прокси отключены.

## 2. Публичный URL проверяющего

Проверяющему нужен внешне доступный URL. Варианты:

### Вариант A: Docker Compose (рекомендуется)
```sh
python tools/bootstrap.py          # создаёт .env с секретами
# отредактируйте .env: LLM_*, BENCHMARK_CIDRS, BIND_ADDRESS, PORT
docker compose up --build -d
```
`compose.yaml` публикует на `BIND_ADDRESS:PORT` (по умолчанию loopback). Для
внешнего доступа задайте `BIND_ADDRESS=0.0.0.0` и `PORT=8000`, а TLS завершите
одобренным входным шлюзом (nginx/Caddy/ALB). Не доверяйте пересылаемым
заголовкам — `proxy_headers=False`.

### Вариант B: нативный запуск
```sh
uv sync --frozen
uv run python -m alfa_pii   # слушает 0.0.0.0:8000
```
Используйте файрвол или явную привязку к loopback вне Docker.

### Проверка доступности
```sh
curl http://<public-host>:<port>/health/ready   # {"status":"ready"}
```

## 3. CIDR проверяющего

Проверяющий может обращаться без Bearer-ключа, если его исходный IP в белом
списке. Задайте в `.env`:

```dotenv
BENCHMARK_CIDRS=203.0.113.0/24   # точные CIDR пиров проверяющего
BENCHMARK_CONSUMER=benchmark
```

- Пустой список = нет анонимного доступа. В поставляемом `.env.example`
  хакатонный режим открыт для всех; для закрытого развёртывания очистите список.
- Для публичного хакатонного прогона без известных IP можно временно задать
  `BENCHMARK_CIDRS=0.0.0.0/0,::/0`. Это открывает `/process` без ключа всем
  клиентам IPv4/IPv6; используйте только синтетические данные и верните точные
  CIDR после прогона. `/v1/chat` и `/metrics` по-прежнему требуют Bearer-ключ.
- Проверка идёт по фактическому IP пира, не по `X-Forwarded-For`.

## 4. Проверка полной цепочки

```sh
# 1. Маскирование
curl -X POST http://<host>:<port>/process \
  -H "Content-Type: application/json" \
  -d '{"payload":"Клиент: Иванов Иван; Email: demo@example.org","payload_id":"demo-1"}'
# -> {"result":"Клиент: ⟦PERSON:...⟧; Email: ⟦EMAIL:...⟧"}

# 2. Восстановление (тот же id, тот же маск)
curl -X POST http://<host>:<port>/process \
  -H "Content-Type: application/json" \
  -d '{"payload":"Клиент: ⟦PERSON:...⟧; Email: ⟦EMAIL:...⟧","payload_id":"demo-1"}'
# -> {"result":"Клиент: Иванов Иван; Email: demo@example.org"}

# 3. LLM-прокси (после настройки LLM)
curl -X POST http://<host>:<port>/v1/chat \
  -H "Authorization: Bearer $DEMO_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"request_id":"demo-2","message":"Summarize: Клиент: Иванов Иван"}'
```

## 5. Метрики и приватность

- `/metrics` требует Bearer-ключ.
- Метрики размечены по потребителю (`consumer` label).
- Журналы не содержат payload, маппинги, учётные данные, сырые ID или PII.
- `/health/ready` проверяет Redis и пул воркеров.

## 6. Чек-лист перед отправкой

- [ ] `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` заполнены, `/v1/chat` отвечает 200.
- [ ] Публичный URL доступен проверяющему, `/health/ready` → 200.
- [ ] `BENCHMARK_CIDRS` содержит точные CIDR проверяющего.
- [ ] Docker-образ собран и загружен на машине с достаточным диском.
- [ ] `uv run pytest` (включая реальный Redis) и оба quality-гейта проходят.
- [ ] ZIP только с исходниками: `uv run python tools/package.py --output alfa-pii-source.zip`.
