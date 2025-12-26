/**
 * Telegram client: Telegraf bot + Express endpoints for linking and admin actions.
 * Run: npm install && node index.js
 *
 * Design:
 * - /link in Telegram creates a one-time code mapped to tgId
 * - Web client calls POST /link/confirm { code, userId, access_token, refresh_token? } with header X-LINK-SECRET
 * - Bot stores mapping and can act on behalf of user using stored tokens
 *
 * NOTE:
 * - In production: use persistent DB (Redis) and HTTPS for /link/confirm; rotate LINK_SECRET.
 * - Refresh token flow: this example will try to refresh using AUTH_BASE_URL /token/refresh if stored refresh_token exists.
 */

require('dotenv').config();
const { Telegraf } = require('telegraf');
const express = require('express');
const bodyParser = require('body-parser');
const axios = require('axios');
const { v4: uuidv4 } = require('uuid');

const BOT_TOKEN = process.env.TELEGRAM_BOT_TOKEN;
const MAIN_BASE = process.env.MAIN_BASE_URL || 'http://localhost:8080';
const AUTH_BASE = process.env.AUTH_BASE_URL || 'http://localhost:8081';
const LINK_SECRET = process.env.LINK_SECRET || 'change-me';
const PORT = Number(process.env.PORT || 4000);
const STORAGE = process.env.STORAGE || 'memory'; // memory/file (simple)

// ========== Storage (simple pluggable) ==========
// For demo we keep everything in memory. Replace with Redis/Postgres in prod.
const storage = {
  // code -> { tgId, expiresAt }
  codes: new Map(),
  // tgId -> { userId, accessToken, refreshToken, accessExp }
  links: new Map()
};

function saveCode(code, tgId, ttlSeconds = 300) {
  const expiresAt = Date.now() + ttlSeconds * 1000;
  storage.codes.set(code, { tgId, expiresAt });
}
function takeCode(code) {
  const rec = storage.codes.get(code);
  if (!rec) return null;
  // one-time: remove
  storage.codes.delete(code);
  if (rec.expiresAt < Date.now()) return null;
  return rec.tgId;
}
function saveLink(tgId, linkObj) {
  storage.links.set(String(tgId), linkObj);
}
function getLinkByTg(tgId) {
  return storage.links.get(String(tgId));
}
function getLinkByUserId(userId) {
  for (const [tg, obj] of storage.links.entries()) {
    if (obj.userId === userId) return { tgId: tg, ...obj };
  }
  return null;
}

// ========== Helper utilities ==========

function genCode(len = 6) {
  // 6-character alphanumeric uppercase
  const s = '23456789ABCDEFGHJKLMNPQRSTUVWXYZ'; // avoid confusing 0/O,1/I
  let out = '';
  for (let i = 0; i < len; ++i) out += s[Math.floor(Math.random() * s.length)];
  return out;
}

async function tryRefreshTokens(stored) {
  // stored: { refreshToken }
  if (!stored || !stored.refreshToken) return null;
  try {
    const r = await axios.post(`${AUTH_BASE}/token/refresh`, { refresh_token: stored.refreshToken });
    if (r.status === 200) {
      const data = r.data;
      // expected: { access_token, refresh_token, expires_at, user }
      return {
        accessToken: data.access_token,
        refreshToken: data.refresh_token || stored.refreshToken,
        accessExp: data.expires_at ? Number(data.expires_at) * 1000 : Date.now() + 60*60*1000
      };
    }
  } catch (e) {
    // ignore
  }
  return null;
}

// API call to main module with user's access token; auto-refresh if expired (best-effort)
async function callMainAsUser(tgId, method, path, body = null) {
  const link = getLinkByTg(tgId);
  if (!link || !link.accessToken) {
    throw { code: 401, message: 'User not linked or no token' };
  }

  // try request
  try {
    const headers = { Authorization: `Bearer ${link.accessToken}` };
    const url = `${MAIN_BASE}${path}`;
    const opts = { headers, method, url, data: body, timeout: 5000 };
    const resp = await axios(opts);
    return resp.data;
  } catch (err) {
    // if 401 and we have refreshToken, try refresh via auth module
    const status = err.response && err.response.status;
    if ((status === 401 || status === 403) && link.refreshToken) {
      const refreshed = await tryRefreshTokens(link);
      if (refreshed) {
        // update stored
        link.accessToken = refreshed.accessToken;
        link.refreshToken = refreshed.refreshToken;
        link.accessExp = refreshed.accessExp;
        saveLink(tgId, link);
        // retry
        const headers = { Authorization: `Bearer ${link.accessToken}` };
        const url = `${MAIN_BASE}${path}`;
        const opts = { headers, method, url, data: body, timeout: 5000 };
        const resp = await axios(opts);
        return resp.data;
      }
    }
    // propagate error
    if (err.response && err.response.data) throw { code: err.response.status, message: err.response.data };
    throw { code: 500, message: err.message };
  }
}

