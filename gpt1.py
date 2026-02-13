import logging
import asyncio
import os
import sys
from typing import Optional, Dict, List
from datetime import datetime
from collections import deque

# Telegram библиотеки
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# OpenAI библиотека
import openai
from openai import AsyncOpenAI

# Flask для веб-сервера (для хостинга)
from flask import Flask, jsonify
import threading

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Создаем Flask приложение для веб-сервера
app = Flask(__name__)

# ВАШИ ТОКЕНЫ (вставлены)
TELEGRAM_TOKEN = "7640794685:AAHWcNmnqrRJw2lqVSymXp3pXym2vndql6g"
OPENAI_API_KEY = "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"

class OpenAITelegramBot:
    def __init__(self):
        """
        Инициализация бота с OpenAI
        """
        self.telegram_token = TELEGRAM_TOKEN
        self.openai_api_key = OPENAI_API_KEY
        
        self.openai_client = AsyncOpenAI(api_key=self.openai_api_key)
        
        # Хранилище истории диалогов для каждого пользователя
        self.user_conversations: Dict[int, deque] = {}
        
        # Максимальная длина истории
        self.max_history_length = 20
        
        # Настройки пользователей
        self.user_settings: Dict[int, dict] = {}
        
        # Доступные модели OpenAI
        self.available_models = {
            "gpt-4": "GPT-4 (самая мощная)",
            "gpt-4-turbo-preview": "GPT-4 Turbo (быстрее)",
            "gpt-3.5-turbo": "GPT-3.5 Turbo (быстрый и дешевый)"
        }
        
        self.application = None
        logger.info("Бот инициализирован")
    
    def get_user_history(self, user_id: int) -> List[dict]:
        """Получение истории диалога пользователя"""
        if user_id not in self.user_conversations:
            self.user_conversations[user_id] = deque(maxlen=self.max_history_length)
        
        messages = []
        for msg in self.user_conversations[user_id]:
            messages.append({"role": msg["role"], "content": msg["content"]})
        
        return messages
    
    def add_to_history(self, user_id: int, role: str, content: str):
        """Добавление сообщения в историю"""
        if user_id not in self.user_conversations:
            self.user_conversations[user_id] = deque(maxlen=self.max_history_length)
        
        self.user_conversations[user_id].append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        })
    
    def get_user_settings(self, user_id: int) -> dict:
        """Получение настроек пользователя"""
        if user_id not in self.user_settings:
            self.user_settings[user_id] = {
                "model": "gpt-3.5-turbo",
                "temperature": 0.7,
                "max_tokens": 1000,
                "system_prompt": "Ты полезный ассистент. Отвечай дружелюбно и информативно на русском языке."
            }
        return self.user_settings[user_id]
    
    async def generate_openai_response(self, user_id: int, user_message: str) -> Optional[str]:
        """
        Генерация ответа через OpenAI API
        """
        try:
            settings = self.get_user_settings(user_id)
            history = self.get_user_history(user_id)
            
            messages = [
                {"role": "system", "content": settings["system_prompt"]}
            ]
            
            # Добавляем историю
            messages.extend(history[-10:])
            messages.append({"role": "user", "content": user_message})
            
            # Отправляем запрос к OpenAI
            response = await self.openai_client.chat.completions.create(
                model=settings["model"],
                messages=messages,
                temperature=settings["temperature"],
                max_tokens=settings["max_tokens"],
                top_p=0.95,
                frequency_penalty=0.3,
                presence_penalty=0.3
            )
            
            bot_response = response.choices[0].message.content
            
            # Сохраняем в историю
            self.add_to_history(user_id, "user", user_message)
            self.add_to_history(user_id, "assistant", bot_response)
            
            return bot_response
            
        except openai.RateLimitError:
            logger.error("Rate limit exceeded")
            return "⚠️ Превышен лимит запросов к API. Пожалуйста, подождите немного."
        except openai.APIError as e:
            logger.error(f"OpenAI API error: {e}")
            return "⚠️ Ошибка при обращении к OpenAI. Попробуйте позже."
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return "⚠️ Произошла непредвиденная ошибка."
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start"""
        welcome_message = (
            "🤖 **Добро пожаловать в AI-бота на базе OpenAI!**\n\n"
            "Я использую технологии ChatGPT для общения.\n\n"
            "📝 **Команды:**\n"
            "/help - помощь\n"
            "/settings - настройки\n"
            "/clear - очистить историю\n"
            "/model - сменить модель\n"
            "/stats - статистика\n\n"
            "Просто напиши мне сообщение!"
        )
        
        keyboard = [
            [InlineKeyboardButton("🔧 Настройки", callback_data="settings"),
             InlineKeyboardButton("📊 Статистика", callback_data="stats")],
            [InlineKeyboardButton("🔄 Сменить модель", callback_data="change_model"),
             InlineKeyboardButton("🧹 Очистить историю", callback_data="clear")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            welcome_message,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /help"""
        help_text = (
            "🔍 **Подробная справка**\n\n"
            "/settings - настройка параметров\n"
            "/model - выбор модели GPT\n"
            "/clear - очистка истории\n"
            "/stats - просмотр статистики\n\n"
            "**Параметры:**\n"
            "• Температура: креативность ответов\n"
            "• Max tokens: длина ответа\n"
            "• System prompt: поведение бота"
        )
        await update.message.reply_text(help_text, parse_mode='Markdown')
    
    async def settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Настройки пользователя"""
        user_id = update.effective_user.id
        settings = self.get_user_settings(user_id)
        
        text = (
            f"⚙️ **Текущие настройки**\n\n"
            f"**Модель:** {settings['model']}\n"
            f"**Температура:** {settings['temperature']}\n"
            f"**Max tokens:** {settings['max_tokens']}\n"
            f"**System prompt:** {settings['system_prompt'][:50]}...\n\n"
            "Изменить:\n"
            "/temp [0.1-2.0]\n"
            "/maxtokens [100-4000]"
        )
        await update.message.reply_text(text, parse_mode='Markdown')
    
    async def change_model(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Смена модели"""
        keyboard = []
        for model_id, description in self.available_models.items():
            keyboard.append([InlineKeyboardButton(
                f"{model_id}", 
                callback_data=f"model_{model_id}"
            )])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "Выберите модель:",
            reply_markup=reply_markup
        )
    
    async def set_temperature(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Установка температуры"""
        try:
            temp = float(context.args[0])
            if 0.1 <= temp <= 2.0:
                user_id = update.effective_user.id
                self.user_settings[user_id]["temperature"] = temp
                await update.message.reply_text(f"✅ Температура: {temp}")
            else:
                await update.message.reply_text("❌ Температура от 0.1 до 2.0")
        except:
            await update.message.reply_text("Использование: /temp [0.1-2.0]")
    
    async def clear_history(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Очистка истории"""
        user_id = update.effective_user.id
        if user_id in self.user_conversations:
            self.user_conversations[user_id].clear()
        await update.message.reply_text("🧹 История очищена!")
    
    async def show_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Статистика"""
        user_id = update.effective_user.id
        history = self.get_user_history(user_id)
        
        text = (
            f"📊 **Статистика**\n\n"
            f"**Сообщений:** {len(history)}\n"
            f"**Модель:** {self.get_user_settings(user_id)['model']}"
        )
        await update.message.reply_text(text, parse_mode='Markdown')
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик сообщений"""
        user_id = update.effective_user.id
        user_message = update.message.text
        
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id, 
            action="typing"
        )
        
        try:
            response = await self.generate_openai_response(user_id, user_message)
            
            if response:
                if len(response) > 4096:
                    for i in range(0, len(response), 4096):
                        await update.message.reply_text(response[i:i+4096])
                else:
                    await update.message.reply_text(response)
            else:
                await update.message.reply_text("❌ Ошибка получения ответа")
                
        except Exception as e:
            logger.error(f"Error: {e}")
            await update.message.reply_text("❌ Ошибка. Попробуйте еще раз.")
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик кнопок"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "settings":
            await self.settings(update, context)
        elif query.data == "stats":
            await self.show_stats(update, context)
        elif query.data == "clear":
            user_id = update.effective_user.id
            if user_id in self.user_conversations:
                self.user_conversations[user_id].clear()
            await query.edit_message_text("🧹 История очищена!")
        elif query.data == "change_model":
            await self.change_model(update, context)
        elif query.data.startswith("model_"):
            model = query.data.replace("model_", "")
            user_id = update.effective_user.id
            self.user_settings[user_id]["model"] = model
            await query.edit_message_text(f"✅ Модель: {model}")
    
    async def setup_application(self):
        """Настройка приложения"""
        self.application = Application.builder().token(self.telegram_token).build()
        
        # Регистрация обработчиков
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("settings", self.settings))
        self.application.add_handler(CommandHandler("model", self.change_model))
        self.application.add_handler(CommandHandler("temp", self.set_temperature))
        self.application.add_handler(CommandHandler("clear", self.clear_history))
        self.application.add_handler(CommandHandler("stats", self.show_stats))
        
        self.application.add_handler(CallbackQueryHandler(self.button_callback))
        
        self.application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND, 
            self.handle_message
        ))
        
        logger.info("Обработчики зарегистрированы")
    
    async def run_bot(self):
        """Запуск бота"""
        await self.setup_application()
        
        logger.info("Бот запускается...")
        
        try:
            await self.application.initialize()
            await self.application.start()
            
            # Используем polling
            await self.application.updater.start_polling()
            
            logger.info("Бот успешно запущен и готов к работе!")
            
            # Держим бота запущенным
            while True:
                await asyncio.sleep(1)
                
        except Exception as e:
            logger.error(f"Ошибка при запуске бота: {e}")
        finally:
            await self.application.stop()

# Создаем глобальный экземпляр бота
telegram_bot = OpenAITelegramBot()

@app.route('/')
def home():
    """Проверка работы бота"""
    return jsonify({
        "status": "running",
        "message": "Telegram OpenAI Bot is running!",
        "timestamp": datetime.now().isoformat()
    })

@app.route('/health')
def health():
    """Проверка здоровья"""
    return jsonify({"status": "healthy"})

def run_flask():
    """Запуск Flask сервера"""
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

def run_bot():
    """Запуск бота в отдельном потоке"""
    asyncio.run(telegram_bot.run_bot())

if __name__ == "__main__":
    # Запускаем бота в отдельном потоке
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    # Запускаем Flask сервер
    run_flask()
