"""
Chat Room Personality Loader - Working Version
============================================

Simplified version for testing AI Council personality integration.
"""

import sys
import os
import logging

# Configure logging for personality system
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add parent directory to path to import ai_council
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

try:
    logger.debug("PERSONALITY_LOADER: Attempting to import AI Council")
    from ai_council.base_personality import BasePersonality
    from ai_council import get_personality, list_personalities
    AI_COUNCIL_AVAILABLE = True
    logger.info("PERSONALITY_LOADER: AI Council imported successfully")
    print("OK: AI Council imported successfully")
except ImportError as e:
    logger.error(f"PERSONALITY_LOADER: Could not import AI Council: {e}")
    print(f"ERROR: Could not import AI Council: {e}")
    AI_COUNCIL_AVAILABLE = False

def get_available_personalities():
    """Get list of available personality code names"""
    logger.debug("PERSONALITY_LOADER: Getting available personalities")
    
    if not AI_COUNCIL_AVAILABLE:
        logger.warning("PERSONALITY_LOADER: AI Council not available")
        return []
    
    try:
        logger.debug("PERSONALITY_LOADER: Calling list_personalities()")
        personalities = list_personalities()
        # Filter out oracle_data personality - it's accessed via /oracle command instead
        code_names = [p['code_name'] for p in personalities if p['code_name'] != 'oracle_data']
        logger.info(f"PERSONALITY_LOADER: Found {len(code_names)} available personalities: {code_names}")
        return code_names
    except Exception as e:
        logger.error(f"PERSONALITY_LOADER: Could not list personalities: {e}")
        print(f"ERROR: Could not list personalities: {e}")
        return []

def get_personality_info(code_name):
    """Get personality information"""
    if not AI_COUNCIL_AVAILABLE:
        return None
        
    try:
        personalities = list_personalities()
        for p in personalities:
            if p['code_name'] == code_name:
                return p
        return None
    except Exception as e:
        print(f"ERROR: Could not get personality info: {e}")
        return None

def load_personality_for_chat(code_name):
    """Load a personality for chat use"""
    logger.debug(f"PERSONALITY_LOADER: Loading personality '{code_name}' for chat")
    
    if not AI_COUNCIL_AVAILABLE:
        logger.warning(f"PERSONALITY_LOADER: AI Council not available, cannot load '{code_name}'")
        return None
        
    try:
        logger.debug(f"PERSONALITY_LOADER: Calling get_personality('{code_name}')")
        base_personality = get_personality(code_name)
        
        if base_personality:
            logger.info(f"PERSONALITY_LOADER: Successfully loaded base personality: {base_personality.name}")
            logger.debug(f"PERSONALITY_LOADER: Creating SimpleChatPersonality wrapper")
            
            chat_personality = SimpleChatPersonality(base_personality)
            logger.info(f"PERSONALITY_LOADER: Created chat personality for {chat_personality.display_name}")
            
            print(f"OK: Loaded personality for chat: {base_personality.name}")
            return chat_personality
        else:
            logger.error(f"PERSONALITY_LOADER: get_personality returned None for '{code_name}'")
            print(f"ERROR: Could not get personality instance for {code_name}")
            return None
    except Exception as e:
        logger.error(f"PERSONALITY_LOADER: Failed to load personality '{code_name}': {e}")
        import traceback
        logger.debug(f"PERSONALITY_LOADER: Exception traceback: {traceback.format_exc()}")
        print(f"ERROR: Failed to load personality '{code_name}': {e}")
        return None

