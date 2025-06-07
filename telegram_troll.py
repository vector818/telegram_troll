import os
import json
import datetime
import asyncio
import random
import logging
import time
from collections import defaultdict
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
pending_responses = {}
message_queue = defaultdict(list)

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
            is_forwarded = message.forward_from is not None
            is_forwarded_self = message.forward_from.is_self if is_forwarded else False
            # Pomiń wiadomości wychodzące (wysłane przez nas)
            if message.outgoing:
                break  # Zatrzymaj pobieranie - znaleziono naszą odpowiedź
            
            # Pomiń wiadomości bez tekstu
            if not (message.text or message.caption):
                continue
                
            # Pomiń zbyt stare wiadomości
            if message.date and message.date < time_threshold:
                continue

            #Pomiń wiadomości nasze wiadomości wysłane jako forwarded
            if is_forwarded_self:
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
            
            # Zbierz zawartość wszystkich wiadomości
            message_contents = []
            for message in messages:
                content = message.text or message.caption or ""
                if content:
                    message_contents.append(content)
            
            if len(message_contents) == 1:
                # Jeśli jest tylko jedna wiadomość, odpowiedz bezpośrednio
                content = message_contents[0]
                short_content = content[:20] + " ... " + content[-20:] if len(content) > 40 else content
                logger.info(f"Processing single message in chat {chat_id}: {short_content}")
                response = await cm.get_response(content)
            else:
                # Jeśli jest wiele wiadomości, połącz je dla kontekstu
                combined = "\n".join([f"[Message {i+1}]: {m}" for i, m in enumerate(message_contents)])
                logger.info(f"Processing {len(message_contents)} accumulated messages in chat {chat_id}")
                response = await cm.get_response(combined)
            
            # Symuluj pisanie i wyślij odpowiedź
            await simulate_typing(chat_id, response, client)
            await client.send_message(chat_id, response)
        else:
            logger.info(f"No unprocessed messages in chat {chat_id}")
    
async def delayed_response(client: Client, chat_id: int, delay: float):
    """
    Wait for the specified delay, then respond to all accumulated messages
    """
    try:
        # Wait for the specified delay
        await asyncio.sleep(delay)
        
        # Check if we have any messages to respond to
        if not message_queue[chat_id]:
            logger.info(f"No messages left to respond to in chat {chat_id}")
            return
            
        # Initialize conversation manager if needed
        if chat_id not in conversations:
            conversations[chat_id] = AIConversationManager(
                api_key=OPENAI_API_KEY,
                chat_id=chat_id,
                history_dir=HISTORY_DIR,
                system_prompt_file="system_prompts/telegram_troll.txt"
            )
        cm = conversations[chat_id]
        
        # Get all messages since our last response
        messages = message_queue[chat_id]
        message_queue[chat_id] = []  # Clear the queue
        
        if len(messages) == 1:
            # If there's only one message, just respond to it directly
            content = messages[0]['content']
            response = await cm.get_response(content)
        else:
            # If there are multiple messages, combine them for context
            combined = "\n".join([f"[Message {i+1}]: {m['content']}" for i, m in enumerate(messages)])
            logger.info(f"Responding to {len(messages)} accumulated messages in chat {chat_id}")
            
            # Get a response considering all messages
            response = await cm.get_response(combined)
        
        # Simulate typing and send response
        await simulate_typing(chat_id, response, client)
        await client.send_message(chat_id, response)
        
    except Exception as e:
        logger.error(f"Error in delayed_response for chat {chat_id}: {str(e)}")

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
    short_content = content[:20] + " ... " + content[-20:] if len(content) > 40 else content
    logger.info(f"Received message in chat {chat_id}: {short_content}")
    
    # Add message to queue
    message_queue[chat_id].append({
        'content': content,
        'time': time.time(),
        'message_id': message.id
    })
    
    # If there's no pending response for this chat, schedule one
    if chat_id not in pending_responses:
        # Calculate random delay (mean: 5 minutes, std dev: 3 minutes)
        delay = random.gauss(300, 180)  # 300 seconds = 5 minutes
        delay = max(30, min(900, delay))  # Clamp between 30 seconds and 15 minutes
        #delay = 0  # For testing, set to 0 for immediate response

        logger.info(f"Scheduling response for chat {chat_id} in {delay:.1f} seconds")
        
        # Create and store the task
        task = asyncio.create_task(delayed_response(client, chat_id, delay))
        pending_responses[chat_id] = task
        
        # Cleanup when done
        task.add_done_callback(lambda t: pending_responses.pop(chat_id, None))

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
