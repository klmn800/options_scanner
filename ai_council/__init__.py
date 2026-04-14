"""
AI Council - Specialized AI Personalities for Trading & Analysis
==============================================================

A framework for creating and managing specialized AI personalities
with distinct expertise, behaviors, and model preferences.

Usage:
    # Direct personality usage
    from ai_council import get_personality
    guru = get_personality('options_guru')
    response = guru.ask("What's your take on NVDA vol?")
    
    # Full council discussion  
    from ai_council.council import AICouncil
    council = AICouncil()
    discussion = council.discuss("Should I hedge my gamma exposure?")
"""

from .base_personality import BasePersonality
from .council import AICouncil

def get_personality(code_name):
    """Get a personality instance by code name"""
    # Dynamic import based on code_name
    try:
        module = __import__(f"ai_council.personalities.{code_name}", fromlist=[code_name])
        # Find the personality class in the module
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (isinstance(attr, type) and 
                issubclass(attr, BasePersonality) and 
                attr != BasePersonality):
                return attr()
    except ImportError:
        raise ValueError(f"Personality '{code_name}' not found")
    
    raise ValueError(f"No personality class found in {code_name}.py")

def list_personalities():
    """List all available personalities"""
    import os
    personalities = []
    personality_dir = os.path.join(os.path.dirname(__file__), 'personalities')
    
    for filename in os.listdir(personality_dir):
        if filename.endswith('.py') and not filename.startswith('_'):
            code_name = filename[:-3]  # Remove .py extension
            try:
                personality = get_personality(code_name)
                personalities.append({
                    'code_name': code_name,
                    'name': personality.name,
                    'specialty': personality.specialty,
                    'primary_model': personality.primary_model
                })
            except:
                pass  # Skip invalid personality files
    
    return personalities