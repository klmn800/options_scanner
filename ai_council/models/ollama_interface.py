"""
Ollama (Local models) interface
"""
import os
import requests
import json
from typing import List, Dict, Optional
from .base_model import BaseModelInterface

# AVAILABLE MODELS - Copy these exact strings to personality files
MODELS = {
    # Llama Series
    "llama3.2": {
        "name": "Llama 3.2 (Latest)", 
        "sizes": ["1B", "3B"],
        "strengths": ["efficiency", "local inference"],
        "description": "Latest Llama model, very efficient"
    },
    "llama3.1:8b": {
        "name": "Llama 3.1 8B", 
        "sizes": ["8B"],
        "strengths": ["reasoning", "coding", "large context"],
        "description": "Powerful Llama model with large context window - 8B variant"
    },
    "llama3.1": {
        "name": "Llama 3.1", 
        "sizes": ["8B", "70B", "405B"],
        "strengths": ["reasoning", "coding", "large context"],
        "description": "Powerful Llama model with large context window"
    },
    "llama3": {
        "name": "Llama 3", 
        "sizes": ["8B", "70B"],
        "strengths": ["general tasks", "reasoning"],
        "description": "Meta's Llama 3 model"
    },
    "llama2": {
        "name": "Llama 2", 
        "sizes": ["7B", "13B", "70B"],
        "strengths": ["general tasks", "stability"],
        "description": "Previous generation Llama model"
    },
    
    # Code Models
    "codellama": {
        "name": "Code Llama", 
        "sizes": ["7B", "13B", "34B"],
        "strengths": ["coding", "programming", "code generation"],
        "description": "Llama fine-tuned for coding tasks"
    },
    "deepseek-coder": {
        "name": "DeepSeek Coder", 
        "sizes": ["1.3B", "6.7B", "33B"],
        "strengths": ["coding", "efficiency", "programming"],
        "description": "Specialized coding model with excellent performance"
    },
    "qwen2.5-coder": {
        "name": "Qwen 2.5 Coder", 
        "sizes": ["1.5B", "7B", "32B"],
        "strengths": ["coding", "multilingual", "efficiency"],
        "description": "Alibaba's coding model"
    },
    
    # Mistral Series
    "mistral": {
        "name": "Mistral 7B", 
        "sizes": ["7B"],
        "strengths": ["efficiency", "general tasks", "speed"],
        "description": "Efficient model from Mistral AI"
    },
    "mixtral": {
        "name": "Mixtral 8x7B MoE", 
        "sizes": ["8x7B"],
        "strengths": ["reasoning", "multilingual", "mixture of experts"],
        "description": "Mixture of Experts model with high performance"
    },
    
    # Google Models
    "gemma2": {
        "name": "Google Gemma 2", 
        "sizes": ["2B", "9B", "27B"],
        "strengths": ["efficiency", "safety", "general tasks"],
        "description": "Google's open model family"
    },
    
    # Microsoft Models
    "phi3": {
        "name": "Microsoft Phi-3", 
        "sizes": ["3.8B", "14B"],
        "strengths": ["efficiency", "reasoning", "small size"],
        "description": "Compact but capable model from Microsoft"
    },
    
    # Alibaba Models
    "qwen2.5": {
        "name": "Qwen 2.5", 
        "sizes": ["0.5B", "1.5B", "3B", "7B", "14B", "32B", "72B"],
        "strengths": ["multilingual", "reasoning", "variety of sizes"],
        "description": "Alibaba's multilingual model family"
    },
    
    # Other Models
    "gpt-oss:20b": {
        "name": "GPT OSS 20B",
        "sizes": ["20B"],
        "strengths": ["large scale", "general tasks", "reasoning"],
        "description": "Open source GPT-style model with 20B parameters"
    }
}

