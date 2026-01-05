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

        self.stats = {
            'start_time': datetime.now(),
            'total_commands': 0,
            'active_users': 0,
        }

    def get_status(self) -> str:
        """Получить статус системы"""
        lines = [
            "🖥️ *СТАТУС СИСТЕМЫ*",
            f"Время: {datetime.now().strftime('%H:%M:%S')}",
            f"Активна: {(datetime.now() - self.stats['start_time']).seconds // 60} мин",
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
        """Генерировать токен входа (простой пример, в реальности используйте UUID или secure random)"""
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

    async def handle_login(self, update: Update, context: CallbackContext):
        """Обработчик /login"""
        chat_id = update.effective_chat.id
        user_data = self.get_user_data(chat_id)
        args = context.args
        login_type = args[0] if args else None

        self.monitor.stats['total_commands'] += 1

        if user_data and user_data.get('status') == UserStatus.AUTHORIZED:
            await update.message.reply_text("Вы уже авторизованы.")
            return

        if not login_type or login_type not in ['github', 'yandex', 'code']:
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
            return

        # Генерируем токен входа
        login_token = self.generate_login_token()

        # Сохраняем в Redis как анонимный
        self.set_user_data(chat_id, {
            'status': UserStatus.ANONYMOUS,
            'login_token': login_token,
            'login_time': datetime.now().isoformat()
        })

        # Запрос к Auth API (предполагаем endpoint /login с type и token)
        auth_url = f"{Config.AUTH_API_URL}/login?type={login_type}&token={login_token}"
        try:
            response = requests.get(auth_url)
            if response.status_code == 200:
                auth_response = response.json()
                # Предполагаем, что Auth возвращает URL для redirect или сообщение
                await update.message.reply_text(
                    f"Перейдите по ссылке для авторизации: {auth_response.get('auth_url', 'URL not provided')}"
                )
            else:
                await update.message.reply_text("Ошибка при запросе авторизации.")
        except Exception as e:
            logger.error(f"Error in login: {e}")
            await update.message.reply_text("Внутренняя ошибка.")

    async def handle_logout(self, update: Update, context: CallbackContext):
        """Обработчик /logout"""
        chat_id = update.effective_chat.id
        user_data = self.get_user_data(chat_id)
        args = context.args
        all_devices = 'all=true' in ' '.join(args).lower()

        self.monitor.stats['total_commands'] += 1

        if not user_data or user_data.get('status') != UserStatus.AUTHORIZED:
            await update.message.reply_text("Вы не авторизованы.")
            return

        # Удаляем из Redis
        self.delete_user_data(chat_id)

        if all_devices:
            # Запрос к Auth на logout all с refresh_token
            try:
                response = requests.post(
                    f"{Config.AUTH_API_URL}/logout",
                    headers={'Authorization': f"Bearer {user_data['refresh_token']}"}
                )
                if response.status_code == 200:
                    await update.message.reply_text("Сеанс завершен на всех устройствах.")
                else:
                    await update.message.reply_text("Ошибка при logout на всех устройствах.")
            except Exception as e:
                logger.error(f"Error in logout all: {e}")
                await update.message.reply_text("Внутренняя ошибка.")
        else:
            await update.message.reply_text("Сеанс завершен.")

    async def check_auth_status(self, chat_id: int) -> Optional[Dict[str, str]]:
        """Проверить статус авторизации через Auth API"""
        user_data = self.get_user_data(chat_id)
        if not user_data or user_data.get('status') != UserStatus.ANONYMOUS:
            return None

        login_token = user_data.get('login_token')

        try:
            response = requests.get(f"{Config.AUTH_API_URL}/check_login?token={login_token}")
            if response.status_code == 200:
                auth_data = response.json()
                status = auth_data.get('status')

                if status == 'denied':
                    self.delete_user_data(chat_id)
                    return {'message': 'Неудачная авторизация.'}
                elif status == 'granted':
                    access_token = auth_data.get('access_token')
                    refresh_token = auth_data.get('refresh_token')
                    if access_token and refresh_token:
                        self.set_user_data(chat_id, {
                            'status': UserStatus.AUTHORIZED,
                            'access_token': access_token,
                            'refresh_token': refresh_token
                        })
                        return {'message': 'Успешная авторизация!'}
                    else:
                        return {'message': 'Ошибка: токены не получены.'}
                elif status == 'expired' or status == 'invalid':
                    self.delete_user_data(chat_id)
                    return None
        except Exception as e:
            logger.error(f"Error checking auth: {e}")

        return None

    async def refresh_tokens(self, chat_id: int) -> bool:
        """Обновить токены через refresh_token"""
        user_data = self.get_user_data(chat_id)
        if not user_data or 'refresh_token' not in user_data:
            return False

        try:
            response = requests.post(
                f"{Config.AUTH_API_URL}/refresh",
                headers={'Authorization': f"Bearer {user_data['refresh_token']}"}
            )
            if response.status_code == 200:
                new_tokens = response.json()
                user_data['access_token'] = new_tokens.get('access_token')
                user_data['refresh_token'] = new_tokens.get('refresh_token')
                self.set_user_data(chat_id, user_data)
                return True
            else:
                self.delete_user_data(chat_id)
                return False
        except Exception as e:
            logger.error(f"Error refreshing tokens: {e}")
            return False

    async def handle_authorized_command(self, update: Update, context: CallbackContext, endpoint: str):
        """Обработчик авторизованных команд (пример для /test)"""
        chat_id = update.effective_chat.id
        user_data = self.get_user_data(chat_id)

        if not user_data or user_data.get('status') != UserStatus.AUTHORIZED:
            await update.message.reply_text("Пожалуйста, авторизуйтесь с помощью /login.")
            return

        # Запрос к Core API
        try:
            response = requests.get(
                f"{Config.CORE_API_URL}/{endpoint}",
                headers={'Authorization': f"Bearer {user_data['access_token']}"}
            )
            if response.status_code == 200:
                data = response.json()
                await update.message.reply_text(f"Ответ от Core: {json.dumps(data)}")
            elif response.status_code == 401:
                # Пробуем refresh
                if await self.refresh_tokens(chat_id):
                    # Рекурсивно повторяем
                    await self.handle_authorized_command(update, context, endpoint)
                else:
                    await update.message.reply_text("Сессия истекла. Пожалуйста, авторизуйтесь заново.")
            elif response.status_code == 403:
                await update.message.reply_text("Недостаточно прав для этого действия.")
            else:
                await update.message.reply_text("Ошибка при запросе к Core API.")
        except Exception as e:
            logger.error(f"Error in authorized command: {e}")
            await update.message.reply_text("Внутренняя ошибка.")

    async def on_start(self, update: Update, context: CallbackContext):
        """Обработчик /start"""
        user = update.effective_user
        chat_id = update.effective_chat.id
        user_data = self.get_user_data(chat_id)
        self.monitor.stats['total_commands'] += 1

        if not user_data:
            # Неизвестный пользователь
            welcome_msg = f"""👋 Привет, {user.first_name}!

🤖 Я - бот системы тестирования.
Система находится в стадии активной разработки.

📊 *Что уже работает:*
• Контейнеры Docker подняты
• Базы данных запущены  
• Веб-интерфейс доступен
• API сервисы готовы

🔧 *Что будет добавлено:*
• Авторизация через OAuth
• Создание и прохождение тестов
• Личный кабинет
• Уведомления

Пожалуйста, авторизуйтесь с помощью /login."""
        elif user_data['status'] == UserStatus.ANONYMOUS:
            welcome_msg = "Вы в статусе анонимного пользователя. Завершите авторизацию."
        else:
            welcome_msg = f"Добро пожаловать обратно, {user.first_name}! Вы авторизованы."

        keyboard = [
            [{'text': '📊 Статус', 'callback_data': 'status'}],
            [{'text': '🔧 Сервисы', 'callback_data': 'services'}],
            [{'text': '🆘 Помощь', 'callback_data': 'help'}],
        ]
        if user_data and user_data['status'] == UserStatus.AUTHORIZED:
            keyboard.append([{'text': '🚪 Logout', 'callback_data': 'logout'}])

        await update.message.reply_text(
            welcome_msg,
            parse_mode='Markdown',
            reply_markup={'inline_keyboard': keyboard}
        )

    async def on_status(self, update: Update, context: CallbackContext):
        """Обработчик /status"""
        self.monitor.stats['total_commands'] += 1
        await update.message.reply_text(
            self.monitor.get_status(),
            parse_mode='Markdown'
        )

    async def on_services(self, update: Update, context: CallbackContext):
        """Обработчик /services"""
        self.monitor.stats['total_commands'] += 1
        await update.message.reply_text(
            self.monitor.get_services(),
            parse_mode='Markdown'
        )

    async def on_help(self, update: Update, context: CallbackContext):
        """Обработчик /help"""
        self.monitor.stats['total_commands'] += 1
        await update.message.reply_text(
            self.monitor.get_help(),
            parse_mode='Markdown'
        )

    async def on_test(self, update: Update, context: CallbackContext):
        """Пример авторизованной команды /test"""
        await self.handle_authorized_command(update, context, "test")  # Замените на реальный endpoint

    async def on_callback(self, update: Update, context: CallbackContext):
        """Обработчик callback-запросов"""
        query = update.callback_query
        await query.answer()

        if query.data == 'status':
            await query.edit_message_text(
                text=self.monitor.get_status(),
                parse_mode='Markdown'
            )
        elif query.data == 'services':
            await query.edit_message_text(
                text=self.monitor.get_services(),
                parse_mode='Markdown'
            )
        elif query.data == 'help':
            await query.edit_message_text(
                text=self.monitor.get_help(),
                parse_mode='Markdown'
            )
        elif query.data.startswith('login_'):
            login_type = query.data.split('_')[1]
            # Симулируем /login с типом
            temp_context = CallbackContext.from_update(update, self.application)
            temp_context.args = [login_type]
            await self.handle_login(update, temp_context)
            await query.edit_message_text("Инициирована авторизация.")
        elif query.data == 'logout':
            temp_context = CallbackContext.from_update(update, self.application)
            await self.handle_logout(update, temp_context)
            await query.edit_message_text("Сеанс завершен.")

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