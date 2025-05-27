import json
import datetime
import os
from typing import Optional, List, Dict
from openai import OpenAI
from dotenv import load_dotenv

class AIConversationManager:
	"""
	Zarządza historią rozmowy AI dla konkretnego czatu.
	Historia jest przechowywana w pliku w katalogu `history_dir`.
	"""
	def __init__(
			self,
			api_key: str,
			chat_id: int,
			history_dir: str = "history",
			model: str = "gpt-4o-mini",
			system_prompt: Optional[str] = None,
			system_prompt_file: Optional[str] = None
		):
		self.client = OpenAI(api_key=api_key)
		self.model = model
		self.chat_id = chat_id
		self.history_dir = history_dir
		os.makedirs(self.history_dir, exist_ok=True)
		# Domyślna nazwa pliku na podstawie chat_id
		self.history_file = os.path.join(
			self.history_dir,
			f"chat_{self.chat_id}_history.json"
		)

		# Ustaw system prompt i ewentualny plik źródłowy
		default_prompt = "Jesteś pomocnym asystentem AI."
		if system_prompt:
			self.system_prompt = system_prompt
		elif system_prompt_file and os.path.exists(system_prompt_file):
			with open(system_prompt_file, 'r', encoding='utf-8') as f:
				self.system_prompt = f.read().strip()
		else:
			self.system_prompt = default_prompt
		self.system_prompt_file = system_prompt_file

		# Załaduj lub zainicjalizuj historię
		self.messages: List[Dict[str, str]] = []
		self.load_history()

	def load_history(self) -> None:
		"""
		Wczytuje historię z pliku, jeśli istnieje; zawsze dba o to,
		żeby pierwsza wiadomość była system promptem i była aktualna.
		"""
		if os.path.exists(self.history_file):
			with open(self.history_file, 'r', encoding='utf-8') as f:
				data = json.load(f)
				self.model = data.get("model", self.model)
				# Nadpisz system prompt z pliku historii, ale zachowaj aktualny wartość
				file_prompt = data.get("system_prompt", self.system_prompt)
				# Jeśli zmienił się prompt plikowy, użyj tego z parametrów konstrukcji
				self.system_prompt = self.system_prompt or file_prompt
				self.messages = data.get("messages", [])
		# Upewnij się, że pierwsza wiadomość to zawsze aktualny system prompt
		if self.messages and self.messages[0].get("role") == "system":
			self.messages[0]["content"] = self.system_prompt
		else:
			self.messages.insert(0, {"role": "system", "content": self.system_prompt})

	def add_system_message(self, content: str) -> None:
		"""Aktualizuje system prompt w historii"""
		# Zaktualizuj atrybut i pierwszą wiadomość w historii
		self.system_prompt = content
		if self.messages and self.messages[0].get("role") == "system":
			self.messages[0]["content"] = content
		else:
			self.messages.insert(0, {"role": "system", "content": content})

	def update_system_prompt(self, new_prompt: str, save: bool = False) -> None:
		"""
		Ustawia nowy system prompt i aktualizuje historię.
		Jeśli save=True, od razu zapisuje historię.
		"""
		self.add_system_message(new_prompt)
		if save:
			self.save_history()

	def update_system_prompt_from_file(self, file_path: str, save: bool = False) -> None:
		"""
		Wczytuje system prompt z pliku i aktualizuje historię.
		"""
		if not os.path.exists(file_path):
			raise FileNotFoundError(f"Brak pliku: {file_path}")
		with open(file_path, 'r', encoding='utf-8') as f:
			prompt = f.read().strip()
		self.update_system_prompt(prompt, save=save)
	
	def save_history(self) -> None:
		"""
		Zapisuje historię rozmowy do pliku JSON wraz z metadanymi.
		"""
		payload = {
			"timestamp": datetime.datetime.now().isoformat(),
			"model": self.model,
			"system_prompt": self.system_prompt,
			"messages": self.messages
		}
		with open(self.history_file, 'w', encoding='utf-8') as f:
			json.dump(payload, f, ensure_ascii=False, indent=2)

	def add_user_message(self, content: str) -> None:
		"""Dodaje do historii wiadomość od użytkownika"""
		self.messages.append({"role": "user", "content": content})

	def add_ai_message(self, content: str) -> None:
		"""Dodaje do historii wiadomość od asystenta AI"""
		self.messages.append({"role": "assistant", "content": content})

	def add_system_message(self, content: str) -> None:
		"""Dodaje do historii wiadomość od systemu"""
		self.messages.append({"role": "system", "content": content})

	def get_response(self, user_message: str = None, save_history: bool = True) -> str:
		"""
		Dodaje wiadomość użytkownika (lub nie), wysyła żądanie do OpenAI i zwraca odpowiedź.
		"""
		if user_message:
			self.add_user_message(user_message)
		response = self.client.chat.completions.create(
			model=self.model,
			messages=self.messages
		)
		ai_content = response.choices[0].message.content
		if save_history:
			self.add_ai_message(ai_content)
			self.save_history()
		elif user_message:
			# Jeśli nie zapisujemy historii a w wejśćiu funkcji była jakaś wiadomość to usuwamy ostatnią wiadomość
			self.messages.pop()
		return ai_content

	def reset_conversation(self) -> None:
		"""Resetuje historię, zachowując jedynie system prompt"""
		self.messages = [{"role": "system", "content": self.system_prompt}]


if __name__ == "__main__":
	# Załaduj klucz API z pliku .env
	api_key = os.getenv("OPENAI_API_KEY")
	if not api_key:
		print("Nie znaleziono klucza API. Ustaw OPENAI_API_KEY w pliku .env.")
		exit(1)
	# Inicjalizacja menedżera konwersacji
	chat_id = input("Podaj chat_id (użyj liczby dla identyfikatora rozmowy): ")
	try:
		chat_id = int(chat_id)
	except ValueError:
		print("Nieprawidłowy chat_id. Użyj liczby.")
		exit(1)
	cm = AIConversationManager(
		api_key=api_key,
		chat_id=chat_id,
		history_dir="history",
		system_prompt_file="system_prompts/telegram_troll.txt"
	)
	print("Rozpoczynam interaktywną rozmowę. Wpisz 'exit' aby zakończyć.")
	while True:
		user_input = input("Ty: ")
		if user_input.lower() in ("exit", "quit"):
			print("Koniec rozmowy.")
			break
		response = cm.get_response(user_input, save_history=False)
		print(f"Bot: {response}\n")