class SimpleChatPersonality:
    """Simplified chat adapter for AI personalities"""
    
    def __init__(self, base_personality):
        logger.debug(f"CHAT_PERSONALITY: Initializing wrapper for {base_personality.name}")
        
        self.base = base_personality
        self.display_name = base_personality.name
        self.code_name = base_personality.code_name
        self.specialty = base_personality.specialty
        self.primary_model = base_personality.primary_model
        self.avatar = self._get_avatar()
        self.message_color = self._get_message_color()
        
        logger.info(f"CHAT_PERSONALITY: Initialized {self.display_name} ({self.code_name}) - Model: {self.primary_model}")
        logger.debug(f"CHAT_PERSONALITY: Avatar: {self.avatar}, Color: {self.message_color}")
    
    def _get_avatar(self):
        """Get avatar for personality"""
        avatar_map = {
            'demo_guru': 'G',
            'data_aware_template': 'D', 
            'oracle_data': 'O',
            'personality_template': 'P'
        }
        return avatar_map.get(self.code_name, '?')
    
    def _get_message_color(self):
        """Get color for chat messages"""
        color_map = {
            'demo_guru': '#4CAF50',
            'data_aware_template': '#2196F3', 
            'oracle_data': '#FF9800',
            'personality_template': '#9C27B0'
        }
        return color_map.get(self.code_name, '#757575')
    
    def ask_for_chat(self, message):
        """Get response from personality for chat"""
        logger.debug(f"CHAT_PERSONALITY: {self.display_name} received chat message (length: {len(message)} chars)")
        # Safe logging without external dependency
        safe_message = message[:100] + "..." if len(message) > 100 else message
        logger.debug(f"CHAT_PERSONALITY: Message preview: '{safe_message}'")
        
        try:
            # Add simple chat context
            chat_context = f"You are in a chat room discussion. Please provide a concise response to: {message}"
            logger.debug(f"CHAT_PERSONALITY: Calling base.ask() for {self.display_name}")
            logger.debug(f"CHAT_PERSONALITY: Using model: {self.primary_model}")
            
            response = self.base.ask(chat_context)
            
            if response:
                logger.info(f"CHAT_PERSONALITY: {self.display_name} generated response (length: {len(response)} chars)")
                safe_response = response[:100] + "..." if len(response) > 100 else response
                logger.debug(f"CHAT_PERSONALITY: Response preview: '{safe_response}'")
                return response
            else:
                logger.warning(f"CHAT_PERSONALITY: {self.display_name} returned empty response")
                return "I'm not sure how to respond to that."
                
        except Exception as e:
            logger.error(f"CHAT_PERSONALITY: Error getting response from {self.display_name}: {e}")
            import traceback
            logger.debug(f"CHAT_PERSONALITY: Exception traceback: {traceback.format_exc()}")
            print(f"ERROR: Getting response from {self.code_name}: {e}")
            return f"Sorry, I'm having trouble responding right now. ({str(e)[:50]}...)"

def list_and_load_demo_personalities():
    """List available personalities and load demo for testing"""
    print("\nAvailable AI Council Personalities:")
    print("=" * 50)
    
    available = get_available_personalities()
    if not available:
        print("ERROR: No personalities found")
        return None
    
    for code_name in available:
        info = get_personality_info(code_name)
        if info:
            print(f"* {code_name}")
            print(f"   Name: {info.get('name', 'Unknown')}")
            print(f"   Specialty: {info.get('specialty', 'Unknown')}")
            print(f"   Model: {info.get('primary_model', 'Unknown')}")
            print()
    
    print(f"Found {len(available)} personalities available")
    
    # Try to load demo_guru for testing
    if 'demo_guru' in available:
        print("\nLoading demo_guru for testing...")
        demo = load_personality_for_chat('demo_guru')
        if demo:
            print(f"Loaded: {demo.display_name}")
            return demo
    
    return None

if __name__ == "__main__":
    print("Testing Chat Personality System")
    print("=" * 40)
    
    demo = list_and_load_demo_personalities()
    
    if demo:
        print(f"\nTesting chat with {demo.display_name}:")
        test_response = demo.ask_for_chat("Hello, can you introduce yourself briefly?")
        print(f"Response: {test_response[:100]}...")
    else:
        print("No demo personality available for testing")