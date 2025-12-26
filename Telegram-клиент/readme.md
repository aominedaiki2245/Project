
Telegram-клиент — короткая инструкция

1) Установка
cd Telegram-клиент
npm install

2) Настройка
Создайте файл .env на основе .env.example и пропишите:
- TELEGRAM_BOT_TOKEN
- MAIN_BASE_URL (адрес главного модуля)
- AUTH_BASE_URL (адрес auth module, опционально)
- LINK_SECRET (сложный секрет)
- PORT (например 4000)

3) Запуск
node index.js

4) Привязка аккаунта Web ↔️ Telegram
- В Telegram: отправьте /link боту — он выдаст код.
- В Web-клиенте, в личном кабинете добавьте форму «Привязать Telegram», которая вызывает POST /link/confirm на сервере Telegram-клиента со следующими данными:
  {
    "code": "XXXXXX",
    "userId": "<id_from_your_app>",
    "access_token": "<jwt_access_token>",
    "refresh_token": "<refresh_token_optional>",
    "access_exp": <unix_seconds_optional>
  }
  Заголовок запроса: X-LINK-SECRET: <LINK_SECRET>

- После успешного вызова бот уведомит пользователя и сохранит токены для вызовов Main API.

5) Возможности бота
- /link — начать привязку
- /tests — получить список тестов (читает public /tests)
- /take <testId> — создать попытку от имени привязанного пользователя (требуется привязка)
- /answer <qIndex> <choice> — отправить ответ
- /finish — завершить попытку и получить результат
- /status — показать статус привязки
- /unlink — удалить привязку

6) Замечания и улучшения
- Хранение: замените in-memory storage на Redis/Postgres.
- Безопасность: используйте HTTPS, rotate LINK_SECRET, шифруйте refresh tokens.
- OAuth2 alternative: можно интегрировать OAuth flow напрямую или использовать Telegram Login Widget.
