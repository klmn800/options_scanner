# Oracle Ollama Chat Interface

A simple, standalone chat interface for interacting with local Ollama models. This provides an offline AI alternative for when Claude API is unavailable.

## Quick Start

### 1. Install Ollama
- Download Ollama from https://ollama.ai/download/windows
- Install and run the application

### 2. Pull a Model
```bash
# Pull the default model (recommended)
ollama pull llama3

# Or try other models
ollama pull mistral
ollama pull codellama
```

### 3. Start Ollama Server
```bash
# This usually starts automatically, but if needed:
ollama serve
```

### 4. Run the Chat Interface
```bash
# Basic usage
python oracle/ollama/chat.py

# With specific model
python oracle/ollama/chat.py --model mistral

# List available models
python oracle/ollama/chat.py --list-models
```

## Usage

### Basic Chat
```
You: Hello! How are you?
Ollama: Hello! I'm doing well, thank you for asking. How can I help you today?
```

### Commands
- `/help` - Show available commands
- `/models` - List available models
- `/model <name>` - Switch to different model
- `/config` - Show current configuration
- `/clear` - Clear conversation history
- `/exit` or `/quit` - Exit the chat

### Examples
```
You: /model codellama
Switched to model: codellama

You: Write a Python function to calculate fibonacci numbers
Ollama: Here's a Python function to calculate Fibonacci numbers...
```

## Configuration

Edit `config.json` to customize:
- `default_model`: Model to use by default
- `ollama_host`: Ollama server URL (default: http://localhost:11434)
- `timeout`: Request timeout in seconds
- `temperature`: Response creativity (0.0-1.0)

## Recommended Models

| Model | Size | Description | Command |
|-------|------|-------------|---------|
| llama3 | 4.7GB | Best balance of speed and quality | `ollama pull llama3` |
| mistral | 4.1GB | Faster, good for general chat | `ollama pull mistral` |
| codellama | 3.8GB | Optimized for coding tasks | `ollama pull codellama` |

## Troubleshooting

**"Cannot connect to Ollama"**
- Make sure Ollama is installed and running
- Check if the service is running: `ollama serve`
- Verify the host URL in config.json

**"Model not found"**
- Pull the model first: `ollama pull <model-name>`
- Check available models: `ollama list`

**Slow responses**
- Try a smaller model like `mistral` instead of `llama3`
- Reduce the temperature in config.json
- Close other applications using GPU/RAM

## Future Integration

This standalone chat interface will eventually integrate with the main Oracle system to provide:
- Offline SQL result analysis
- Fallback when Claude API is unavailable  
- Local processing for sensitive data

## Requirements

- Python 3.7+
- requests library (pip install requests)
- Ollama application running locally