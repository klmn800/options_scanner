#!/usr/bin/env python3
"""
Simple Ollama Chat Interface
A minimal CLI for chatting with local Ollama models
"""

import json
import sys
import argparse
import requests
from datetime import datetime
from pathlib import Path


class OllamaChat:
    """Simple chat interface for Ollama models"""
    
    def __init__(self, model=None, host=None, config_path=None):
        """Initialize the chat interface with configuration"""
        self.config = self._load_config(config_path)
        
        # Override config with parameters
        self.model = model or self.config.get('default_model', 'llama3')
        self.host = host or self.config.get('ollama_host', 'http://localhost:11434')
        self.timeout = self.config.get('timeout', 30)
        self.temperature = self.config.get('temperature', 0.7)
        
        self.conversation_history = []
        
    def _load_config(self, config_path=None):
        """Load configuration from config.json"""
        if not config_path:
            config_path = Path(__file__).parent / 'config.json'
        
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            # Return minimal default config if file not found
            return {
                'default_model': 'llama3',
                'ollama_host': 'http://localhost:11434',
                'timeout': 30,
                'temperature': 0.7
            }
    
    def check_connection(self):
        """Check if Ollama server is accessible"""
        try:
            response = requests.get(f"{self.host}/api/tags", timeout=5)
            return response.status_code == 200
        except requests.exceptions.ConnectionError:
            return False
        except Exception:
            return False
    
    def list_models(self):
        """Get list of available models from Ollama"""
        try:
            response = requests.get(f"{self.host}/api/tags", timeout=self.timeout)
            if response.status_code == 200:
                data = response.json()
                return [model['name'] for model in data.get('models', [])]
            return []
        except Exception:
            return []
    
    def chat(self, message):
        """Send message to Ollama and get response"""
        endpoint = f"{self.host}/api/generate"
        
        payload = {
            "model": self.model,
            "prompt": message,
            "stream": False,
            "options": {
                "temperature": self.temperature
            }
        }
        
        try:
            response = requests.post(endpoint, json=payload, timeout=self.timeout)
            if response.status_code == 200:
                result = response.json()
                return result.get('response', 'No response received')
            else:
                return f"Error: HTTP {response.status_code} - {response.text}"
        except requests.exceptions.ConnectionError:
            return "Error: Cannot connect to Ollama. Is it running? (ollama serve)"
        except requests.exceptions.Timeout:
            return f"Error: Request timed out after {self.timeout} seconds"
        except Exception as e:
            return f"Error: {str(e)}"
    
    def display_help(self):
        """Display help information"""
        print("\\nCommands:")
        print("  /help           - Show this help")
        print("  /models         - List available models")
        print("  /model <name>   - Switch to different model")
        print("  /config         - Show current configuration")
        print("  /clear          - Clear conversation history")
        print("  /exit or /quit  - Exit the chat")
        print("\\nExample models: llama3, mistral, codellama")
    
    def display_config(self):
        """Display current configuration"""
        print(f"\\nCurrent Configuration:")
        print(f"  Model: {self.model}")
        print(f"  Host: {self.host}")
        print(f"  Timeout: {self.timeout}s")
        print(f"  Temperature: {self.temperature}")
        print(f"  Messages in history: {len(self.conversation_history)}")
    
    def run(self):
        """Main chat loop"""
        print("\\n" + "="*50)
        print(f"Ollama Chat - Model: {self.model}")
        print("="*50)
        
        # Check if Ollama is running
        if not self.check_connection():
            print("❌ Cannot connect to Ollama server!")
            print(f"   Make sure Ollama is running at {self.host}")
            print("   Try running: ollama serve")
            return
        
        print("✅ Connected to Ollama server")
        
        # Get available models
        available_models = self.list_models()
        if available_models:
            print(f"📋 Available models: {', '.join(available_models[:5])}")
            if self.model not in available_models:
                print(f"⚠️  Model '{self.model}' not found. You may need to pull it first.")
                print(f"   Try: ollama pull {self.model}")
        
        print("\\nType '/help' for commands, '/exit' to quit\\n")
        
        while True:
            try:
                user_input = input("You: ").strip()
                
                if not user_input:
                    continue
                
                # Handle commands
                if user_input.startswith('/'):
                    if self._handle_command(user_input):
                        continue
                    else:
                        break  # Exit requested
                
                # Send message to Ollama
                print("Ollama: ", end='', flush=True)
                response = self.chat(user_input)
                print(response)
                
                # Store in history
                self.conversation_history.append({
                    "timestamp": datetime.now().isoformat(),
                    "user": user_input,
                    "assistant": response,
                    "model": self.model
                })
                
            except KeyboardInterrupt:
                print("\\n\\nGoodbye!")
                break
            except EOFError:
                print("\\nGoodbye!")
                break
            except Exception as e:
                print(f"Error: {e}")
    
    def _handle_command(self, command):
        """Handle chat commands. Returns True to continue, False to exit"""
        parts = command[1:].split()
        cmd = parts[0].lower() if parts else ''
        
        if cmd in ['exit', 'quit']:
            print("Goodbye!")
            return False
        
        elif cmd == 'help':
            self.display_help()
        
        elif cmd == 'models':
            models = self.list_models()
            if models:
                print(f"\\nAvailable models:")
                for model in models:
                    marker = " (current)" if model == self.model else ""
                    print(f"  - {model}{marker}")
            else:
                print("\\nNo models found or cannot connect to Ollama")
        
        elif cmd == 'model':
            if len(parts) > 1:
                new_model = parts[1]
                self.model = new_model
                print(f"Switched to model: {self.model}")
            else:
                print("Usage: /model <model_name>")
                print("Example: /model mistral")
        
        elif cmd == 'config':
            self.display_config()
        
        elif cmd == 'clear':
            self.conversation_history = []
            print("Conversation history cleared.")
        
        else:
            print(f"Unknown command: /{cmd}")
            print("Type '/help' for available commands")
        
        return True


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Chat with Ollama models')
    parser.add_argument('--model', help='Model to use (default: llama3)')
    parser.add_argument('--host', help='Ollama host URL (default: http://localhost:11434)')
    parser.add_argument('--config', help='Path to config file')
    parser.add_argument('--list-models', action='store_true', help='List available models and exit')
    
    args = parser.parse_args()
    
    # Just list models and exit if requested
    if args.list_models:
        chat = OllamaChat(host=args.host, config_path=args.config)
        models = chat.list_models()
        if models:
            print("Available models:")
            for model in models:
                print(f"  - {model}")
        else:
            print("No models found or cannot connect to Ollama")
        return
    
    # Start the chat
    chat = OllamaChat(
        model=args.model,
        host=args.host,
        config_path=args.config
    )
    chat.run()


if __name__ == "__main__":
    main()