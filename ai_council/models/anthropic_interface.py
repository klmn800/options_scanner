"""
Anthropic (Claude) model interface
"""
import os
import json
from typing import List, Dict, Optional
from .base_model import BaseModelInterface

# AVAILABLE MODELS - Copy these exact strings to personality files
MODELS = {
    # Claude 3.5 (Most Capable)
    "claude-3-5-sonnet-20241022": {
        "name": "Claude 3.5 Sonnet (Latest)",
        "context": 200000,
        "strengths": ["coding", "analysis", "reasoning", "long context"],
        "cost_per_1k_tokens": 0.003,
        "description": "Most capable Claude model, excellent for complex analysis"
    },
    "claude-3-5-sonnet-20240620": {
        "name": "Claude 3.5 Sonnet (Previous)",
        "context": 200000,
        "strengths": ["coding", "analysis", "reasoning"],
        "cost_per_1k_tokens": 0.003,
        "description": "Previous version of 3.5 Sonnet"
    },
    
    # Claude 3.0 Series
    "claude-3-opus-20240229": {
        "name": "Claude 3 Opus (Most Powerful)",
        "context": 200000,
        "strengths": ["complex reasoning", "creativity", "nuanced analysis"],
        "cost_per_1k_tokens": 0.015,
        "description": "Most powerful Claude 3 model, best for complex tasks"
    },
    "claude-3-sonnet-20240229": {
        "name": "Claude 3 Sonnet (Balanced)",
        "context": 200000,
        "strengths": ["general tasks", "balanced performance"],
        "cost_per_1k_tokens": 0.003,
        "description": "Balanced performance and cost"
    },
    "claude-3-haiku-20240307": {
        "name": "Claude 3 Haiku (Fastest)",
        "context": 200000,
        "strengths": ["speed", "simple tasks", "cost-effective"],
        "cost_per_1k_tokens": 0.00025,
        "description": "Fastest Claude model, good for simple tasks"
    }
}

class AnthropicInterface(BaseModelInterface):
    """Interface for Anthropic's Claude models"""
    
    def _initialize_client(self):
        """Initialize Anthropic client"""
        try:
            import anthropic
            
            # Try to get API key from various sources
            api_key = self._get_api_key()
            if not api_key:
                raise ValueError("Anthropic API key not found")
            
            self.client = anthropic.Anthropic(api_key=api_key)
            
        except ImportError:
            raise ImportError("anthropic package not installed. Run: pip install anthropic")
        except Exception as e:
            raise Exception(f"Failed to initialize Anthropic client: {e}")
    
    def _get_api_key(self):
        """Get Anthropic API key from config or environment"""
        # Try config.json first
        try:
            config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'config.json')
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    claude_config = config.get('claude_api', {})
                    if claude_config.get('api_key'):
                        return claude_config['api_key']
        except:
            pass
        
        # Try environment variable
        return os.environ.get('ANTHROPIC_API_KEY')
    
    def query(self, 
              query: str, 
              system_prompt: str = "", 
              temperature: float = 0.7,
              max_tokens: int = 2000,
              conversation_history: Optional[List[Dict]] = None) -> str:
        """Send query to Claude and return response"""
        
        if not self.client:
            raise Exception("Anthropic client not initialized")
        
        try:
            # Format conversation history
            messages = []
            if conversation_history:
                formatted_history = self.format_conversation_history(conversation_history)
                messages.extend(formatted_history)
            
            # Add current query
            messages.append({
                'role': 'user',
                'content': query
            })
            
            # Send request to Claude
            response = self.client.messages.create(
                model=self.model_name,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_prompt if system_prompt else "You are a helpful assistant.",
                messages=messages
            )
            
            return response.content[0].text
            
        except Exception as e:
            return f"❌ Anthropic API Error: {str(e)}"
    
    def is_available(self) -> bool:
        """Check if Claude is available"""
        try:
            if not self.client:
                return False
            
            # Test with a simple query
            test_response = self.client.messages.create(
                model=self.model_name,
                max_tokens=10,
                messages=[{"role": "user", "content": "Hi"}]
            )
            return True
            
        except Exception:
            return False
    
    @staticmethod
    def list_models():
        """List all available Claude models"""
        return MODELS
    
    @staticmethod
    def get_model_info(model_name: str):
        """Get detailed information about a specific model"""
        return MODELS.get(model_name, {})
    
    @staticmethod
    def recommend_model(use_case: str):
        """Recommend a model based on use case"""
        recommendations = {
            'complex_analysis': 'claude-3-opus-20240229',
            'coding': 'claude-3-5-sonnet-20241022', 
            'general': 'claude-3-sonnet-20240229',
            'fast': 'claude-3-haiku-20240307',
            'cost_effective': 'claude-3-haiku-20240307',
            'reasoning': 'claude-3-5-sonnet-20241022'
        }
        return recommendations.get(use_case.lower(), 'claude-3-5-sonnet-20241022')