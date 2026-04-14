"""
xAI (Grok) model interface
"""
import os
import json
from typing import List, Dict, Optional
from .base_model import BaseModelInterface

# AVAILABLE MODELS - Copy these exact strings to personality files
MODELS = {
    # Grok Series
    "grok-2": {
        "name": "Grok 2",
        "context": 128000,
        "strengths": ["reasoning", "coding", "real-time info", "humor"],
        "cost_per_1k_tokens": 0.002,  # Estimated
        "description": "Latest Grok model with real-time knowledge and humor"
    },
    "grok-2-mini": {
        "name": "Grok 2 Mini",
        "context": 128000,
        "strengths": ["speed", "efficiency", "cost-effective"],
        "cost_per_1k_tokens": 0.0005,  # Estimated
        "description": "Smaller, faster version of Grok 2"
    },
    "grok-1": {
        "name": "Grok 1",
        "context": 64000,
        "strengths": ["reasoning", "humor", "contrarian thinking"],
        "cost_per_1k_tokens": 0.003,  # Estimated
        "description": "Original Grok model with unique personality"
    }
}

class XAIInterface(BaseModelInterface):
    """Interface for xAI's Grok models"""
    
    def _initialize_client(self):
        """Initialize xAI client"""
        try:
            # xAI uses OpenAI-compatible API
            from openai import OpenAI
            
            # Try to get API key from various sources
            api_key = self._get_api_key()
            if not api_key:
                raise ValueError("xAI API key not found")
            
            # xAI uses their own base URL
            self.client = OpenAI(
                api_key=api_key,
                base_url="https://api.x.ai/v1"
            )
            
        except ImportError:
            raise ImportError("openai package not installed. Run: pip install openai")
        except Exception as e:
            raise Exception(f"Failed to initialize xAI client: {e}")
    
    def _get_api_key(self):
        """Get xAI API key from config or environment"""
        # Try config.json first
        try:
            config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'config.json')
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    xai_config = config.get('xai_api', {}) or config.get('grok_api', {})
                    if xai_config.get('api_key'):
                        return xai_config['api_key']
        except:
            pass
        
        # Try environment variables
        return (os.environ.get('XAI_API_KEY') or 
                os.environ.get('GROK_API_KEY') or
                os.environ.get('X_API_KEY'))
    
    def query(self, 
              query: str, 
              system_prompt: str = "", 
              temperature: float = 0.7,
              max_tokens: int = 2000,
              conversation_history: Optional[List[Dict]] = None) -> str:
        """Send query to Grok and return response"""
        
        if not self.client:
            raise Exception("xAI client not initialized")
        
        try:
            # Build messages array (OpenAI-compatible format)
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
            
            # Send request to Grok
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            return f"❌ xAI API Error: {str(e)}"
    
    def is_available(self) -> bool:
        """Check if Grok is available"""
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
        """List all available Grok models"""
        return MODELS
    
    @staticmethod
    def get_model_info(model_name: str):
        """Get detailed information about a specific model"""
        return MODELS.get(model_name, {})
    
    @staticmethod
    def recommend_model(use_case: str):
        """Recommend a model based on use case"""
        recommendations = {
            'reasoning': 'grok-2',
            'coding': 'grok-2',
            'humor': 'grok-1',
            'contrarian': 'grok-1',
            'fast': 'grok-2-mini',
            'cost_effective': 'grok-2-mini',
            'general': 'grok-2'
        }
        return recommendations.get(use_case.lower(), 'grok-2')