"""
Base model interface that all AI model interfaces inherit from
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

class BaseModelInterface(ABC):
    """Base class for all AI model interfaces"""
    
    def __init__(self, model_name: str):
        self.model_name = model_name
        self.client = None
        self._initialize_client()
    
    @abstractmethod
    def _initialize_client(self):
        """Initialize the API client for this model provider"""
        pass
    
    @abstractmethod
    def query(self, 
              query: str, 
              system_prompt: str = "", 
              temperature: float = 0.7,
              max_tokens: int = 2000,
              conversation_history: Optional[List[Dict]] = None) -> str:
        """
        Send a query to the model and return the response
        
        Args:
            query: The user's question/prompt
            system_prompt: System prompt defining the AI's role/personality
            temperature: Creativity/randomness (0.0-1.0)
            max_tokens: Maximum response length
            conversation_history: Previous conversation for context
            
        Returns:
            The model's response as a string
        """
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if this model is currently available/accessible"""
        pass
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get information about this model"""
        return {
            'model_name': self.model_name,
            'provider': self.__class__.__name__.replace('Interface', '').lower(),
            'available': self.is_available()
        }
    
    def format_conversation_history(self, history: List[Dict]) -> List[Dict]:
        """Convert internal conversation history to model-specific format"""
        if not history:
            return []
        
        formatted = []
        for exchange in history:
            formatted.append({
                'role': 'user',
                'content': exchange.get('query', '')
            })
            formatted.append({
                'role': 'assistant', 
                'content': exchange.get('response', '')
            })
        
        return formatted