class OllamaInterface(BaseModelInterface):
    """Interface for Ollama local models"""
    
    def __init__(self, model_name: str, host: str = "http://localhost:11434"):
        self.host = host
        super().__init__(model_name)
    
    def _initialize_client(self):
        """Initialize Ollama connection"""
        try:
            # Test if Ollama is running
            response = requests.get(f"{self.host}/api/tags", timeout=5)
            if response.status_code == 200:
                self.client = True  # Simple flag for Ollama
                
                # Check if our specific model is available
                available_models = response.json().get('models', [])
                model_names = [model['name'] for model in available_models]  # Keep full names
                base_names = [model['name'].split(':')[0] for model in available_models]  # Also check base names
                
                if self.model_name not in model_names and self.model_name not in base_names:
                    print(f"WARNING: Model {self.model_name} not found locally.")
                    print(f"Available models: {', '.join(model_names)}")
                    print(f"To install: ollama pull {self.model_name}")
                    self.client = False
            else:
                raise Exception(f"Ollama not responding (status: {response.status_code})")
                
        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to connect to Ollama at {self.host}: {e}")
        except Exception as e:
            raise Exception(f"Failed to initialize Ollama: {e}")
    
    def query(self, 
              query: str, 
              system_prompt: str = "", 
              temperature: float = 0.7,
              max_tokens: int = 2000,
              conversation_history: Optional[List[Dict]] = None) -> str:
        """Send query to Ollama and return response"""
        
        if not self.client:
            return "❌ Ollama not available or model not installed"
        
        try:
            # Build the full prompt with system prompt and history
            full_prompt = ""
            
            if system_prompt:
                full_prompt += f"System: {system_prompt}\n\n"
            
            # Add conversation history
            if conversation_history:
                for exchange in conversation_history:
                    full_prompt += f"Human: {exchange.get('query', '')}\n"
                    full_prompt += f"Assistant: {exchange.get('response', '')}\n\n"
            
            # Add current query
            full_prompt += f"Human: {query}\nAssistant:"
            
            # Prepare request payload
            payload = {
                "model": self.model_name,
                "prompt": full_prompt,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens
                }
            }
            
            # Send request to Ollama
            response = requests.post(
                f"{self.host}/api/generate",
                json=payload,
                timeout=60  # Longer timeout for local inference
            )
            
            if response.status_code == 200:
                result = response.json()
                return result.get('response', 'No response received')
            else:
                return f"❌ Ollama API Error: {response.status_code}"
                
        except Exception as e:
            return f"❌ Ollama Error: {str(e)}"
    
    def is_available(self) -> bool:
        """Check if Ollama and the model are available"""
        try:
            if not self.client:
                return False
            
            # Test with a simple query
            test_payload = {
                "model": self.model_name,
                "prompt": "Hi",
                "stream": False,
                "options": {"num_predict": 5}
            }
            
            response = requests.post(
                f"{self.host}/api/generate",
                json=test_payload,
                timeout=10
            )
            
            return response.status_code == 200
            
        except Exception:
            return False
    
    def list_installed_models(self):
        """List models currently installed in Ollama"""
        try:
            response = requests.get(f"{self.host}/api/tags", timeout=5)
            if response.status_code == 200:
                models_data = response.json().get('models', [])
                return [
                    {
                        'name': model['name'],
                        'size': model.get('size', 0),
                        'modified': model.get('modified_at', '')
                    }
                    for model in models_data
                ]
        except:
            return []
    
    @staticmethod
    def list_models():
        """List all available Ollama models"""
        return MODELS
    
    @staticmethod
    def get_model_info(model_name: str):
        """Get detailed information about a specific model"""
        return MODELS.get(model_name, {})
    
    @staticmethod
    def recommend_model(use_case: str):
        """Recommend a model based on use case"""
        recommendations = {
            'coding': 'deepseek-coder',
            'general': 'llama3.1',
            'fast': 'llama3.2',
            'reasoning': 'mixtral',
            'efficient': 'phi3',
            'multilingual': 'qwen2.5'
        }
        return recommendations.get(use_case.lower(), 'llama3.1')