// ========== Telegram Bot using Telegraf ==========
if (!BOT_TOKEN) {
  console.error('TELEGRAM_BOT_TOKEN is not set. Fill .env and restart.');
  process.exit(1);
}
const bot = new Telegraf(BOT_TOKEN);

// Command: /start
bot.start((ctx) => {
  ctx.reply(`Привет, ${ctx.from.first_name || 'пользователь'}!\n` +
    'Я бот для доступа к тестам и опросам.\n' +
    'Используйте /link чтобы привязать Ваш аккаунт Web → Telegram.\n' +
    'Далее: /tests — список тестов, /take <testId> — пройти тест.');
});

// Command: /help
bot.help((ctx) => {
  ctx.reply('/link — привязать аккаунт\n/tests — посмотреть доступные тесты\n/take <testId> — начать попытку\n/status — показать привязку\n/unlink — отвязать аккаунт');
});

// Command: /link
bot.command('link', async (ctx) => {
  const tgId = ctx.from.id;
  const code = genCode(6);
  saveCode(code, tgId, 5 * 60); // 5 minutes
  const msg = `Чтобы привязать аккаунт, откройте Web-клиент (в личном кабинете — Привязка Telegram) и введите код:\n\n` +
              `КОД: *${code}*\n\n` +
              `Код действует 5 минут. Ваш Telegram id: \`${tgId}\`.`;
  await ctx.replyWithMarkdown(msg);
});

// Command: /status
bot.command('status', async (ctx) => {
  const tgId = ctx.from.id;
  const link = getLinkByTg(tgId);
  if (!link) {
    return ctx.reply('Аккаунт не привязан. Выполните /link.');
  }
  const ttl = link.accessExp ? Math.max(0, Math.floor((link.accessExp - Date.now())/1000)) : null;
  ctx.reply(`Привязан как userId=${link.userId}\nAccess expires in: ${ttl ? ttl + 's' : 'unknown'}`);
});

// Command: /unlink
bot.command('unlink', async (ctx) => {
  const tgId = ctx.from.id;
  storage.links.delete(String(tgId));
  ctx.reply('Привязка удалена.');
});

// Command: /tests — list tests (public endpoint on main module)
bot.command('tests', async (ctx) => {
  try {
    // main /tests is public in example; else require user token
    const r = await axios.get(`${MAIN_BASE}/tests`);
    const tests = r.data;
    if (!Array.isArray(tests) || tests.length === 0) {
      return ctx.reply('Тесты не найдены.');
    }
    let txt = 'Список тестов:\n\n';
    tests.forEach(t => {
      txt += `• ${t.title} — id: \`${t.id}\`\n`;
    });
    txt += '\nЧтобы пройти тест: /take <testId>';
    ctx.replyWithMarkdown(txt);
  } catch (e) {
    ctx.reply('Ошибка при получении списка тестов: ' + (e.message || 'unknown'));
  }
});

// Command: /take <testId>
bot.command('take', async (ctx) => {
  const parts = ctx.message.text.split(/\s+/);
  if (parts.length < 2) return ctx.reply('Использование: /take <testId>');
  const testId = parts[1].trim();
  const tgId = ctx.from.id;
  try {
    const result = await callMainAsUser(tgId, 'post', `/tests/${testId}/attempts`);
    // result expected { id: attemptId }
    const attemptId = result.id || result.ID || null;
    if (!attemptId) {
      return ctx.reply('Сервер вернул неожидимый результат: ' + JSON.stringify(result));
    }
    // Save last attempt id with tg user for later
    const link = getLinkByTg(tgId) || {};
    link.lastAttemptId = attemptId;
    saveLink(tgId, link);
    ctx.reply(`Попытка запущена. attemptId: ${attemptId}\nЧтобы ответить на вопрос используйте /answer <qIndex> <choice>\nКогда закончите: /finish`);
  } catch (e) {
    ctx.reply(`Ошибка при старте попытки: ${e.message || JSON.stringify(e)}`);
  }
});

