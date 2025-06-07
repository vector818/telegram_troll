A sophisticated Telegram bot that leverages OpenAI's GPT models to simulate realistic human conversations with delayed responses. The bot is designed to handle multiple conversations simultaneously while maintaining context and conversation history.

## Features

- **Realistic Delayed Responses**: Simulates human typing and response timing with randomized delays
- **Conversation Memory**: Maintains conversation history for each chat
- **Multi-Chat Support**: Handles multiple conversations simultaneously
- **Automatic Response**: Processes existing unread messages when started
- **Customizable Personality**: Uses system prompts to define bot behavior
- **History Management**: Saves conversation history to JSON files

## Requirements

- Python 3.6+
- Telegram API credentials (API ID and Hash)
- OpenAI API key
- Required Python packages (see requirements.txt)

## Installation

1. Clone this repository
2. Install required packages:
   ```
   pip install -r requirements.txt
   ```
3. Create a .env file based on example.env with your API credentials:
   ```
   TELEGRAM_API_ID=your_telegram_api_id
   TELEGRAM_API_HASH=your_telegram_api_hash
   OPENAI_API_KEY=your_openai_api_key
   ```
4. Create a system prompt file in the system_prompts directory (e.g., `telegram_troll.txt`)

## Usage

Start the bot by running:

```
python telegram_troll.py
```

The bot will:
1. Connect to Telegram using your credentials
2. Process any existing unread messages
3. Begin responding to new messages with realistic delays

## How it Works

1. When a message is received, it's added to a queue for that specific chat
2. The bot schedules a delayed response (average 5 minutes with 3 minute standard deviation)
3. During the waiting period, any additional messages are added to the queue
4. After the delay, the bot processes all accumulated messages and generates a response
5. The bot simulates typing time based on response length
6. The response is sent to the chat

## Customization

- Modify the system prompt file to change the bot's personality and behavior
- Adjust response timing parameters in the code
- Change the AI model used for responses in the `AIConversationManager` class

## Directory Structure

- history: Contains conversation history JSON files
- system_prompts: Contains system prompt files
- .env: Configuration file for API keys
- telegram_troll.py: Main bot script

## Note

This bot is designed for educational purposes to demonstrate conversational AI capabilities. Please use responsibly and in accordance with Telegram's terms of service and OpenAI's usage policies.