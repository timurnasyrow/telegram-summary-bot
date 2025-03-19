import os
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import requests
from dotenv import load_dotenv

load_dotenv()

# {chat_id: [messages]}
group_messages = {}
storage_lock = asyncio.Lock()

async def save_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сохраняем сообщения из группового чата"""
    if not update.message or not update.message.text:
        return
    
    chat_id = update.effective_chat.id
    text = f"{update.message.from_user.name}: {update.message.text}"
    
    async with storage_lock:
        if chat_id not in group_messages:
            group_messages[chat_id] = []
        group_messages[chat_id].append(text)

async def summarize(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка команды /summarize"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    async with storage_lock:
        if chat_id not in group_messages or not group_messages[chat_id]:
            await update.message.reply_text("ℹ️ Нет новых сообщений для обработки")
            return
        
        messages = group_messages.pop(chat_id)
        text_to_process = "\n".join(messages[:100])  # Лимит 100 сообщений
    
    try:
        summary = await get_deepseek_summary(text_to_process)
        
        # Пытаемся отправить в личные сообщения
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"📌 Сводка из чата {update.effective_chat.title}\n\n{summary}"
            )
            # Удаляем сообщение-команду в группе
            await update.message.delete()
        except Exception as e:
            await update.message.reply_text(f"❌ Не могу отправить сообщение. Начните диалог с ботом!")

    except Exception as e:
        async with storage_lock:
            group_messages[chat_id] = messages + group_messages.get(chat_id, [])
        
        await update.message.reply_text(f"⚠️ Ошибка обработки: {str(e)}")

async def get_deepseek_summary(text: str) -> str:
    """Запрос к DeepSeek API"""
    api_key = os.getenv("DEEPSEEK_API_KEY")
    url = "https://api.deepseek.com/v1/chat/completions"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    data = {
        "model": "deepseek-chat",
        "messages": [{
            "role": "user", 
            "content": f"Сделай структурированную выжимку на русском языке. Выдели основные темы и решения:\n\n{text}"
        }]
    }
    
    response = requests.post(url, json=data, headers=headers)
    response.raise_for_status()
    return response.json()['choices'][0]['message']['content']

def main():
    app = Application.builder().token(os.getenv("TELEGRAM_BOT_TOKEN")).build()
    
    # Для групповых чатов
    app.add_handler(MessageHandler(
        filters.ChatType.GROUPS & filters.TEXT & ~filters.COMMAND,
        save_group_message
    ))
    
    # Команда работает и в группах, и в личных сообщениях
    app.add_handler(CommandHandler("summarize", summarize))
    
    print("Bot started in group mode")
    app.run_polling()

if __name__ == "__main__":
    main()