// Command: /answer <qIndex> <choice>
bot.command('answer', async (ctx) => {
  const parts = ctx.message.text.split(/\s+/);
  if (parts.length < 3) return ctx.reply('Использование: /answer <qIndex> <choice>');
  const qIndex = Number(parts[1]);
  const choice = Number(parts[2]);
  if (Number.isNaN(qIndex) || Number.isNaN(choice)) return ctx.reply('qIndex и choice должны быть числами');
  const tgId = ctx.from.id;
  const link = getLinkByTg(tgId);
  if (!link || !link.lastAttemptId) return ctx.reply('Нет запущенной попытки. Начните /take <testId>');
  try {
    await callMainAsUser(tgId, 'put', `/attempts/${link.lastAttemptId}/answer`, { qIndex, choice });
    ctx.reply(`Ответ сохранён (q=${qIndex}, choice=${choice})`);
  } catch (e) {
    ctx.reply(`Ошибка при сохранении ответа: ${e.message || JSON.stringify(e)}`);
  }
});

// Command: /finish
bot.command('finish', async (ctx) => {
  const tgId = ctx.from.id;
  const link = getLinkByTg(tgId);
  if (!link || !link.lastAttemptId) return ctx.reply('Нет запущенной попытки.');
  try {
    const resp = await callMainAsUser(tgId, 'post', `/attempts/${link.lastAttemptId}/finish`);
    ctx.reply(`Тест завершён. Результат: ${JSON.stringify(resp)}`);
    // Optionally clear lastAttemptId
    delete link.lastAttemptId;
    saveLink(tgId, link);
  } catch (e) {
    ctx.reply(`Ошибка при завершении попытки: ${e.message || JSON.stringify(e)}`);
  }
});

// Graceful error handling
bot.catch((err) => {
  console.error('Bot error', err);
});

// ========== Express HTTP API (for Web client to confirm link) ==========
const app = express();
app.use(bodyParser.json());

// POST /link/confirm
// Body: { code, userId, access_token, refresh_token?, access_exp? }
// Header: X-LINK-SECRET: <secret>
app.post('/link/confirm', async (req, res) => {
  try {
    const secret = req.get('X-LINK-SECRET');
    if (!secret || secret !== LINK_SECRET) return res.status(403).json({ error: 'forbidden' });

    const { code, userId, access_token, refresh_token, access_exp } = req.body;
    if (!code || !userId || !access_token) return res.status(400).json({ error: 'bad_request' });
    const tgId = takeCode(code);
    if (!tgId) return res.status(404).json({ error: 'invalid_or_expired_code' });

    // Save mapping
    const obj = {
      userId,
      accessToken: access_token,
      refreshToken: refresh_token,
      accessExp: access_exp ? Number(access_exp) * 1000 : Date.now() + 60 * 60 * 1000
    };
    saveLink(tgId, obj);

    // Notify user in Telegram
    try {
      await bot.telegram.sendMessage(tgId, `Аккаунт успешно привязан (userId=${userId}). Теперь вы можете запускать тесты из бота.`);
    } catch (e) {
      console.warn('Failed to notify user via Telegram', e.message || e);
    }

    return res.json({ ok: true });
  } catch (e) {
    console.error('link/confirm error', e);
    return res.status(500).json({ error: 'internal' });
  }
});

// Simple admin endpoint to list linked users (protected by LINK_SECRET)
app.get('/links', (req, res) => {
  const secret = req.get('X-LINK-SECRET');
  if (!secret || secret !== LINK_SECRET) return res.status(403).json({ error: 'forbidden' });
  const out = [];
  for (const [tg, obj] of storage.links.entries()) {
    out.push({ tgId: tg, userId: obj.userId, accessExp: obj.accessExp });
  }
  res.json(out);
});

// Start bot and express
(async () => {
  try {
    // Start Telegram polling
    bot.launch().then(() => console.log('Telegram bot started (polling)'));

    // Start Express
    app.listen(PORT, () => {
      console.log(`Telegram-client HTTP API listening on ${PORT}`);
      console.log(`Expose /link/confirm endpoint and protect with X-LINK-SECRET header`);
    });

    // Enable graceful stop
    process.once('SIGINT', () => bot.stop('SIGINT'));
    process.once('SIGTERM', () => bot.stop('SIGTERM'));
  } catch (e) {
    console.error('Startup error', e);
    process.exit(1);
  }
})();
