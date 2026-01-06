require('dotenv').config();
const express = require('express');
const cookieParser = require('cookie-parser');
const redis = require('redis');
const { v4: uuidv4 } = require('uuid');

const app = express();
const port = process.env.PORT || 3000;

// Подключение к Redis
const redisClient = redis.createClient({
  url: process.env.REDIS_URL || 'redis://localhost:6379'
});

redisClient.on('error', (err) => console.error('Redis Client Error', err));

(async () => {
  await redisClient.connect();
  console.log('Подключено к Redis');
})();

// Middleware
app.use(cookieParser());
app.use(express.static('public'));

// Вспомогательные функции для работы с сессиями
async function getSessionData(sessionToken) {
  if (!sessionToken) return null;
  const data = await redisClient.get(sessionToken);
  return data ? JSON.parse(data) : null;
}

async function setSessionData(sessionToken, data, ttl = 3600 * 24) { // 24 часа по умолчанию
  await redisClient.set(sessionToken, JSON.stringify(data), { EX: ttl });
}

async function deleteSession(sessionToken) {
  if (sessionToken) {
    await redisClient.del(sessionToken);
  }
}

// Middleware для прикрепления сессии к запросу
async function sessionMiddleware(req, res, next) {
  const sessionToken = req.cookies.sessionToken;
  req.session = await getSessionData(sessionToken);
  req.sessionToken = sessionToken; // для удобства
  next();
}

app.use(sessionMiddleware);

// Главная страница — базовая логика статусов
app.get('/', async (req, res) => {
  if (!req.session) {
    // Неизвестный пользователь
    return res.send(`
      <h1>Добро пожаловать!</h1>
      <p>Для начала работы необходимо авторизоваться:</p>
      <ul>
        <li><a href="/login?type=github">Войти через GitHub</a></li>
        <li><a href="/login?type=yandex">Войти через Yandex ID</a></li>
        <li><a href="/login?type=code">Войти по коду</a></li>
      </ul>
    `);
  }

  if (req.session.status === 'Anonymous') {
    return res.send(`
      <h1>Ожидание авторизации...</h1>
      <p>Вы начали процесс входа. Пожалуйста, завершите его во всплывшем окне.</p>
      <p><a href="/">Обновить</a></p>
    `);
  }

  if (req.session.status === 'Authorized') {
    return res.send(`
      <h1>Личный кабинет</h1>
      <p>Добро пожаловать, пользователь!</p>
      <p>Список тестов, дисциплин и т.д. (в разработке)</p>
      <a href="/logout">Выйти</a>
    `);
  }

  // Если статус неизвестен — редирект на главную
  res.redirect('/');
});
// Маршрут для начала авторизации
app.get('/login', async (req, res) => {
  const type = req.query.type; // github, yandex или code

  // Если тип не указан — редирект на главную
  if (!type || !['github', 'yandex', 'code'].includes(type)) {
    return res.redirect('/');
  }

  let sessionToken = req.sessionToken;
  let isNewSession = false;

  // Если сессии нет или она не Anonymous — создаём новую
  if (!sessionToken || !req.session || req.session.status === 'Authorized') {
    sessionToken = uuidv4();
    isNewSession = true;
  }

  const loginToken = uuidv4();

  // Сохраняем в Redis: статус Anonymous + loginToken
  await setSessionData(sessionToken, {
    status: 'Anonymous',
    loginToken: loginToken
  });

  // Устанавливаем cookie (httpOnly для безопасности)
  if (isNewSession) {
    res.cookie('sessionToken', sessionToken, {
      httpOnly: true,
      secure: process.env.NODE_ENV === 'production', // HTTPS в проде
      maxAge: 24 * 60 * 60 * 1000 // 24 часа
    });
  }

  // Здесь будет редирект на Authorization Server
  // Пока заглушка — просто сообщение
  const authUrl = `${process.env.AUTH_SERVER_URL || 'http://localhost:4000'}/auth?type=${type}&state=${loginToken}`;

  return res.send(`
    <h1>Перенаправление на авторизацию...</h1>
    <p>Тип: ${type}</p>
    <p>В реальной системе здесь будет редирект на:<br>
    <a href="${authUrl}" target="_blank">${authUrl}</a></p>
    <p>После подтверждения вернитесь сюда и обновите страницу.</p>
    <a href="/">← На главную</a>
  `);
});
// Маршрут выхода
app.get('/logout', async (req, res) => {
  if (req.sessionToken) {
    await deleteSession(req.sessionToken);
    res.clearCookie('sessionToken');
  }
  res.redirect('/');
});
app.listen(port, () => {
  console.log(`Web Client запущен на http://localhost:${port}`);
});
