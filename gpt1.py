import logging
import asyncio
from typing import Optional, Dict, List
from datetime import datetime
import os

# Telegram библиотеки
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# OpenAI библиотека
import openai
from openai import AsyncOpenAI

# Для работы с историей сообщений
import json
from collections import deque

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class OpenAITelegramBot:
    def __init__(self, telegram_token: str, openai_api_key: str):
        """
        Инициализация бота с OpenAI
        """
        self.telegram_token = telegram_token
        self.openai_client = AsyncOpenAI(api_key=openai_api_key)
        
        # Хранилище истории диалогов для каждого пользователя
        self.user_conversations: Dict[int, deque] = {}
        
        # Максимальная длина истории (количество сообщений)
        self.max_history_length = 20
        
        # Настройки пользователей
        self.user_settings: Dict[int, dict] = {}
        
        # Доступные модели OpenAI
        self.available_models = {
            "gpt-4": "GPT-4 (самая мощная)",
            "gpt-4-turbo-preview": "GPT-4 Turbo (быстрее)",
            "gpt-3.5-turbo": "GPT-3.5 Turbo (быстрый и дешевый)"
        }
        
    def get_user_history(self, user_id: int) -> List[dict]:
        """Получение истории диалога пользователя"""
        if user_id not in self.user_conversations:
            self.user_conversations[user_id] = deque(maxlen=self.max_history_length)
        
        # Преобразуем deque в список сообщений для API
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
                "system_prompt": "Ты полезный ассистент. Отвечай дружелюбно и информативно."
            }
        return self.user_settings[user_id]
    
    async def generate_openai_response(self, user_id: int, user_message: str) -> Optional[str]:
        """
        Генерация ответа через OpenAI API
        """
        try:
            settings = self.get_user_settings(user_id)
            
            # Получаем историю диалога
            history = self.get_user_history(user_id)
            
            # Формируем сообщения для API
            messages = [
                {"role": "system", "content": settings["system_prompt"]}
            ]
            
            # Добавляем историю диалога
            messages.extend(history[-10:])  # Последние 10 сообщений для контекста
            
            # Добавляем новое сообщение пользователя
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
            
            # Получаем ответ
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
    
    # Обработчики команд
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start"""
        welcome_message = (
            "🤖 **Добро пожаловать в AI-бота на базе OpenAI!**\n\n"
            "Я использую технологии ChatGPT для общения. Вот что я умею:\n\n"
            "📝 **Основные возможности:**\n"
            "• Отвечать на любые вопросы\n"
            "• Помогать с написанием кода\n"
            "• Переводить тексты\n"
            "• Объяснять сложные темы\n"
            "• Поддерживать контекст разговора\n\n"
            "🔧 **Доступные команды:**\n"
            "/help - подробная помощь\n"
            "/settings - настройки модели\n"
            "/clear - очистить историю\n"
            "/model - сменить модель\n"
            "/stats - статистика использования\n"
            "/system - изменить системный промпт\n\n"
            "Просто напиши мне сообщение, и я отвечу!"
        )
        
        # Создаем клавиатуру
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
            "**Основные команды:**\n"
            "/settings - настройка параметров генерации\n"
            "/model - выбор модели GPT\n"
            "/system - изменение системного промпта\n"
            "/clear - очистка истории диалога\n"
            "/stats - просмотр статистики\n\n"
            
            "**Параметры настройки:**\n"
            "• **Модель**: выбор между GPT-3.5 и GPT-4\n"
            "• **Температура**: креативность ответов (0.1 - 2.0)\n"
            "• **Max tokens**: максимальная длина ответа\n"
            "• **System prompt**: инструкция для поведения бота\n\n"
            
            "**Советы по использованию:**\n"
            "• Бот помнит последние 20 сообщений диалога\n"
            "• Для сложных задач используйте GPT-4\n"
            "• Для быстрых ответов - GPT-3.5\n"
            "• Температура 0.7 оптимальна для большинства задач"
        )
        await update.message.reply_text(help_text, parse_mode='Markdown')
    
    async def settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Настройки пользователя"""
        user_id = update.effective_user.id
        settings = self.get_user_settings(user_id)
        
        settings_text = (
            f"⚙️ **Текущие настройки**\n\n"
            f"**Модель:** {settings['model']}\n"
            f"**Температура:** {settings['temperature']}\n"
            f"**Max tokens:** {settings['max_tokens']}\n"
            f"**System prompt:** {settings['system_prompt'][:50]}...\n\n"
            "Используйте команды для изменения:\n"
            "/temp [0.1-2.0] - изменить температуру\n"
            "/maxtokens [число] - изменить max tokens\n"
            "/model - выбрать модель"
        )
        
        await update.message.reply_text(settings_text, parse_mode='Markdown')
    
    async def change_model(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Смена модели"""
        keyboard = []
        for model_id, description in self.available_models.items():
            keyboard.append([InlineKeyboardButton(
                f"{model_id} - {description}", 
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
                await update.message.reply_text(f"✅ Температура установлена на {temp}")
            else:
                await update.message.reply_text("❌ Температура должна быть от 0.1 до 2.0")
        except (IndexError, ValueError):
            await update.message.reply_text("Использование: /temp [0.1-2.0]")
    
    async def set_max_tokens(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Установка максимального количества токенов"""
        try:
            tokens = int(context.args[0])
            if 100 <= tokens <= 4000:
                user_id = update.effective_user.id
                self.user_settings[user_id]["max_tokens"] = tokens
                await update.message.reply_text(f"✅ Max tokens установлен на {tokens}")
            else:
                await update.message.reply_text("❌ Max tokens должен быть от 100 до 4000")
        except (IndexError, ValueError):
            await update.message.reply_text("Использование: /maxtokens [100-4000]")
    
    async def set_system_prompt(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Установка системного промпта"""
        if context.args:
            prompt = ' '.join(context.args)
            user_id = update.effective_user.id
            self.user_settings[user_id]["system_prompt"] = prompt
            await update.message.reply_text(f"✅ System prompt обновлен!")
        else:
            await update.message.reply_text(
                "Использование: /system [ваш промпт]\n"
                "Например: /system Ты эксперт по Python программированию"
            )
    
    async def clear_history(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Очистка истории диалога"""
        user_id = update.effective_user.id
        if user_id in self.user_conversations:
            self.user_conversations[user_id].clear()
        await update.message.reply_text("🧹 История диалога очищена!")
    
    async def show_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показ статистики"""
        user_id = update.effective_user.id
        history = self.get_user_history(user_id)
        
        stats_text = (
            f"📊 **Статистика**\n\n"
            f"**Сообщений в истории:** {len(history)}\n"
            f"**Модель:** {self.get_user_settings(user_id)['model']}\n"
            f"**Температура:** {self.get_user_settings(user_id)['temperature']}\n\n"
            f"Использовано токенов: информация доступна в OpenAI Dashboard"
        )
        
        await update.message.reply_text(stats_text, parse_mode='Markdown')
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик текстовых сообщений"""
        user_id = update.effective_user.id
        user_message = update.message.text
        
        # Показываем индикатор "печатает"
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id, 
            action="typing"
        )
        
        try:
            # Генерируем ответ через OpenAI
            response = await self.generate_openai_response(user_id, user_message)
            
            if response:
                # Разбиваем длинные сообщения на части
                if len(response) > 4096:
                    for i in range(0, len(response), 4096):
                        await update.message.reply_text(response[i:i+4096])
                else:
                    await update.message.reply_text(response)
            else:
                await update.message.reply_text(
                    "❌ Не удалось получить ответ от OpenAI. Попробуйте позже."
                )
                
        except Exception as e:
            logger.error(f"Error handling message: {e}")
            await update.message.reply_text(
                "❌ Произошла ошибка. Пожалуйста, попробуйте еще раз."
            )
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик нажатий на кнопки"""
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
            await query.edit_message_text(f"✅ Модель изменена на {model}")
    
    def run(self):
        """Запуск бота"""
        try:
            # Создание приложения
            self.application = Application.builder().token(self.telegram_token).build()
            
            # Регистрация обработчиков команд
            self.application.add_handler(CommandHandler("start", self.start))
            self.application.add_handler(CommandHandler("help", self.help_command))
            self.application.add_handler(CommandHandler("settings", self.settings))
            self.application.add_handler(CommandHandler("model", self.change_model))
            self.application.add_handler(CommandHandler("temp", self.set_temperature))
            self.application.add_handler(CommandHandler("maxtokens", self.set_max_tokens))
            self.application.add_handler(CommandHandler("system", self.set_system_prompt))
            self.application.add_handler(CommandHandler("clear", self.clear_history))
            self.application.add_handler(CommandHandler("stats", self.show_stats))
            
            # Обработчик кнопок
            self.application.add_handler(CallbackQueryHandler(self.button_callback))
            
            # Обработчик текстовых сообщений
            self.application.add_handler(MessageHandler(
                filters.TEXT & ~filters.COMMAND, 
                self.handle_message
            ))
            
            logger.info("Бот запущен и готов к работе!")
            self.application.run_polling(allowed_updates=Update.ALL_TYPES)
            
        except Exception as e:
            logger.error(f"Ошибка запуска бота: {e}")

# Файл requirements.txt
requirements = """
python-telegram-bot==20.7
openai==1.6.1
"""

if __name__ == "__main__":
    # Токены (получите свои)
    TELEGRAM_TOKEN = "7640794685:AAHWcNmnqrRJw2lqVSymXp3pXym2vndql6g"
    OPENAI_API_KEY = "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"
    # Создание и запуск бота
    bot = OpenAITelegramBot(TELEGRAM_TOKEN, OPENAI_API_KEY)
    bot.run()