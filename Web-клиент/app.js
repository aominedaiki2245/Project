require('dotenv').config();
const express = require('express');
const cookieParser = require('cookie-parser');

const app = express();
const port = process.env.PORT || 3000;

app.use(cookieParser());
app.use(express.static('public'));

app.get('/', (req, res) => {
  res.send('<h1>Web Client модуль работает!</h1><p>Аутентификация и сессии в разработке...</p>');
});

app.listen(port, () => {
  console.log(`Web Client запущен на http://localhost:${port}`);
});
