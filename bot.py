import os
import logging
import asyncio
import sys
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import redis
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, CallbackContext, JobQueue
)
import pytz

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Глобальные настройки
class Config:
    """Конфигурация бота"""
    TELEGRAM_TOKEN: Optional[str] = None
    WEB_CLIENT_URL = "http://localhost:3000"
    CORE_API_URL = "http://core-service:8082"
    AUTH_API_URL = "http://auth-service:8081"
    REDIS_URL = "redis://redis:6379/0"
    POLLING_INTERVAL_LOGIN = 10  # секунды для проверки входа
    POLLING_INTERVAL_NOTIFICATIONS = 30  # секунды для уведомлений
    LOGIN_TOKEN_EXPIRY = 300  # секунды для токена входа

# Подключение к Redis
redis_client = redis.Redis.from_url(Config.REDIS_URL, decode_responses=True)

class UserStatus:
    UNKNOWN = "unknown"
    ANONYMOUS = "anonymous"
    AUTHORIZED = "authorized"

class SystemMonitor:
    """Мониторинг состояния системы"""

    def __init__(self):
        self.services = {
            'core-service': {'status': '🟢 Онлайн', 'port': 8082, 'url': Config.CORE_API_URL},
            'auth-service': {'status': '🟢 Онлайн', 'port': 8081, 'url': Config.AUTH_API_URL},
            'web-client': {'status': '🟢 Онлайн', 'port': 3000, 'url': Config.WEB_CLIENT_URL},
            'postgres': {'status': '🟢 Онлайн', 'port': 5432},
            'mongodb': {'status': '🟢 Онлайн', 'port': 27017},
            'redis': {'status': '🟢 Онлайн', 'port': 6379, 'url': Config.REDIS_URL},
        }

        tz = pytz.timezone('Europe/Moscow')
        self.stats = {
            'start_time': datetime.now(tz),
            'total_commands': 0,
            'active_users': 0,
        }

    def get_status(self) -> str:
        """Получить статус системы"""
        tz = pytz.timezone('Europe/Moscow')
        now = datetime.now(tz)
        lines = [
            "🖥️ *СТАТУС СИСТЕМЫ*",
            f"Время: {now.strftime('%H:%M:%S')}",
            f"Активна: {(now - self.stats['start_time']).seconds // 60} мин",
            "",
            "*Сервисы:*"
        ]

        for service, info in self.services.items():
            lines.append(f"• {service}: {info['status']} :{info['port']}")

        lines.extend([
            "",
            "*Статистика:*",
            f"Команд выполнено: {self.stats['total_commands']}",
            f"Активных пользователей: {self.stats['active_users']}",
            "",
            f"🌐 Веб-интерфейс: {Config.WEB_CLIENT_URL}",
            f"🔧 API Core: {Config.CORE_API_URL}",
            f"🔐 API Auth: {Config.AUTH_API_URL}",
        ])

        return "\n".join(lines)

    def get_services(self) -> str:
        """Получить детальную информацию о сервисах"""
        lines = ["🔧 *СЕРВИСЫ СИСТЕМЫ*", ""]

        for service, info in self.services.items():
            lines.append(f"*{service.upper()}*")
            lines.append(f"Статус: {info['status']}")
            lines.append(f"Порт: `{info['port']}`")
            if 'url' in info:
                lines.append(f"URL: `{info['url']}`")
            lines.append("")

        return "\n".join(lines)

    def get_help(self) -> str:
        """Получить справку"""
        return """🆘 *ПОМОЩЬ ПО КОМАНДАМ*

*Основные команды:*
/start - Начало работы
/status - Статус системы
/services - Информация о сервисах
/help - Эта справка
/login - Авторизация (опционально с type: github, yandex, code)
/logout - Выход (опционально с all=true для всех устройств)
/test - Пример команды для тестирования (требует авторизации)

*Технические данные:*
📊 PostgreSQL: `localhost:5432`
🗄️ MongoDB: `localhost:27017`
⚡ Redis: `localhost:6379`

🚧 *В РАЗРАБОТКЕ:* 
• Прохождение тестов
• Личный кабинет
• Уведомления
"""

