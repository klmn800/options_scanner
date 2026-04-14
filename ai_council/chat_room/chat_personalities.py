"""
Chat Room Personality Loader
============================

Bridge between the AI Council personality system and the chat room.
Loads personalities and formats their responses for chat display.

Phase 2: Basic personality integration with sequential responses
"""

import sys
import os
import asyncio
import threading
import time
from datetime import datetime
from typing import Dict, List, Optional, Any

# Add parent directory to path to import ai_council
# From chat_room -> ai_council -> options_scanner (project root)
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

try:
    from ai_council.base_personality import BasePersonality
    from ai_council import get_personality, list_personalities
    AI_COUNCIL_AVAILABLE = True
except ImportError as e:
    print(f"ERROR Could not import AI Council: {e}")
    print("Make sure ai_council module is available")
    BasePersonality = None
    get_personality = None
    list_personalities = None
    AI_COUNCIL_AVAILABLE = False

class ChatPersonalityManager:
    """Manages AI personalities in the chat room context"""
    
    def __init__(self):
        self.active_personalities = {}  # code_name -> ChatPersonality
        self.response_queue = []
        self.is_processing = False
        
    def load_personality(self, code_name: str) -> Optional['ChatPersonality']:
        """Load a personality directly from ai_council/personalities/ for chat use"""
        try:
            # Get personality from existing AI Council personalities directory
            base_personality = get_personality(code_name)
            
            # Wrap in chat-specific adapter (not a new personality, just chat formatting)
            chat_personality = ChatPersonality(base_personality)
            
            self.active_personalities[code_name] = chat_personality
            print(f"OK Loaded personality for chat: {chat_personality.display_name}")
            print(f"    Model: {chat_personality.primary_model}")
            print(f"    Specialty: {chat_personality.specialty}")
            
            return chat_personality
            
        except Exception as e:
            print(f"ERROR Failed to load personality '{code_name}': {e}")
            print(f"    Available personalities: {self.get_available_personalities()}")
            return None
    
    def get_available_personalities(self) -> List[str]:
        """Get list of available personalities from ai_council/personalities/"""
        try:
            personalities_info = list_personalities()
            return [p['code_name'] for p in personalities_info]
        except Exception as e:
            print(f"ERROR Could not list personalities: {e}")
            return []
    
    def get_personality_info(self, code_name: str) -> Optional[Dict[str, Any]]:
        """Get detailed info about a personality before loading"""
        try:
            personalities_info = list_personalities()
            for p in personalities_info:
                if p['code_name'] == code_name:
                    return p
            return None
        except Exception as e:
            print(f"ERROR Could not get personality info: {e}")
            return None
    
    def get_personality(self, code_name: str) -> Optional['ChatPersonality']:
        """Get an active personality"""
        return self.active_personalities.get(code_name)
    
    def list_active_personalities(self) -> List[Dict[str, Any]]:
        """Get list of active personalities with their info"""
        return [
            {
                'code_name': code_name,
                'display_name': personality.display_name,
                'specialty': personality.specialty,
                'avatar': personality.avatar,
                'color': personality.message_color,
                'model': personality.primary_model
            }
            for code_name, personality in self.active_personalities.items()
        ]
    
    def remove_personality(self, code_name: str) -> bool:
        """Remove a personality from active chat"""
        if code_name in self.active_personalities:
            personality = self.active_personalities.pop(code_name)
            print(f"🗑️ Removed personality: {personality.display_name}")
            return True
        return False
    
    def generate_responses(self, user_message: str, message_history: List[Dict], 
                          room_id: str) -> List[Dict[str, Any]]:
        """
        Generate responses from all active personalities
        Returns list of response objects for the chat room
        """
        responses = []
        
        for code_name, personality in self.active_personalities.items():
            try:
                # Build context from message history
                context = self._build_conversation_context(message_history)
                
                # Get response from personality
                response_text = personality.ask_for_chat(user_message, context)
                
                if response_text:
                    responses.append({
                        'sender': personality.display_name,
                        'sender_type': 'ai',
                        'sender_id': code_name,
                        'message': response_text,
                        'room_id': room_id,
                        'avatar': personality.avatar,
                        'color': personality.message_color,
                        'model': personality.primary_model,
                        'specialty': personality.specialty
                    })
                    
            except Exception as e:
                print(f"ERROR getting response from {code_name}: {e}")
                # Add error message to chat
                responses.append({
                    'sender': personality.display_name if code_name in self.active_personalities else code_name,
                    'sender_type': 'ai_error',
                    'sender_id': code_name,
                    'message': f"Sorry, I encountered an error: {str(e)[:100]}",
                    'room_id': room_id,
                    'avatar': 'X',
                    'color': '#ef4444',
                    'model': 'error',
                    'specialty': 'Error'
                })
        
        return responses
    
    def _build_conversation_context(self, message_history: List[Dict]) -> str:
        """Build conversation context from recent messages"""
        if not message_history:
            return ""
        
        # Get last 10 messages for context
        recent_messages = message_history[-10:]
        
        context_lines = ["Recent conversation:"]
        for msg in recent_messages:
            sender = msg.get('sender', 'Unknown')
            message = msg.get('message', '')
            context_lines.append(f"{sender}: {message}")
        
        return "\n".join(context_lines)


