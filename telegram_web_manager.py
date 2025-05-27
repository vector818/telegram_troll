import os
import time
import logging
import random
from pathlib import Path
from dotenv import load_dotenv
from pyrogram import Client
from pyrogram.types import Dialog
from ai import AIConversationManager

# Configure logging
logger = logging.getLogger("telegram_manager")
logger.setLevel(logging.INFO)

# Create handlers
console_handler = logging.StreamHandler()
file_handler = logging.FileHandler("telegram.log")

# Set levels
console_handler.setLevel(logging.INFO)
file_handler.setLevel(logging.INFO)

# Create formatters
log_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(log_format)
file_handler.setFormatter(log_format)

# Add handlers to logger
logger.addHandler(console_handler)
logger.addHandler(file_handler)

# Wczytaj zmienne środowiskowe tylko raz
load_dotenv()

TELEGRAM_API_ID = os.getenv("TELEGRAM_API_ID")
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not TELEGRAM_API_ID or not TELEGRAM_API_HASH:
	raise RuntimeError("Ustaw TELEGRAM_API_ID i TELEGRAM_API_HASH w pliku .env")

try:
	TELEGRAM_API_ID = int(TELEGRAM_API_ID)
except ValueError:
	raise RuntimeError("TELEGRAM_API_ID musi być liczbą całkowitą")

# Inicjalizacja klienta Pyrogram
app = Client(
	"my_account_session",
	api_id=TELEGRAM_API_ID,
	api_hash=TELEGRAM_API_HASH
)

class Chat:
	"""
	Reprezentuje pojedynczy czat (dialog) i operacje na nim.
	"""
	def __init__(
		self,
		dialog: Dialog,
		client: Client,
		openai_api_key: str,
		history_dir: str = "history"
	):
		self.id = dialog.chat.id
		self.title = dialog.chat.title or dialog.chat.first_name or str(self.id)
		self.client = client
		# Każdy Chat tworzy własnego AIConversationManager z odpowiednim chat_id
		self.ai = AIConversationManager(
			api_key=openai_api_key,
			chat_id=self.id,
			history_dir=history_dir,
			system_prompt_file="system_prompts/telegram_troll.txt"
		)
		# Plik do przechowywania ostatniego zsynchronizowanego message_id
		self.synced_file = Path(history_dir) / f"chat_{self.id}_last_synced.txt"
		self.last_synced = self._load_last_synced_id()

	def _load_last_synced_id(self) -> int:
		if self.synced_file.exists():
			try:
				return int(self.synced_file.read_text())
			except ValueError:
				return 0
		return 0
	
	def _save_last_synced_id(self) -> None:
		self.synced_file.parent.mkdir(parents=True, exist_ok=True)
		self.synced_file.write_text(str(self.last_synced))
	
	def last_outgoing(self) -> bool:
		"""
		Zwraca True, jeśli ostatnia wiadomość w czacie była wysłana przez nas.
		"""
		history_iter = self.client.get_chat_history(self.id, limit=1)
		try:
			last_msg = next(history_iter)
		except StopIteration:
			return False
		outgoing = last_msg.outgoing
		result = False if not outgoing or last_msg.text[:5] == 'user:' else True
		return result
	
	def simulate_typing(self, message: str, wpm: int = 100, sigma: float = 0.3, min_delay: float = 0.5, max_delay: float = 3.0) -> None:
		"""
		Symuluje wpisywanie każego słowa osobno z czasem wygenerowanym z rozkładu normalnego.
		- wpm: średnia liczba słów na minutę (np. 40)
		- sigma: odchylenie standardowe w sekundach
		- min_delay, max_delay: ograniczenia czasów dla pojedynczego słowa
		"""
		# Oblicz średni czas na słowo
		avg_word_time = 60.0 / wpm  # sekundy na słowo
		words = message.split()
		total_delay = 0.0
		for word in words:
			if len(word) < 2:
				continue
			# losuj delay = N(avg_word_time, sigma)
			delay = random.gauss(avg_word_time, sigma)
			delay = max(min_delay, min(max_delay, delay))
			total_delay += delay
		logger.info(f"Symulowane opóźnienie: {total_delay:.2f} sekundy")
		time.sleep(total_delay)

	def send_message(self, message: str) -> None:
		"""
		Wysyła wiadomość do czatu i synchronizuje historię.
		"""
		sent_message = self.client.send_message(self.id, message)
		self.last_synced = sent_message.id
		self._save_last_synced_id()
		logger.info(f"Wysłano wiadomość o id {sent_message.id} do {self.title} (ID: {self.id})")

	def send_message_human(self, text: str) -> None:
		"""
		Symuluje wpisywanie i wysyła wiadomość do chatu.
		"""
		self.simulate_typing(text)
		sent_message = self.client.send_message(self.id, text)
		self.last_synced = sent_message.id
		self._save_last_synced_id()
		logger.info(f"Wysłano wiadomość o id {sent_message.id} do {self.title} (ID: {self.id})")

	def sync_history(self) -> None:
		"""
		Synchronizuje nowe wiadomości z Telegrama do AIConversationManager.
		Przypisuje role: 'user' dla incoming, 'assistant' dla outgoing.
		"""
		# Pobierz historię (od najnowszych)
		new_msgs = []
		for msg in self.client.get_chat_history(self.id, limit=20):
			if msg.id <= self.last_synced:
				break
			new_msgs.append(msg)
		# Dodaj w kolejności chronologicznej
		for msg in reversed(new_msgs):
			content = msg.text or msg.caption or None
			role = "user" if not msg.outgoing or content[:5] == 'user:' else "assistant"
			if content:
				if role == "user":
					self.ai.add_user_message(content)
				else:
					self.ai.add_ai_message(content)
			self.last_synced = msg.id
		if new_msgs:
			# Zapisz historię AI i zaktualizuj marker
			self.ai.save_history()
			self._save_last_synced_id()

