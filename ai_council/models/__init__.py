"""
Model interfaces for AI Council personalities
"""

from .base_model import BaseModelInterface

# Available model types
MODEL_TYPES = {
    'anthropic': ['claude'],
    'openai': ['gpt'],
    'ollama': ['llama', 'mistral', 'phi', 'gemma', 'qwen', 'codellama', 'deepseek'],
    'google': ['gemini'],
    'xai': ['grok']
}

def detect_model_type(model_name):
    """Detect which interface to use based on model name"""
    model_lower = model_name.lower()
    
    for provider, prefixes in MODEL_TYPES.items():
        for prefix in prefixes:
            if prefix in model_lower:
                return provider
    
    raise ValueError(f"Unknown model type for: {model_name}")