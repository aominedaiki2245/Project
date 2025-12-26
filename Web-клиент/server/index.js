// Простая proxy/auth helper: выставляет HttpOnly refresh cookie после oauth callback
// и проксирует API запросы к main module.
// Требует: npm i

require('dotenv').config();
const express = require('express');
const fetch = require('cross-fetch');
const cookieParser = require('cookie-parser');
const { createProxyMiddleware } = require('http-proxy-middleware');
const url = require('url');

const PORT = process.env.PORT || 3001;
const AUTH_BASE = process.env.AUTH_BASE_URL || 'http://localhost:8081';
const MAIN_BASE = process.env.MAIN_BASE_URL || 'http://localhost:8080';
const FRONTEND = process.env.FRONTEND_URL || 'http://localhost:5173';
const COOKIE_DOMAIN = process.env.COOKIE_DOMAIN || 'localhost';
const COOKIE_SECURE = (process.env.COOKIE_SECURE === 'true');

const app = express();
app.use(express.json());
app.use(cookieParser());

// 1) Redirect to auth module start
app.get('/auth/start/:provider', (req, res) => {
  const provider = req.params.provider;
  // redirect to auth module start
  res.redirect(`${AUTH_BASE}/oauth/start/${provider}`);
});

// 2) Callback proxy:
//    Если ваш Auth module отвечает на /oauth/callback JSON {access_token, refresh_token, user}
//    то этот endpoint забирает ответ, ставит HttpOnly cookie refresh_token и отдаёт минимальную HTML,
//    который отправит access_token в окно-опенер через postMessage (popup flow).
app.get('/auth/callback', async (req, res) => {
  // Forward query string to Auth module callback
  const q = url.format({ query: req.query });
  try {
    const r = await fetch(`${AUTH_BASE}/oauth/callback${q}`, { method: 'GET' });
    const bodyText = await r.text();

    // Популярный вариант: auth module возвращает JSON. Если это JSON - распарсим.
    let parsed;
    try {
      parsed = JSON.parse(bodyText);
    } catch (e) {
      // Если auth module уже возвращает HTML (например postMessage wrapper),
      // просто передаём содержимое дальше.
      res.set('Content-Type', 'text/html');
      res.send(bodyText);
      return;
    }

    // ожидаем parsed.access_token, parsed.refresh_token, parsed.user
    const access = parsed.access_token;
    const refresh = parsed.refresh_token;

    // set refresh token as http only cookie (server-side session management)
    if (refresh) {
      res.cookie('refresh_token', refresh, {
        httpOnly: true,
        secure: COOKIE_SECURE,
        domain: COOKIE_DOMAIN,
        sameSite: 'lax',
        path: '/auth/refresh'
      });
    }

    // Return small HTML that posts access token to opener and closes popup
    const origin = FRONTEND;
    const html = `<!doctype html>
<html>
  <head><meta charset="utf-8"><title>Auth callback</title></head>
  <body>
    <script>
      (function(){
        try {
          const payload = ${JSON.stringify(parsed)};
          // send to opener window
          window.opener.postMessage({ type: 'oauth', payload: payload }, ${JSON.stringify(origin)});
        } catch(e){}
        window.close();
      })();
    </script>
    <p>Авторизация завершена. Можно закрыть окно.</p>
  </body>
</html>`;
    res.set('Content-Type','text/html');
    res.send(html);

  } catch (err) {
    console.error('callback proxy error', err);
    res.status(500).send('proxy error');
  }
});

// 3) Refresh token endpoint — вызывает Auth module /token/refresh,
//    читает refresh_token из HttpOnly cookie и возвращает новый access token.
//    Auth module returns JSON {access_token, refresh_token, expires_at}
app.post('/auth/refresh', async (req, res) => {
  const rt = req.cookies['refresh_token'];
  if (!rt) return res.status(401).json({ error: 'no refresh token' });

  try {
    const r = await fetch(`${AUTH_BASE}/token/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: rt })
    });
    if (r.status !== 200) {
      // clear cookie
      res.clearCookie('refresh_token', { path: '/auth/refresh' });
      return res.status(401).json({ error: 'refresh failed' });
    }
    const data = await r.json();

    // rotate refresh cookie if server sent a new refresh_token
    if (data.refresh_token) {
      res.cookie('refresh_token', data.refresh_token, {
        httpOnly: true,
        secure: COOKIE_SECURE,
        domain: COOKIE_DOMAIN,
        sameSite: 'lax',
        path: '/auth/refresh'
      });
    }

    res.json({ access_token: data.access_token, expires_at: data.expires_at, user: data.user });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'internal' });
  }
});

// 4) Simple logout — clear refresh cookie
app.post('/auth/logout', (req, res) => {
  res.clearCookie('refresh_token', { path: '/auth/refresh' });
  res.json({ ok: true });
});

// 5) Proxy API to main module: forwards Authorization header from client
//    /api/* -> MAIN_BASE/*
app.use('/api', createProxyMiddleware({
  target: MAIN_BASE,
  changeOrigin: true,
  pathRewrite: {'^/api' : ''},
  onProxyReq: (proxyReq, req, res) => {
    // leave Authorization header from client (so client includes access_token)
    // nothing to change here
  },
  logLevel: 'warn'
}));

app.listen(PORT, () => {
  console.log(`Proxy server listening ${PORT}`);
  console.log(`Auth base: ${AUTH_BASE}, Main base: ${MAIN_BASE}`);
});
