require('dotenv').config();
const express = require('express');
const cookieParser = require('cookie-parser');
const { v4: uuidv4 } = require('uuid');
const redis = require('redis');
const path = require('path');
const axios = require('axios');

const app = express();
const port = process.env.PORT || 3000;

// Подключение к Redis
const redisClient = redis.createClient({
  url: process.env.REDIS_URL || 'redis://localhost:6379',
  // Отключаем сохранение на диск
  socket: {
    reconnectStrategy: false
  },
  disableOfflineQueue: true,
  // Команда для отключения RDB/AOF
  // Будет выполнена после подключения
});
(async () => {
  await redisClient.connect();
  console.log('Подключено к Redis');

  // Отключаем сохранение на диск
  await redisClient.configSet('save', '');
  await redisClient.configSet('appendonly', 'no');
})();

// Middleware
app.use(cookieParser());
app.use(express.static(path.join(__dirname, 'public')));

// Функции сессий
async function getSessionData(sessionToken) {
  if (!sessionToken) return null;
  const data = await redisClient.get(sessionToken);
  return data ? JSON.parse(data) : null;
}

async function setSessionData(sessionToken, data, ttl = 86400) {
  await redisClient.set(sessionToken, JSON.stringify(data), { EX: ttl });
}

async function deleteSession(sessionToken) {
  if (sessionToken) await redisClient.del(sessionToken);
}

// Middleware сессии
async function sessionMiddleware(req, res, next) {
  const sessionToken = req.cookies.sessionToken;
  req.session = await getSessionData(sessionToken);
  req.sessionToken = sessionToken;
  next();
}

app.use(sessionMiddleware);

// Главная страница
app.get('/', async (req, res) => {
  if (!req.session) {
    return res.sendFile(path.join(__dirname, 'public', 'index.html'));
  }

  if (req.session.status === 'Anonymous') {
    return res.send(`
      <h1>Ожидание авторизации...</h1>
      <p>Пожалуйста, подтвердите вход во всплывшем окне.</p>
      <p><a href="/">Обновить статус</a></p>
    `);
  }

  if (req.session.status === 'Authorized') {
    return res.sendFile(path.join(__dirname, 'public', 'dashboard.html'));
  }

  return res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

// /login
app.get('/login', async (req, res) => {
  const type = req.query.type;

  if (!type || !['github', 'yandex', 'code'].includes(type)) {
    return res.redirect('/');
  }

  let sessionToken = req.sessionToken;
  let isNewSession = false;

  if (!sessionToken || req.session?.status === 'Authorized') {
    sessionToken = uuidv4();
    isNewSession = true;
  }

  const loginToken = uuidv4();

  await setSessionData(sessionToken, {
    status: 'Anonymous',
    loginToken: loginToken
  });

  if (isNewSession) {
    res.cookie('sessionToken', sessionToken, { httpOnly: true, maxAge: 86400000 });
  }

  const authUrl = `\( {process.env.AUTH_SERVER_URL || 'http://localhost:4000'}/auth?type= \){type}&state=${loginToken}`;

  return res.send(`
    <h1>Перенаправление на ${type}</h1>
    <p>В реальной системе здесь будет редирект.</p>
    <p>Ссылка для теста:</p>
    <a href="\( {authUrl}" target="_blank"> \){authUrl}</a>
    <p><a href="/">← На главную</a></p>
  `);
});

// /logout
app.get('/logout', async (req, res) => {
  if (req.sessionToken) {
    await deleteSession(req.sessionToken);
    res.clearCookie('sessionToken');
  }
  res.redirect('/');
});

// Временный маршрут для теста Authorized
app.get('/debug/auth-success', async (req, res) => {
  if (!req.session || req.session.status !== 'Anonymous') {
    return res.redirect('/');
  }

  await setSessionData(req.sessionToken, {
    status: 'Authorized',
    accessToken: 'fake-access-token',
    refreshToken: 'fake-refresh-token'
  });

  res.send(`
    <h1>Авторизация имитирована!</h1>
    <p>Статус изменён на Authorized.</p>
    <a href="/">Перейти в личный кабинет</a>
  `);
});
// Прокси для действий авторизованного пользователя
app.all('/api/*', async (req, res) => {
  if (!req.session || req.session.status !== 'Authorized') {
    return res.status(401).send('Не авторизован');
  }

  let accessToken = req.session.accessToken;

  const targetPath = req.path.substring(4); // убираем /api
  const mainUrl = `\( {process.env.MAIN_MODULE_URL || 'http://localhost:5000'} \){targetPath}${req.url.split('?')[1] ? '?' + req.url.split('?')[1] : ''}`;

  try {
    const response = await axios({
      method: req.method,
      url: mainUrl,
      headers: {
        'Authorization': `Bearer ${accessToken}`,
        'Content-Type': 'application/json'
      },
      data: req.body
    });

    res.status(response.status).json(response.data);
  } catch (error) {
    if (error.response?.status === 401) {
      // Токен истёк — refresh
      try {
        const refreshRes = await axios.post(`${process.env.AUTH_SERVER_URL || 'http://localhost:4000'}/refresh`, {
          refreshToken: req.session.refreshToken
        });

        const { accessToken: newAccess, refreshToken: newRefresh } = refreshRes.data;

        await setSessionData(req.sessionToken, {
          status: 'Authorized',
          accessToken: newAccess,
          refreshToken: newRefresh || req.session.refreshToken
        });

        // Повтор запроса
        const retry = await axios({
          method: req.method,
          url: mainUrl,
          headers: { 'Authorization': `Bearer ${newAccess}` },
          data: req.body
        });

        res.status(retry.status).json(retry.data);
      } catch (refreshError) {
        await deleteSession(req.sessionToken);
        res.clearCookie('sessionToken');
        res.status(401).send('Сессия истекла');
      }
    } else {
      res.status(error.response?.status || 500).send('Ошибка действия');
    }
  }
});
app.listen(port, () => {
  console.log('Web Client запущен на http://localhost:${port}');
});
