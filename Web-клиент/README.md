# Web Client модуль

Часть системы массовых опросов и тестирования.

## Функции
- Доступ через веб-браузер
- Аутентификация через GitHub, Yandex ID, одноразовый код
- Сессии через Redis
- JWT-токены, автоматическое обновление
- Горизонтальное масштабирование

## Технологии
- Node.js + Express
- Redis
- Cookies + JWT

## Запуск
```bash
cd Web-клиент
npm install
cp .env.example .env
node app.js