if AI_COUNCIL_AVAILABLE:
    class ChatPersonality:
        """
        Chat adapter for existing AI Council personalities.
        
        This doesn't create new personalities - it just adapts existing ones
        from ai_council/personalities/ for chat room display and interaction.
        """
        
        def __init__(self, base_personality):
            # Reference to the actual personality (not a copy)
        self.base = base_personality
        
        # Use the personality's existing properties
        self.code_name = base_personality.code_name
        self.display_name = base_personality.name
        self.specialty = base_personality.specialty
        self.primary_model = base_personality.primary_model
        self.signature_phrases = getattr(base_personality, 'signature_phrases', [])
        
        # Chat-specific visual adaptations (these don't change the personality)
        self.avatar = self._get_avatar()
        self.message_color = self._get_message_color()
        
        # Chat session tracking (separate from personality's main conversation history)
        self.chat_session_history = []
        
        # Memory bank system - persistent storage for personality insights
        self.memory_file = self._setup_memory_bank()
        
        # Load existing memories on initialization
        self._load_memories()
    
    def ask_for_chat(self, message: str, context: str = "") -> str:
        """
        Get a chat-formatted response from the actual personality.
        
        This uses the personality's existing ask() method but adapts the 
        response for real-time chat display.
        """
        try:
            # Build chat-appropriate context
            chat_context = self._build_chat_context(context)
            
            # Use the personality's actual ask() method
            # This preserves all their unique logic, system prompts, etc.
            response = self.base.ask(message, chat_context)
            
            # Only format for chat display (don't change the personality's response logic)
            formatted_response = self._format_for_chat(response)
            
            # Track this chat session (separate from personality's main history)
            self.chat_session_history.append({
                'timestamp': datetime.now().isoformat(),
                'user_message': message,
                'response': formatted_response,
                'context': context
            })
            
            # Keep chat session history manageable
            if len(self.chat_session_history) > 20:
                self.chat_session_history = self.chat_session_history[-20:]
            
            return formatted_response
            
        except Exception as e:
            # Graceful error handling for chat context
            return f"I'm having trouble responding right now: {str(e)[:100]}..."
    
    def _build_chat_context(self, conversation_context: str) -> str:
        """Build context specific to chat room environment"""
        chat_instructions = f"""
You are participating in a live chat room discussion. Keep your responses:
- Conversational and natural (like you're chatting with friends)
- Concise but informative (2-3 sentences typically)
- Engaging and interactive (feel free to ask questions back)
- Appropriate for real-time chat (not essay-length responses)

{conversation_context}
"""
        return chat_instructions
    
    def _format_for_chat(self, response: str) -> str:
        """Format AI response for chat room display"""
        if not response:
            return "I'm not sure how to respond to that."
        
        # Remove excessive markdown formatting
        formatted = response.replace('**', '').replace('*', '')
        
        # Remove emoji signatures that might be duplicated
        if '📊' in formatted and formatted.count('📊') > 1:
            # Keep only the first instance
            parts = formatted.split('📊')
            formatted = parts[0] + '📊' + '📊'.join(parts[1:-1])
        
        # Limit length for chat (max ~300 characters for readability)
        if len(formatted) > 300:
            # Find a good breaking point
            truncate_at = 280
            if '. ' in formatted[truncate_at:]:
                # Find next sentence boundary
                next_period = formatted.find('. ', truncate_at)
                if next_period != -1 and next_period < 350:
                    formatted = formatted[:next_period + 1]
                else:
                    formatted = formatted[:truncate_at] + "..."
            else:
                formatted = formatted[:truncate_at] + "..."
        
        return formatted.strip()
    
    def _get_avatar(self) -> str:
        """Get emoji avatar for this personality"""
        # Map personality types to avatars
        avatar_map = {
            'risk': '⚠️',
            'hawk': '🦅', 
            'options': '📈',
            'guru': 'G',
            'trader': '💹',
            'analyst': '📊',
            'data': '💾',
            'oracle': '🔮',
            'demo': '🎯'
        }
        
        code_lower = self.code_name.lower()
        
        # Check for keywords in code name
        for keyword, emoji in avatar_map.items():
            if keyword in code_lower:
                return emoji
        
        # Check specialty for clues
        specialty_lower = self.specialty.lower()
        if 'risk' in specialty_lower:
            return '⚠️'
        elif 'option' in specialty_lower:
            return '📈'
        elif 'data' in specialty_lower:
            return '📊'
        elif 'trading' in specialty_lower:
            return '💹'
        
        # Default avatar
        return '🤖'
    
    def _get_message_color(self) -> str:
        """Get color for this personality's messages"""
        # Color map for different personality types
        color_map = {
            'risk': '#ef4444',      # Red for risk management
            'options': '#8b5cf6',   # Purple for options
            'data': '#06b6d4',      # Cyan for data analysis
            'trader': '#f59e0b',    # Orange for trading
            'analyst': '#10b981',   # Green for analysis
            'guru': '#6366f1',      # Indigo for gurus
            'oracle': '#ec4899',    # Pink for oracle
            'demo': '#3b82f6'       # Blue for demo
        }
        
        code_lower = self.code_name.lower()
        
        # Check for keywords
        for keyword, color in color_map.items():
            if keyword in code_lower:
                return color
        
        # Check specialty
        specialty_lower = self.specialty.lower()
        if 'risk' in specialty_lower:
            return '#ef4444'
        elif 'option' in specialty_lower:
            return '#8b5cf6'  
        elif 'data' in specialty_lower:
            return '#06b6d4'
        elif 'trading' in specialty_lower:
            return '#f59e0b'
        
        # Default color (neutral AI)
        return '#6b7280'
    
    def get_info(self) -> Dict[str, Any]:
        """Get personality info for display"""
        return {
            'code_name': self.code_name,
            'display_name': self.display_name,
            'specialty': self.specialty,
            'avatar': self.avatar,
            'color': self.message_color,
            'model': self.primary_model,
            'chat_messages': len(self.chat_session_history),
            'memory_file': self.memory_file,
            'memory_entries': getattr(self, 'memory_count', 0)
        }
    
    def _setup_memory_bank(self) -> str:
        """Set up persistent memory file for this personality"""
        # Create memories directory
        memory_dir = os.path.join(os.path.dirname(__file__), 'memories')
        os.makedirs(memory_dir, exist_ok=True)
        
        # Memory file named after the personality
        memory_file = os.path.join(memory_dir, f"{self.code_name}_memory.md")
        
        # Create initial memory file if it doesn't exist
        if not os.path.exists(memory_file):
            with open(memory_file, 'w', encoding='utf-8') as f:
                f.write(f"# {self.display_name} - Memory Bank\n\n")
                f.write(f"**Personality**: {self.display_name}  \n")
                f.write(f"**Specialty**: {self.specialty}  \n")
                f.write(f"**Model**: {self.primary_model}  \n")
                f.write(f"**Created**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  \n\n")
                f.write("## 📋 Personal Insights & Journal\n\n")
                f.write("*This is my personal memory bank where I record insights, observations, and reflections from conversations.*\n\n")
                f.write("---\n\n")
        
        return memory_file
    
    def _load_memories(self):
        """Load existing memories to provide context awareness"""
        try:
            if os.path.exists(self.memory_file):
                with open(self.memory_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    # Count memory entries (lines starting with "###")
                    self.memory_count = content.count('### ')
                    # Store recent memories for context (last 1000 chars)
                    self.recent_memories = content[-1000:] if len(content) > 1000 else content
            else:
                self.memory_count = 0
                self.recent_memories = ""
        except Exception as e:
            print(f"⚠️ Could not load memories for {self.code_name}: {e}")
            self.memory_count = 0
            self.recent_memories = ""
    
    def log_insight(self, insight_type: str, content: str, context: str = ""):
        """Log an insight or observation to the memory bank"""
        try:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            with open(self.memory_file, 'a', encoding='utf-8') as f:
                f.write(f"### {insight_type} - {timestamp}\n\n")
                f.write(f"{content}\n\n")
                if context:
                    f.write(f"*Context: {context}*\n\n")
                f.write("---\n\n")
            
            self.memory_count += 1
            self._load_memories()  # Refresh recent memories
            
        except Exception as e:
            print(f"⚠️ Could not log insight for {self.code_name}: {e}")
    
    def add_conversation_memory(self, user_message: str, my_response: str, notable_aspects: List[str] = None):
        """Add a notable conversation to memory bank"""
        if not notable_aspects:
            # Auto-detect if this conversation might be worth remembering
            if (len(user_message) > 50 or len(my_response) > 100 or 
                any(word in user_message.lower() for word in ['help', 'advice', 'strategy', 'decision', 'problem'])):
                notable_aspects = ["Significant conversation"]
        
        if notable_aspects:
            insight_content = f"**User asked**: {user_message[:200]}{'...' if len(user_message) > 200 else ''}\n\n"
            insight_content += f"**My response approach**: {my_response[:300]}{'...' if len(my_response) > 300 else ''}\n\n"
            insight_content += f"**Notable aspects**: {', '.join(notable_aspects)}"
            
            self.log_insight("Conversation", insight_content, "Chat room discussion")
    
    def reflect_on_session(self, session_summary: str):
        """Record reflections on a chat session"""
        self.log_insight("Session Reflection", session_summary, "End of chat session")
    
    def get_memory_context(self, max_chars: int = 500) -> str:
        """Get recent memory context to inform responses"""
        if hasattr(self, 'recent_memories') and self.recent_memories:
            # Extract just the content, not the markdown formatting
            memory_lines = []
            for line in self.recent_memories.split('\n'):
                if line.strip() and not line.startswith('#') and not line.startswith('*') and not line.startswith('---'):
                    memory_lines.append(line.strip())
            
            memory_text = ' '.join(memory_lines)
            if len(memory_text) > max_chars:
                memory_text = memory_text[:max_chars] + "..."
            
            return f"My recent memories/insights: {memory_text}" if memory_text else ""
        return ""


# Global personality manager instance
personality_manager = ChatPersonalityManager()

# Convenience functions for the chat server
def load_personality_for_chat(code_name: str) -> Optional[ChatPersonality]:
    """Load a personality from ai_council/personalities/ for chat use"""
    return personality_manager.load_personality(code_name)

def get_available_personalities() -> List[str]:
    """Get list of all available personalities from ai_council/personalities/"""
    return personality_manager.get_available_personalities()

def get_personality_info(code_name: str) -> Optional[Dict[str, Any]]:
    """Get info about a personality before loading it"""
    return personality_manager.get_personality_info(code_name)

def get_active_chat_personalities() -> List[Dict[str, Any]]:
    """Get list of currently active chat personalities"""
    return personality_manager.list_active_personalities()

def generate_ai_responses(user_message: str, message_history: List[Dict], room_id: str) -> List[Dict[str, Any]]:
    """Generate responses from all active AI personalities"""
    return personality_manager.generate_responses(user_message, message_history, room_id)

def remove_chat_personality(code_name: str) -> bool:
    """Remove a personality from active chat"""
    return personality_manager.remove_personality(code_name)

def list_and_load_demo_personalities():
    """Utility function to see available personalities and load a couple for testing"""
    print("\nAvailable AI Council Personalities:")
    print("=" * 50)
    
    available = get_available_personalities()
    if not available:
        print("ERROR No personalities found in ai_council/personalities/")
        return
    
    for code_name in available:
        info = get_personality_info(code_name)
        if info:
            print(f"* {code_name}")
            print(f"   Name: {info.get('name', 'Unknown')}")
            print(f"   Specialty: {info.get('specialty', 'Unknown')}")
            print(f"   Model: {info.get('primary_model', 'Unknown')}")
            print()
    
    print("To load for chat: load_personality_for_chat('code_name')")
    print(f"Found {len(available)} personalities available")
    
    # Try to load a demo personality if available
    if 'demo_guru' in available:
        print("\n Loading demo_guru for testing...")
        demo = load_personality_for_chat('demo_guru')
        if demo:
            print(f"Loaded: {demo.display_name}")
            return demo
    
    return None

else:
    # Fallback classes when AI Council is not available
    class ChatPersonality:
        """Stub class when AI Council is not available"""
        def __init__(self, base_personality=None):
            self.display_name = "Unavailable"
            self.code_name = "unavailable"
            self.specialty = "System Error"
        
        def ask_for_chat(self, message: str) -> str:
            return "AI Council system is not available."