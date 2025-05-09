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

		# Wczytaj system prompt
		default_prompt = "Jesteś pomocnym asystentem AI."
		if system_prompt:
			self.system_prompt = system_prompt
		elif system_prompt_file and os.path.exists(system_prompt_file):
			with open(system_prompt_file, 'r', encoding='utf-8') as f:
				self.system_prompt = f.read().strip()
		else:
			self.system_prompt = default_prompt

		# Załaduj lub zainicjalizuj historię
		self.messages: List[Dict[str, str]] = []
		self.load_history()

	def load_history(self) -> None:
		"""
		Wczytuje historię z pliku, jeśli istnieje; w przeciwnym wypadku inicjalizuje od system prompt.
		"""
		if os.path.exists(self.history_file):
			with open(self.history_file, 'r', encoding='utf-8') as f:
				data = json.load(f)
				self.model = data.get("model", self.model)
				self.system_prompt = data.get("system_prompt", self.system_prompt)
				self.messages = data.get("messages", [])
		# Upewnij się, że pierwsza wiadomość to system prompt
		if not self.messages or self.messages[0]["role"] != "system":
			self.messages.insert(0, {"role": "system", "content": self.system_prompt})

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

	def get_response(self, user_message: str = None) -> str:
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
		self.add_ai_message(ai_content)
		self.save_history()
		return ai_content

	def reset_conversation(self) -> None:
		"""Resetuje historię, zachowując jedynie system prompt"""
		self.messages = [{"role": "system", "content": self.system_prompt}]


if __name__ == "__main__":
	
	
	# Załaduj klucz API z pliku .env
	load_dotenv()
	api_key = os.getenv("OPENAI_API_KEY")
	
	if not api_key:
		print("Nie znaleziono klucza API. Ustaw OPENAI_API_KEY w pliku .env lub w zmiennych środowiskowych.")
		exit(1)
	current_dir = os.path.dirname(os.path.abspath(__file__))
	system_prompt_file = os.path.join(current_dir, "system_prompts", "telegram_troll.txt")
	# Inicjalizuj menedżera konwersacji
	conversation = AIConversationManager(api_key,system_prompt_file=system_prompt_file)
	
	# Przykładowa interaktywna sesja
	print("Witaj! Rozpoczynamy rozmowę z AI. Wpisz 'quit' aby zakończyć.")
	
	while True:
		user_input = input("Ty: ")
		if user_input.lower() in ["quit", "exit", "koniec", "q"]:
			break
		
		try:
			response = conversation.add_message_and_get_response(user_input)
			print(f"AI: {response}")
		except Exception as e:
			print(f"Błąd: {e}")
			print(f"Historia rozmowy została zapisana w pliku {conversation.history_file}")
	
	print(f"Koniec rozmowy. Historia została zapisana w pliku {conversation.history_file}")
