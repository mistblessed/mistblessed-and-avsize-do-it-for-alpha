# Матрица «требование-тест»

Исходные документы: предоставленное задание AlfaGen, ds.pdf онбординг (9 страниц)
и критерии оценки (4 страницы). Никакой исходный PDF не распространяется в этом пакете.

| Требование | Реализация | Исполняемое доказательство |
|---|---|---|
| Все 17 типов и исходные смещения | detection/engine.py | test_required_category_offsets (три варианта регистра) |
| Синтетическая регрессия; независимый holdout ожидает ручной проверки | detection/engine.py; tools/validate_holdout.py | test_holdout_regression.py (24 случая); docs/HOLDOUT_REVIEW.md |
| Публичные имена/адреса филиалов | контекстное подавление | test_public_and_non_personal_text; реальный NER-тест |
| Текстовые даты, разделители, переставленные даты | ограниченные контекстные правила | фикстуры основных категорий |
| Точное layout- и токен-восстановление | transformation/masking.py | Unicode property-тест; точный roundtrip |
| Без рекурсивного/чужого расширения токенов | однопроходный ограниченный поиск | test_no_recursive_token_restoration; тест ограниченных токенов |
| Точная JSON-схема процесса | api/app.py | test_contract_replays_and_conflict |
| Отклонение неизвестных полей /process | api/app.py | test_process_rejects_unknown_fields |
| Per-consumer rate limit | api/app.py; ratelimit.py | test_per_consumer_rate_limit |
| Метрики по потребителям | api/app.py | test_metrics_include_consumer_label |
| Валидация конфига | config.py | test_settings_reject_inconsistent_capacity |
| Health-check воркеров | api/app.py; service.py | test_ready_checks_engine_health |
| Property-тесты roundtrip | transformation/masking.py | test_multiple_entities_roundtrip; test_layout_mask_preserves_length_and_non_alnum |
| Повторы и конкурентный первый запрос | отпечатки содержимого + атомарное состояние | сервисные тесты повторов/конкурентности; реальный Redis-тест |
| Общее состояние между процессами | RedisStore | test_real_redis_cross_instance_atomicity_expiry_and_encryption |
| Авторизованное восстановление, отключённый потребитель | политика потребителя на запрос | тесты изоляции и отключённого потребителя |
| Изменения политики | сравнение сохранённой действующей политики | test_policy_change_cannot_replay_old_weaker_mask |
| Истечение и целостность состояния | TTL/tombstone; AEAD-привязка | тесты истечения и шифра |
| Fail-closed при недоступном Redis | фиксированный безопасный 503 | test_state_failure_fails_closed |
| Реальное поведение прокси-транспорта | LLMClient | проверка тела мок-HTTP-провода; реальное демо провайдера остаётся внешним |
| Новые данные ответа защищены | сканирование ответа до восстановления | test_proxy_masks_wire_data_and_restores_only_known_tokens |
| Нет публичного доступа по умолчанию | ключи и фактические CIDR пиров | тест белого списка/пересылаемых заголовков |
| Безопасная валидация и ограниченный ввод | валидация модели; граница тела ASGI | test_validation_size_limit_and_metrics |
| Нет PII в журналах | фиксированные структурированные метаданные | test_payloads_absent_from_logs с включённым логированием |
| CPU-работа вне цикла событий | ограниченный ProcessPoolExecutor | test_real_process_pool |
| Длинный текст/границы чанков | блочная обработка с перекрытием | большой лексический токен-тест; тесты границ |
| Расширение правил без правок ядра | YAML extra_rules | test_conditional_policy_and_custom_rule |
| Режимы/условный бонус | политики потребителей | тест политики и демо-потребители |
| Метрики и доказательства нагрузки | Prometheus; tools/load.py | тест метрик; сохранённый JSON нагрузки |
| README и ZIP только с исходниками | README; tools/package.py | проверка пакета и процедура чистого запуска |

## Допущения и неэквивалентности
- Звёздочные маски по умолчанию не являются установленными официальными эталонными масками.
- Протокол провайдера предполагается OpenAI-совместимым до подтверждения реальным вызовом.
- Пример на 100000 слов/лексических токенов не является проверенным вводом на 100000 токенов DeepSeek.
- Оценённый TPS — это символы/4, явно помеченные как оценка.
- Сгенерированные данные разработки на 340 случаев не являются независимыми и содержат повторяющиеся негативы.
- Один экземпляр Redis и ограниченные tombstone не обещают HA или бесконечную безопасность повторов.
- Linux/Python 3.11 — цель Docker; локальная проверка выполнялась на Windows/Python 3.12.
