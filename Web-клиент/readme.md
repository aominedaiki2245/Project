Web-клиент (React + Node.js)
Назначение

Web-клиент предоставляет браузерный интерфейс для системы массовых опросов и тестирования.
Клиент взаимодействует с двумя backend-модулями:

Модуль авторизации (Auth module, Go) — аутентификация через внешние сервисы, выдача JWT, управление правами.

Главный модуль (Main module, C++) — бизнес-логика: тесты, вопросы, попытки, ответы.

Архитектура разделяет:

Frontend (React) — UI, навигация, отображение тестов и прохождение опросов.

Backend proxy (Node.js / Express) — безопасная работа с refresh-токенами (HttpOnly cookies), проксирование API-запросов к основному сервису.

Такое разделение упрощает безопасность и масштабирование.

Архитектура взаимодействия
Browser (React)
   |
   |  /auth/start, /auth/refresh
   v
Node.js proxy (Express)
   |                    \
   |                     -> Main module (C++)  /tests, /attempts, ...
   |
   -> Auth module (Go)   /oauth/*, /verify, /token/refresh

Почему нужен Node.js proxy

Refresh-токены хранятся в HttpOnly cookie, недоступных JavaScript.

Proxy обновляет access-token при истечении срока действия.

React-клиент никогда напрямую не работает с refresh-токенами.

Структура каталога
Web-клиент/
├─ README.md              ← этот файл
├─ server/                ← Node.js proxy
│  ├─ index.js
│  ├─ package.json
│  └─ .env.example
└─ client/                ← React (Vite)
   ├─ package.json
   ├─ vite.config.js
   ├─ index.html
   └─ src/
      ├─ main.jsx
      ├─ App.jsx
      ├─ apiClient.js
      ├─ auth.js
      ├─ pages/
      │  ├─ LoginPage.jsx
      │  ├─ TestsPage.jsx
      │  └─ AttemptPage.jsx
      └─ components/
         └─ Nav.jsx

Функциональность
Реализовано

Авторизация через внешние OAuth-провайдеры (Google, GitHub).

Получение и обновление JWT (access + refresh).

Просмотр списка тестов.

Запуск попытки прохождения теста.

Отправка ответов и завершение попытки.

Контроль доступа на основе ролей и разрешений (через backend).

Упрощено (осознанно)

UI минималистичен, без сложного дизайна.

Отображение вопросов сделано в демонстрационном виде.

Основной акцент — архитектура и взаимодействие сервисов.

Переменные окружения
Web-клиент/server/.env
PORT=3001
AUTH_BASE_URL=http://localhost:8081
MAIN_BASE_URL=http://localhost:8080
FRONTEND_URL=http://localhost:5173

COOKIE_DOMAIN=localhost
COOKIE_SECURE=false


Пояснения:

AUTH_BASE_URL — адрес модуля авторизации (Go).

MAIN_BASE_URL — адрес главного модуля (C++).

FRONTEND_URL — адрес React-приложения (используется для postMessage).

COOKIE_SECURE=true — обязательно включить в production (HTTPS).

Установка и запуск (локально)
1. Запустить backend-модули

Убедитесь, что запущены:

Auth module → http://localhost:8081

Main module → http://localhost:8080

2. Node.js proxy
cd Web-клиент/server
npm install
cp .env.example .env
node index.js


Proxy будет доступен на:
http://localhost:3001

3. React frontend
cd Web-клиент/client
npm install
npm run dev


Frontend будет доступен на:
http://localhost:5173

Процесс авторизации (коротко)

Пользователь нажимает Login with Google / GitHub.

Открывается popup /auth/start/{provider}.

Auth module выполняет OAuth-аутентификацию.

Proxy:

сохраняет refresh-token в HttpOnly cookie;

передаёт access-token в окно клиента через postMessage.

React сохраняет access-token и использует его для API-запросов.

При 401 Unauthorized access-token автоматически обновляется.
