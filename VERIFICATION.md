# Результаты проверки

Проверено 14 ноября 2026 года.

- `npm ci` / установка по package-lock и `npm run build`: production-сборка React/Vite успешна.
- API pytest после исправлений: 11 passed на SQLite и 11 passed на PostgreSQL 16.
- Клиент API: 3 passed (`node --test frontend/src/api.test.js`): обновление CSRF, отсутствие повтора обычных ошибок, диагностика недоступного сервера.
- Новый локальный запуск `run_local.py`: успешно собирает React, применяет миграции и запускает один HTTP-сервер.
- HTTP-проверка локального сервера: регистрация → допуск организатором → вступление в команду → задача → чат; production JS/CSS возвращают 200.
- Начальная миграция Alembic успешно применена на PostgreSQL 16.
- Демонстрационные данные успешно созданы на PostgreSQL.
- Flask test client: `/` и обе ссылки JS/CSS из собранного HTML возвращают 200; содержимое соответствует production-сборке.
- Python compileall: без синтаксических ошибок.
- ZIP проверен на целостность; секреты, пользовательская база, venv и node_modules не включены.

Не проверено: интерактивный рендеринг в реальном браузере, мобильное устройство, полная Docker-сборка образа, работа после публичного развёртывания. Инфраструктура браузерного QA в этой сессии недоступна. Compose и Dockerfile подготовлены для самостоятельного запуска; PostgreSQL для проверок запущен отдельно в Docker.

Для повторения тестов PostgreSQL задайте TEST_DATABASE_URL на **отдельную пустую тестовую базу**. ВАЖНО: тесты создают и удаляют таблицы в указанной базе. Никогда не указывайте рабочую базу.

Пример macOS/Linux:

```sh
TEST_DATABASE_URL=postgresql+psycopg://user:password@localhost/hackflow_tests python -m pytest -q backend/test_app.py
```

Windows PowerShell:

```powershell
$env:TEST_DATABASE_URL = "postgresql+psycopg://user:password@localhost/hackflow_tests"
python -m pytest -q backend/test_app.py
Remove-Item Env:TEST_DATABASE_URL
```
