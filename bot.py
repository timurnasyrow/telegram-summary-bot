import os
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import requests
from dotenv import load_dotenv
import openai

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
        # api_key = os.getenv("DEEPSEEK_API_KEY")
        client = openai.Client(base_url="http://zeliboba.yandex-team.ru/balance/deepseek_r1/v1", api_key="EMPTY")
        
        custom_headers = {
        'X-Model-Discovery-Oauth-Token': api_key,
        'X-Model-Discovery-Enable-Client-Ping': '0'
        }
        prompt = f'''
        Представь, что ты персональный ассистент. У твоего руководителя очень мало свободного времени и нет возможности читать все рабочие чаты. 
        При этом он хочет быть в контексте всего происходящего.
        Составь краткую выжимку из непрочитанных сообщений в рабочем чате. 
        Нужно узнать основную суть обсуждений, кто и с кем взаимодействовал, о чем шла речь, какие решения были приняты 
        или какие договоренности достигнуты, и любую другую важную информацию. Опиши события кратко и понятно, акцентируя внимание на ключевых деталях
        Представь ответ в виде
        Вот, что обсуждалось:
        - Ключевые темы:
        - Проблемы
        - Договоренности
        - Ключевые детали
        :\n\n{text}
        '''
        response = client.chat.completions.create(
            model="deepseek",
            messages=[{
                "role": "user", 
                "content": prompt
                },
            ],
        response_format={
            'type': 'json_object'
            },
        temperature=0,
        max_tokens=4096,
        extra_headers=custom_headers
        )
        return response['choices'][0]['message']['content']

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