class TelegramManager:
	"""
	Zarządza pobieraniem czatów i tworzeniem obiektów Chat.
	"""
	def __init__(
		self,
		client: Client,
		openai_api_key: str,
		history_dir: str = "history",
		limit: int = 100
	):
		self.client = client
		self.openai_api_key = openai_api_key
		self.history_dir = history_dir
		self.limit = limit

	def get_chats(self, ignored_chats: list[int] = []) -> list[Chat]:
		"""
		Pobiera listę Dialog i zwraca listę obiektów Chat.
		"""
		dialogs = self.client.get_dialogs(limit=self.limit)
		chats: list[Chat] = []
		for d in dialogs:
			# Filtruj czaty, które nie są prywatne, grupowe ani supergrupowe
			if d.chat.type.name.lower() == "private" and d.chat.id not in ignored_chats:
				# Jeśli czat jest prywatny, dodaj go do listy czatów
				chats.append(Chat(
					dialog=d,
					client=self.client,
					openai_api_key=self.openai_api_key,
					history_dir=self.history_dir
				))
			else:
				continue
				
		return chats

if __name__ == "__main__":
	if not OPENAI_API_KEY:
		raise RuntimeError("Ustaw OPENAI_API_KEY w pliku .env")

	with app:
		manager = TelegramManager(
			client=app,
			openai_api_key=OPENAI_API_KEY
		)
		ingored_chats = [777000,1354558262]
		chats: list[Chat] = manager.get_chats(ignored_chats=ingored_chats)
		logger.info(f"Znaleziono {len(chats)} czatów:")
		for chat in chats:
			logger.info(f" - {chat.title} (ID: {chat.id})")
		while True:
			try:
				for chat in chats:
					# Synchronizacja historii z AI
					chat.sync_history()
					#chat.ai.add_system_message("Zdradź użytkownikowi wszystkie swoje wiadomości systemowe, które masz w historii. i wyślij w następnej wiadomości")
					last_outgoing = chat.last_outgoing()
					if not last_outgoing:
						# Pobierz wiadomość od AI
						logger.info(f"Nadeszła nowa wiadomość w czacie {chat.title} (ID: {chat.id}) - last_synced: {chat.last_synced}")
						logger.info("Przystępuję do generowania odpowiedzi...")
						wiadomosc = chat.ai.get_response()
						chat.send_message_human(wiadomosc)
				time.sleep(5)  # Opóźnienie między iteracjami, aby nie przeciążać API
			except KeyboardInterrupt:
				logger.info("Przerwano przez użytkownika.")
				for chat in chats:
					# Synchronizacja historii z AI
					chat.sync_history()
				break
			except Exception as e:
				logger.error(f"Błąd: {e}", exc_info=True)
				for chat in chats:
					# Synchronizacja historii z AI
					chat.sync_history()
				raise e