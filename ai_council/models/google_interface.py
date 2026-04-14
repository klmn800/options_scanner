"""
Google (Gemini) model interface
"""
import os
import json
from typing import List, Dict, Optional
from .base_model import BaseModelInterface

# AVAILABLE MODELS - Copy these exact strings to personality files
MODELS = {
    # Gemini 1.5 Series
    "gemini-1.5-pro": {
        "name": "Gemini 1.5 Pro",
        "context": 2000000,  # 2M tokens!
        "strengths": ["massive context", "multimodal", "reasoning", "code"],
        "cost_per_1k_tokens": 0.00125,
        "description": "Most capable Gemini with massive context window"
    },
    "gemini-1.5-flash": {
        "name": "Gemini 1.5 Flash",
        "context": 1000000,  # 1M tokens
        "strengths": ["speed", "large context", "multimodal", "cost-effective"],
        "cost_per_1k_tokens": 0.000075,
        "description": "Fast Gemini with large context, great value"
    },
    "gemini-1.5-flash-8b": {
        "name": "Gemini 1.5 Flash 8B",
        "context": 1000000,
        "strengths": ["speed", "efficiency", "cost-effective"],
        "cost_per_1k_tokens": 0.0000375,
        "description": "Smallest and most efficient Gemini 1.5"
    },
    
    # Gemini 1.0 Series (Legacy)
    "gemini-1.0-pro": {
        "name": "Gemini 1.0 Pro",
        "context": 32768,
        "strengths": ["general tasks", "reasoning"],
        "cost_per_1k_tokens": 0.0005,
        "description": "Original Gemini Pro model"
    },
    "gemini-1.0-pro-vision": {
        "name": "Gemini 1.0 Pro Vision",
        "context": 16384,
        "strengths": ["vision", "multimodal", "image analysis"],
        "cost_per_1k_tokens": 0.0005,
        "description": "Gemini with vision capabilities"
    }
}

class GoogleInterface(BaseModelInterface):
    """Interface for Google's Gemini models"""
    
    def _initialize_client(self):
        """Initialize Google AI client"""
        try:
            import google.generativeai as genai
            
            # Try to get API key from various sources
            api_key = self._get_api_key()
            if not api_key:
                raise ValueError("Google AI API key not found")
            
            genai.configure(api_key=api_key)
            self.client = genai
            
            # Initialize the model
            self.model = genai.GenerativeModel(self.model_name)
            
        except ImportError:
            raise ImportError("google-generativeai package not installed. Run: pip install google-generativeai")
        except Exception as e:
            raise Exception(f"Failed to initialize Google AI client: {e}")
    
    def _get_api_key(self):
        """Get Google AI API key from config or environment"""
        # Try config.json first
        try:
            config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'config.json')
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    google_config = config.get('google_ai', {})
                    if google_config.get('api_key'):
                        return google_config['api_key']
        except:
            pass
        
        # Try environment variable
        return os.environ.get('GOOGLE_AI_API_KEY') or os.environ.get('GEMINI_API_KEY')
    
    def query(self, 
              query: str, 
              system_prompt: str = "", 
              temperature: float = 0.7,
              max_tokens: int = 2000,
              conversation_history: Optional[List[Dict]] = None) -> str:
        """Send query to Gemini and return response"""
        
        if not self.client or not self.model:
            raise Exception("Google AI client not initialized")
        
        try:
            # Gemini handles system prompts and conversation differently
            # Build the full prompt with system prompt and history
            full_prompt = ""
            
            if system_prompt:
                full_prompt += f"Instructions: {system_prompt}\n\n"
            
            # Add conversation history
            if conversation_history:
                full_prompt += "Previous conversation:\n"
                for exchange in conversation_history:
                    full_prompt += f"User: {exchange.get('query', '')}\n"
                    full_prompt += f"Assistant: {exchange.get('response', '')}\n\n"
            
            # Add current query
            full_prompt += f"Current request: {query}"
            
            # Configure generation parameters
            generation_config = self.client.types.GenerationConfig(
                temperature=temperature,
                max_output_tokens=max_tokens,
            )
            
            # Send request to Gemini
            response = self.model.generate_content(
                full_prompt,
                generation_config=generation_config
            )
            
            return response.text
            
        except Exception as e:
            return f"❌ Google AI API Error: {str(e)}"
    
    def is_available(self) -> bool:
        """Check if Gemini is available"""
        try:
            if not self.client or not self.model:
                return False
            
            # Test with a simple query
            test_response = self.model.generate_content("Hi")
            return bool(test_response.text)
            
        except Exception:
            return False
    
    @staticmethod
    def list_models():
        """List all available Gemini models"""
        return MODELS
    
    @staticmethod
    def get_model_info(model_name: str):
        """Get detailed information about a specific model"""
        return MODELS.get(model_name, {})
    
    @staticmethod
    def recommend_model(use_case: str):
        """Recommend a model based on use case"""
        recommendations = {
            'long_context': 'gemini-1.5-pro',
            'fast': 'gemini-1.5-flash',
            'cost_effective': 'gemini-1.5-flash-8b',
            'multimodal': 'gemini-1.5-pro',
            'vision': 'gemini-1.0-pro-vision',
            'general': 'gemini-1.5-flash',
            'reasoning': 'gemini-1.5-pro'
        }
        return recommendations.get(use_case.lower(), 'gemini-1.5-flash')