class TelegramBot:
    """Основной класс бота"""

    def __init__(self, token: str):
        self.token = token
        self.monitor = SystemMonitor()
        self.application: Optional[Application] = None
        self.job_queue: Optional[JobQueue] = None

    def generate_login_token(self) -> str:
        """Генерировать токен входа"""
        import uuid
        return str(uuid.uuid4())

    def get_user_data(self, chat_id: int) -> Optional[Dict[str, Any]]:
        """Получить данные пользователя из Redis"""
        data = redis_client.get(str(chat_id))
        if data:
            return json.loads(data)
        return None

    def set_user_data(self, chat_id: int, data: Dict[str, Any]):
        """Сохранить данные пользователя в Redis"""
        redis_client.set(str(chat_id), json.dumps(data),
                         ex=Config.LOGIN_TOKEN_EXPIRY if data.get('status') == UserStatus.ANONYMOUS else None)

    def delete_user_data(self, chat_id: int):
        """Удалить данные пользователя из Redis"""
        redis_client.delete(str(chat_id))

    async def initiate_login(self, chat_id: int, login_type: str, update: Update = None, query = None):
        """Инициировать авторизацию (общий метод для message и callback)"""
        user_data = self.get_user_data(chat_id)
        self.monitor.stats['total_commands'] += 1

        if user_data and user_data.get('status') == UserStatus.AUTHORIZED:
            message_text = "Вы уже авторизованы."
        else:
            # Генерируем токен входа
            login_token = self.generate_login_token()

            # Сохраняем в Redis как анонимный
            self.set_user_data(chat_id, {
                'status': UserStatus.ANONYMOUS,
                'login_token': login_token,
                'login_time': datetime.now().isoformat()
            })

            # Запрос к Auth API
            auth_url = f"{Config.AUTH_API_URL}/login?type={login_type}&token={login_token}"
            try:
                response = requests.get(auth_url)
                if response.status_code == 200:
                    auth_response = response.json()
                    message_text = auth_response.get('message', 'Авторизация инициирована. Пожалуйста, завершите вход через предоставленную ссылку.')
                    if 'url' in auth_response:
                        message_text += f"\nСсылка: {auth_response['url']}"
                else:
                    message_text = f"Ошибка авторизации: {response.status_code}"
            except Exception as e:
                logger.error(f"Error in login request: {e}")
                message_text = "Произошла ошибка при авторизации."

        # Отправляем ответ в зависимости от типа update
        if query:  # Для callback - редактируем сообщение
            await query.edit_message_text(message_text)
        elif update.message:  # Для обычного сообщения
            await update.message.reply_text(message_text)

    async def handle_login(self, update: Update, context: CallbackContext):
        """Обработчик /login для сообщений"""
        chat_id = update.effective_chat.id
        user_data = self.get_user_data(chat_id)
        args = context.args
        login_type = args[0] if args else None

        if user_data and user_data.get('status') == UserStatus.AUTHORIZED:
            await update.message.reply_text("Вы уже авторизованы.")
            return

        if login_type in ['github', 'yandex', 'code']:
            await self.initiate_login(chat_id, login_type, update=update)
            return

        # Показываем клавиатуру выбора
        keyboard = [
            [InlineKeyboardButton("GitHub", callback_data='login_github')],
            [InlineKeyboardButton("Yandex ID", callback_data='login_yandex')],
            [InlineKeyboardButton("Code", callback_data='login_code')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "Пожалуйста, выберите метод авторизации:",
            reply_markup=reply_markup
        )

    async def handle_logout(self, update: Update, context: CallbackContext):
        """Обработчик /logout"""
        chat_id = update.effective_chat.id
        user_data = self.get_user_data(chat_id)
        args = context.args
        all_devices = args and args[0] == 'all=true'

        self.monitor.stats['total_commands'] += 1

        if not user_data or user_data.get('status') != UserStatus.AUTHORIZED:
            await update.message.reply_text("Вы не авторизованы.")
            return

        # Удаляем данные из Redis
        self.delete_user_data(chat_id)

        if all_devices:
            # Запрос к Auth API для выхода со всех устройств
            try:
                response = requests.post(f"{Config.AUTH_API_URL}/logout", json={'all': True}, headers={'Authorization': f"Bearer {user_data['access_token']}"})
                if response.status_code == 200:
                    await update.message.reply_text("Вы вышли из всех устройств.")
                else:
                    await update.message.reply_text("Ошибка при выходе из всех устройств.")
            except Exception as e:
                logger.error(f"Error in logout all: {e}")
                await update.message.reply_text("Ошибка при выходе.")
            return

        await update.message.reply_text("Вы вышли из системы.")

    async def refresh_tokens(self, chat_id: int) -> bool:
        """Обновить токены с помощью refresh_token"""
        user_data = self.get_user_data(chat_id)
        if not user_data or 'refresh_token' not in user_data:
            return False

        try:
            response = requests.post(f"{Config.AUTH_API_URL}/refresh", headers={'Authorization': f"Bearer {user_data['refresh_token']}"})
            if response.status_code == 200:
                tokens = response.json()
                user_data['access_token'] = tokens['access_token']
                user_data['refresh_token'] = tokens['refresh_token']
                self.set_user_data(chat_id, user_data)
                return True
            else:
                self.delete_user_data(chat_id)
                return False
        except Exception as e:
            logger.error(f"Error refreshing tokens: {e}")
            self.delete_user_data(chat_id)
            return False

    async def check_auth_status(self, chat_id: int) -> Optional[Dict]:
        """Проверить статус аутентификации для анонимного пользователя"""
        user_data = self.get_user_data(chat_id)
        if not user_data or user_data['status'] != UserStatus.ANONYMOUS:
            return None

        login_token = user_data['login_token']
        try:
            response = requests.get(f"{Config.AUTH_API_URL}/check_login?token={login_token}")
            if response.status_code == 200:
                data = response.json()
                if data['status'] == 'approved':
                    user_data['status'] = UserStatus.AUTHORIZED
                    user_data['access_token'] = data['access_token']
                    user_data['refresh_token'] = data['refresh_token']
                    del user_data['login_token']
                    del user_data['login_time']
                    self.set_user_data(chat_id, user_data)
                    return {'message': 'Авторизация успешна! Теперь вы можете использовать защищенные команды.'}
                elif data['status'] == 'denied':
                    self.delete_user_data(chat_id)
                    return {'message': 'Авторизация отклонена.'}
                elif data['status'] == 'expired':
                    self.delete_user_data(chat_id)
                    return {'message': 'Срок действия токена истек. Пожалуйста, попробуйте войти заново.'}
            return None
        except Exception as e:
            logger.error(f"Error checking auth status: {e}")
            return None

    async def handle_authorized_command(self, update: Update, context: CallbackContext, endpoint: str):
        """Общий обработчик для авторизованных команд"""
        chat_id = update.effective_chat.id
        user_data = self.get_user_data(chat_id)

        if not user_data or user_data['status'] != UserStatus.AUTHORIZED:
            await update.message.reply_text("Пожалуйста, авторизуйтесь с помощью /login.")
            return

        headers = {'Authorization': f"Bearer {user_data['access_token']}"}

        try:
            response = requests.get(f"{Config.CORE_API_URL}/{endpoint}", headers=headers)
            if response.status_code == 200:
                result = response.json()
                await update.message.reply_text(str(result))
            elif response.status_code == 401:
                if await self.refresh_tokens(chat_id):
                    # Повторить запрос после обновления
                    headers['Authorization'] = f"Bearer {self.get_user_data(chat_id)['access_token']}"
                    response = requests.get(f"{Config.CORE_API_URL}/{endpoint}", headers=headers)
                    if response.status_code == 200:
                        result = response.json()
                        await update.message.reply_text(str(result))
                    else:
                        await update.message.reply_text("Ошибка после обновления токена.")
                else:
                    await update.message.reply_text("Сессия истекла. Пожалуйста, авторизуйтесь заново.")
            else:
                await update.message.reply_text(f"Ошибка: {response.status_code}")
        except Exception as e:
            logger.error(f"Error in authorized command: {e}")
            await update.message.reply_text("Произошла ошибка.")

    async def on_start(self, update: Update, context: CallbackContext):
        """Обработчик /start"""
        self.monitor.stats['total_commands'] += 1
        keyboard = [
            [InlineKeyboardButton("Статус", callback_data='status')],
            [InlineKeyboardButton("Сервисы", callback_data='services')],
            [InlineKeyboardButton("Помощь", callback_data='help')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "👋 Привет! Это бот для системы тестирования.\n"
            "Пожалуйста, авторизуйтесь с помощью /login для полного доступа.",
            reply_markup=reply_markup
        )

    async def show_main_menu(self, query):
        """Показать основное меню"""
        keyboard = [
            [InlineKeyboardButton("Статус", callback_data='status')],
            [InlineKeyboardButton("Сервисы", callback_data='services')],
            [InlineKeyboardButton("Помощь", callback_data='help')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "👋 Привет! Это бот для системы тестирования.\n"
            "Пожалуйста, авторизуйтесь с помощью /login для полного доступа.",
            reply_markup=reply_markup
        )

    async def on_status(self, update: Update, context: CallbackContext):
        """Обработчик /status"""
        self.monitor.stats['total_commands'] += 1
        keyboard = [[InlineKeyboardButton("🔙 Вернуться назад", callback_data='back')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(self.monitor.get_status(), parse_mode='Markdown', reply_markup=reply_markup)

    async def on_services(self, update: Update, context: CallbackContext):
        """Обработчик /services"""
        self.monitor.stats['total_commands'] += 1
        keyboard = [[InlineKeyboardButton("🔙 Вернуться назад", callback_data='back')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(self.monitor.get_services(), parse_mode='Markdown', reply_markup=reply_markup)

    async def on_help(self, update: Update, context: CallbackContext):
        """Обработчик /help"""
        self.monitor.stats['total_commands'] += 1
        keyboard = [[InlineKeyboardButton("🔙 Вернуться назад", callback_data='back')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(self.monitor.get_help(), parse_mode='Markdown', reply_markup=reply_markup)

    async def on_test(self, update: Update, context: CallbackContext):
        """Обработчик /test - пример авторизованной команды"""
        self.monitor.stats['total_commands'] += 1
        await self.handle_authorized_command(update, context, 'test')

    async def on_callback(self, update: Update, context: CallbackContext):
        """Обработчик callback-запросов"""
        query = update.callback_query
        await query.answer()

        keyboard_back = [[InlineKeyboardButton("🔙 Вернуться назад", callback_data='back')]]
        reply_markup_back = InlineKeyboardMarkup(keyboard_back)

        if query.data == 'status':
            await query.edit_message_text(
                text=self.monitor.get_status(),
                parse_mode='Markdown',
                reply_markup=reply_markup_back
            )
        elif query.data == 'services':
            await query.edit_message_text(
                text=self.monitor.get_services(),
                parse_mode='Markdown',
                reply_markup=reply_markup_back
            )
        elif query.data == 'help':
            await query.edit_message_text(
                text=self.monitor.get_help(),
                parse_mode='Markdown',
                reply_markup=reply_markup_back
            )
        elif query.data.startswith('login_'):
            login_type = query.data.split('_')[1]
            chat_id = query.message.chat_id
            await self.initiate_login(chat_id, login_type, query=query)
        elif query.data == 'logout':
            temp_context = CallbackContext.from_update(update, self.application)
            await self.handle_logout(update, temp_context)
            await query.edit_message_text("Сеанс завершен.")
        elif query.data == 'back':
            await self.show_main_menu(query)

    async def on_unknown(self, update: Update, context: CallbackContext):
        """Обработчик неизвестных команд"""
        await update.message.reply_text(
            "❓ Нет такой команды.\n"
            "Используйте /help для списка доступных команд.",
            parse_mode='Markdown'
        )

    async def poll_login_checks(self, context: CallbackContext):
        """Циклическая проверка статусов входа для анонимных пользователей"""
        keys = redis_client.keys('*')  # Получаем все ключи (chat_ids)
        responses = {}

        for key in keys:
            try:
                chat_id = int(key)
                result = await self.check_auth_status(chat_id)
                if result:
                    responses[chat_id] = result['message']
            except ValueError:
                continue

        # Отправляем сообщения
        for chat_id, message in responses.items():
            try:
                await context.bot.send_message(chat_id=chat_id, text=message)
            except Exception as e:
                logger.error(f"Error sending login update to {chat_id}: {e}")

    async def poll_notifications(self, context: CallbackContext):
        """Циклическая проверка уведомлений для авторизованных пользователей"""
        keys = redis_client.keys('*')
        responses = {}

        for key in keys:
            try:
                chat_id = int(key)
                user_data = self.get_user_data(chat_id)
                if user_data and user_data['status'] == UserStatus.AUTHORIZED:
                    # Запрос к Core /notifications
                    try:
                        response = requests.get(
                            f"{Config.CORE_API_URL}/notifications",
                            headers={'Authorization': f"Bearer {user_data['access_token']}"}
                        )
                        if response.status_code == 200:
                            notifications = response.json().get('notifications', [])
                            if notifications:
                                responses[chat_id] = '\n'.join(notifications)
                                # Удаляем уведомления
                                requests.delete(
                                    f"{Config.CORE_API_URL}/notifications",
                                    headers={'Authorization': f"Bearer {user_data['access_token']}"}
                                )
                        elif response.status_code == 401:
                            if not await self.refresh_tokens(chat_id):
                                continue
                    except Exception as e:
                        logger.error(f"Error fetching notifications for {chat_id}: {e}")
            except ValueError:
                continue

        # Отправляем уведомления
        for chat_id, message in responses.items():
            try:
                await context.bot.send_message(chat_id=chat_id, text=f"Уведомления:\n{message}")
            except Exception as e:
                logger.error(f"Error sending notifications to {chat_id}: {e}")

    def setup_application(self):
        """Настройка приложения"""
        self.application = Application.builder().token(self.token).build()
        self.job_queue = self.application.job_queue

        # Регистрируем обработчики
        self.application.add_handler(CommandHandler("start", self.on_start))
        self.application.add_handler(CommandHandler("status", self.on_status))
        self.application.add_handler(CommandHandler("services", self.on_services))
        self.application.add_handler(CommandHandler("help", self.on_help))
        self.application.add_handler(CommandHandler("login", self.handle_login))
        self.application.add_handler(CommandHandler("logout", self.handle_logout))
        self.application.add_handler(CommandHandler("test", self.on_test))  # Пример
        self.application.add_handler(CallbackQueryHandler(self.on_callback))
        self.application.add_handler(MessageHandler(filters.COMMAND, self.on_unknown))

        # Регистрируем обработчик ошибок
        self.application.add_error_handler(self.error_handler)

        # Настраиваем циклические задачи
        self.job_queue.run_repeating(self.poll_login_checks, interval=Config.POLLING_INTERVAL_LOGIN, first=0)
        self.job_queue.run_repeating(self.poll_notifications, interval=Config.POLLING_INTERVAL_NOTIFICATIONS, first=0)

    async def error_handler(self, update: Update, context: CallbackContext):
        """Обработчик ошибок"""
        logger.error(f"Ошибка при обработке обновления {update}: {context.error}")

    def run(self):
        """Запуск бота"""
        self.setup_application()

        # Запускаем polling
        logger.info("🤖 Бот запущен. Нажмите Ctrl+C для остановки")
        self.application.run_polling()

def main():
    """Точка входа"""
    logger.info("🚀 Инициализация Telegram Bot...")

    # Получаем токен
    token = os.getenv('TELEGRAM_BOT_TOKEN')

    if not token:
        logger.error("❌ Токен бота не установлен!")
        return

    # Устанавливаем в конфиг
    Config.TELEGRAM_TOKEN = token

    try:
        bot = TelegramBot(token)
        bot.run()
    except Exception as e:
        logger.error(f"💥 Необработанная ошибка: {e}")

if __name__ == '__main__':
    main()