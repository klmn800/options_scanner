"""
OpenAI (GPT) model interface
"""
import os
import json
from typing import List, Dict, Optional
from .base_model import BaseModelInterface

# AVAILABLE MODELS - Copy these exact strings to personality files
MODELS = {
    # GPT-4o Series (Latest)
    "gpt-4o": {
        "name": "GPT-4o (Omni)",
        "context": 128000,
        "strengths": ["reasoning", "coding", "vision", "multimodal"],
        "cost_per_1k_tokens": 0.005,
        "description": "Latest GPT-4 with vision capabilities"
    },
    "gpt-4o-mini": {
        "name": "GPT-4o Mini (Efficient)",
        "context": 128000,
        "strengths": ["speed", "cost-effective", "general tasks"],
        "cost_per_1k_tokens": 0.00015,
        "description": "Efficient version of GPT-4o, great value"
    },
    
    # GPT-4 Turbo Series
    "gpt-4-turbo": {
        "name": "GPT-4 Turbo (Latest)",
        "context": 128000,
        "strengths": ["complex tasks", "large context", "accuracy"],
        "cost_per_1k_tokens": 0.01,
        "description": "High-performance GPT-4 with large context window"
    },
    "gpt-4-turbo-preview": {
        "name": "GPT-4 Turbo Preview",
        "context": 128000,
        "strengths": ["complex tasks", "preview features"],
        "cost_per_1k_tokens": 0.01,
        "description": "Preview version of GPT-4 Turbo"
    },
    
    # GPT-4 Base
    "gpt-4": {
        "name": "GPT-4 (Original)",
        "context": 8192,
        "strengths": ["reasoning", "accuracy", "complex tasks"],
        "cost_per_1k_tokens": 0.03,
        "description": "Original GPT-4 model"
    },
    "gpt-4-32k": {
        "name": "GPT-4 32K Context",
        "context": 32768,
        "strengths": ["long context", "detailed analysis"],
        "cost_per_1k_tokens": 0.06,
        "description": "GPT-4 with extended context window"
    },
    
    # GPT-3.5 Series
    "gpt-3.5-turbo": {
        "name": "GPT-3.5 Turbo (Latest)",
        "context": 16385,
        "strengths": ["speed", "cost-effective", "general chat"],
        "cost_per_1k_tokens": 0.0005,
        "description": "Fast and cost-effective for simple tasks"
    },
    "gpt-3.5-turbo-16k": {
        "name": "GPT-3.5 Turbo 16K",
        "context": 16385,
        "strengths": ["speed", "longer context", "cost-effective"],
        "cost_per_1k_tokens": 0.001,
        "description": "GPT-3.5 with larger context window"
    }
}

class OpenAIInterface(BaseModelInterface):
    """Interface for OpenAI's GPT models"""
    
    def _initialize_client(self):
        """Initialize OpenAI client"""
        try:
            from openai import OpenAI
            
            # Try to get API key from various sources
            api_key = self._get_api_key()
            if not api_key:
                raise ValueError("OpenAI API key not found")
            
            self.client = OpenAI(api_key=api_key)
            
        except ImportError:
            raise ImportError("openai package not installed. Run: pip install openai")
        except Exception as e:
            raise Exception(f"Failed to initialize OpenAI client: {e}")
    
    def _get_api_key(self):
        """Get OpenAI API key from config or environment"""
        # Try config.json first
        try:
            config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'config.json')
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    openai_config = config.get('openai_api', {})
                    if openai_config.get('api_key'):
                        return openai_config['api_key']
        except:
            pass
        
        # Try environment variable
        return os.environ.get('OPENAI_API_KEY')
    
    def query(self, 
              query: str, 
              system_prompt: str = "", 
              temperature: float = 0.7,
              max_tokens: int = 2000,
              conversation_history: Optional[List[Dict]] = None) -> str:
        """Send query to GPT and return response"""
        
        if not self.client:
            raise Exception("OpenAI client not initialized")
        
        try:
            # Build messages array
            messages = []
            
            # Add system prompt if provided
            if system_prompt:
                messages.append({
                    'role': 'system',
                    'content': system_prompt
                })
            
            # Add conversation history
            if conversation_history:
                formatted_history = self.format_conversation_history(conversation_history)
                messages.extend(formatted_history)
            
            # Add current query
            messages.append({
                'role': 'user',
                'content': query
            })
            
            # Send request to OpenAI
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            return f"❌ OpenAI API Error: {str(e)}"
    
    def is_available(self) -> bool:
        """Check if GPT is available"""
        try:
            if not self.client:
                return False
            
            # Test with a simple query
            test_response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": "Hi"}],
                max_tokens=5
            )
            return True
            
        except Exception:
            return False
    
    @staticmethod
    def list_models():
        """List all available GPT models"""
        return MODELS
    
    @staticmethod
    def get_model_info(model_name: str):
        """Get detailed information about a specific model"""
        return MODELS.get(model_name, {})
    
    @staticmethod
    def recommend_model(use_case: str):
        """Recommend a model based on use case"""
        recommendations = {
            'complex_analysis': 'gpt-4o',
            'coding': 'gpt-4o',
            'general': 'gpt-4o-mini',
            'fast': 'gpt-3.5-turbo',
            'cost_effective': 'gpt-3.5-turbo',
            'reasoning': 'gpt-4o',
            'long_context': 'gpt-4-turbo'
        }
        return recommendations.get(use_case.lower(), 'gpt-4o-mini')