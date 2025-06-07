import os
import json
import datetime
import asyncio
import random
import logging
from typing import Optional, List, Dict
from openai import OpenAI
from dotenv import load_dotenv
from pyrogram import Client, filters, idle

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ch = logging.StreamHandler()
ch.setFormatter(formatter)
logger.addHandler(ch)

# Load environment variables
load_dotenv()
TELEGRAM_API_ID = os.getenv("TELEGRAM_API_ID")
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
HISTORY_DIR = "history"

# Validate env vars
if not (TELEGRAM_API_ID and TELEGRAM_API_HASH and OPENAI_API_KEY):
    logger.error("Missing TELEGRAM_API_ID, TELEGRAM_API_HASH or OPENAI_API_KEY in .env")
    exit(1)
try:
    TELEGRAM_API_ID = int(TELEGRAM_API_ID)
except ValueError:
    logger.error("TELEGRAM_API_ID must be an integer")
    exit(1)

class AIConversationManager:
    """
    Asynchroniczny manager historii rozmowy AI, oparty na ai.py
    """
    def __init__(
        self,
        api_key: str,
        chat_id: int,
        history_dir: str = HISTORY_DIR,
        model: str = "gpt-4o-mini",
        system_prompt: Optional[str] = None,
        system_prompt_file: Optional[str] = None
    ):
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.chat_id = chat_id
        self.history_dir = history_dir
        os.makedirs(self.history_dir, exist_ok=True)
        self.history_file = os.path.join(self.history_dir, f"chat_{self.chat_id}_history.json")

        default_prompt = "Jesteś pomocnym asystentem AI."
        if system_prompt:
            self.system_prompt = system_prompt
        elif system_prompt_file and os.path.exists(system_prompt_file):
            with open(system_prompt_file, 'r', encoding='utf-8') as f:
                self.system_prompt = f.read().strip()
        else:
            self.system_prompt = default_prompt

        self.messages: List[Dict[str, str]] = []
        self._load_history()

    def _load_history(self) -> None:
        if os.path.exists(self.history_file):
            with open(self.history_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.model = data.get("model", self.model)
                file_prompt = data.get("system_prompt", self.system_prompt)
                self.system_prompt = self.system_prompt or file_prompt
                self.messages = data.get("messages", [])
        if self.messages and self.messages[0].get("role") == "system":
            self.messages[0]["content"] = self.system_prompt
        else:
            self.messages.insert(0, {"role": "system", "content": self.system_prompt})

    def _save_history(self) -> None:
        payload = {
            "timestamp": datetime.datetime.now().isoformat(),
            "model": self.model,
            "system_prompt": self.system_prompt,
            "messages": self.messages
        }
        with open(self.history_file, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    def add_user_message(self, content: str) -> None:
        self.messages.append({"role": "user", "content": content})

    def add_ai_message(self, content: str) -> None:
        self.messages.append({"role": "assistant", "content": content})

    async def get_response(self, user_message: Optional[str] = None, save_history: bool = True) -> str:
        """
        Asynchroniczne pobranie odpowiedzi od OpenAI, wykonane w wątku roboczym
        """
        if user_message:
            self.add_user_message(user_message)
        # run blocking create() in thread to avoid blocking event loop
        response = await asyncio.to_thread(
            self.client.chat.completions.create,
            model=self.model,
            messages=self.messages
        )
        ai_content = response.choices[0].message.content
        if save_history:
            self.add_ai_message(ai_content)
            self._save_history()
        else:
            if user_message:
                self.messages.pop()
        return ai_content

async def simulate_typing(chat_id: int, text: str, client: Client, wpm: int = 100000, sigma: float = 0.3, min_delay: float = 0, max_delay: float = 3.0) -> None:
    """
    Asynchroniczne symulowanie wpisywania (opóźnienia słowne)
    """
    avg = 60.0 / wpm
    end_delay = 0
    for word in text.split():
        if len(word) < 2:
            continue
        delay = random.gauss(avg, sigma)
        delay = max(min_delay, min(max_delay, delay))
        end_delay += delay
    logger.info(f"Simulating typing delay for chat {chat_id}: {end_delay:.2f} seconds")
    await asyncio.sleep(end_delay)

# Inicjalizacja klienta Pyrogram w trybie asynchronicznym
app = Client(
    "my_account_session",
    api_id=TELEGRAM_API_ID,
    api_hash=TELEGRAM_API_HASH
)

async def process_existing_chats(client: Client, max_messages: int = 50, max_days_back: int = 14):
    """
    Przejdź przez istniejące czaty i odpowiedz na nieodpowiedziane wiadomości
    """
    logger.info("Processing existing chats...")
    
    # Ustaw limit czasu dla wiadomości (nie odpowiadaj na zbyt stare)
    time_threshold = datetime.datetime.now() - datetime.timedelta(days=max_days_back)
    
    # Pobierz wszystkie dialogi (czaty)
    async for dialog in client.get_dialogs():
        if not dialog.chat.type.name == "PRIVATE" or dialog.chat.id == 777000:
            continue
        
        chat_id = dialog.chat.id
        logger.info(f"Checking chat with {dialog.chat.first_name} (ID: {chat_id})")
        
        # Pobierz ostatnie wiadomości
        messages = []
        async for message in client.get_chat_history(chat_id, limit=max_messages):
            # Pomiń wiadomości wychodzące (wysłane przez nas)
            if message.outgoing:
                break  # Zatrzymaj pobieranie - znaleziono naszą odpowiedź
            
            # Pomiń wiadomości bez tekstu
            if not (message.text or message.caption):
                continue
                
            # Pomiń zbyt stare wiadomości
            if message.date and message.date < time_threshold:
                continue
                
            messages.append(message)
            
        # Odwróć kolejność wiadomości (od najstarszej do najnowszej)
        messages.reverse()
        
        # Odpowiedz na nieodpowiedziane wiadomości
        if messages:
            # Inicjalizuj manager konwersacji jeśli nie istnieje
            if chat_id not in conversations:
                conversations[chat_id] = AIConversationManager(
                    api_key=OPENAI_API_KEY,
                    chat_id=chat_id,
                    history_dir=HISTORY_DIR,
                    system_prompt_file="system_prompts/telegram_troll.txt"
                )
            
            cm = conversations[chat_id]
            
            for message in messages:
                content = message.text or message.caption or ""
                if not content:
                    continue
                    
                short_content = content
                if len(content) > 40:
                    short_content = content[:20] + " ... " + content[-20:]
                logger.info(f"Processing existing message in chat {chat_id}: {short_content}")
                
                response = await cm.get_response(content)
                await simulate_typing(chat_id, response, client)
                await client.send_message(chat_id, response)
                
                # Odczekaj chwilę między wiadomościami aby nie przekroczyć limitów API
                await asyncio.sleep(1)
                
        else:
            logger.info(f"No unprocessed messages in chat {chat_id}")

conversations: Dict[int, AIConversationManager] = {}

# Handler: treat incoming private messages or outgoing prefixed with "user:" as user input
@app.on_message(
    (filters.private & ~filters.outgoing)
    | (filters.private & filters.outgoing & filters.regex(r'(?i)^user:'))
)
async def handle_message(client: Client, message):
    raw = message.text or message.caption or ""
    if message.outgoing and raw.lower().startswith("user:"):
        content = raw[len("user:"):].strip()
    elif not message.outgoing:
        content = raw
    else:
        return
    if not content:
        return
    chat_id = message.chat.id
    if chat_id not in conversations:
        conversations[chat_id] = AIConversationManager(
            api_key=OPENAI_API_KEY,
            chat_id=chat_id,
            history_dir=HISTORY_DIR,
            system_prompt_file="system_prompts/telegram_troll.txt"
        )
    cm = conversations[chat_id]
    short_content = content
    if len(content) > 40:
        short_content = content[:20] + " ... " + content[-20:]
    logger.info(f"Received message in chat {chat_id}: {short_content}")
    response = await cm.get_response(content)
    await simulate_typing(chat_id, response, client)
    await client.send_message(chat_id, response)

if __name__ == "__main__":
    logger.info("Starting Telegram Async Manager...")
    
    # Uruchom klienta
    app.start()
    
    # Przetwarzaj istniejące czaty
    asyncio.get_event_loop().run_until_complete(process_existing_chats(app))
    
    # Kontynuuj nasłuchiwanie na nowe wiadomości
    idle()
    
    # Na końcu zatrzymaj klienta
    app.stop()
