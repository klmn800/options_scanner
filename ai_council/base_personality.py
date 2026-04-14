"""
Base personality class that all AI Council members inherit from
"""
from abc import ABC, abstractmethod
from datetime import datetime
import json
import sys
import os

class BasePersonality(ABC):
    """Base class for AI Council personalities"""
    
    # PERSONALITY DEFINITION (Override these in child classes)
    name = "Unknown Assistant"  # Full name/title
    code_name = "unknown"  # Short identifier for CLI usage
    specialty = "General Advisor"
    
    # MODEL CONFIGURATION (Copy model names from interface files)
    primary_model = None  # e.g., "claude-3-5-sonnet-20241022"
    backup_model = None   # e.g., "gpt-4o"
    
    # PERSONALITY TRAITS
    temperature = 0.7  # 0.0 = focused, 1.0 = creative
    max_tokens = 2000
    
    # SYSTEM PROMPT (The heart of the personality)
    system_prompt = "You are a helpful assistant."
    
    # CONVERSATION STYLE
    conversation_style = "professional"
    signature_phrases = []
    
    # OPTIONAL PERSONALITY ENRICHMENT
    backstory = ""
    expertise_areas = []
    behavioral_traits = []
    decision_framework = ""
    
    # ORACLE DATABASE ACCESS (Optional)
    enable_oracle_access = False  # Set to True to enable database queries
    
    def __init__(self):
        """Initialize personality with model interface"""
        self.model_interface = None
        self.conversation_history = []
        self._setup_model()
    
    def _setup_model(self):
        """Setup primary or backup model interface"""
        if not self.primary_model:
            raise ValueError(f"Personality {self.name} must specify primary_model")
        
        # Import the appropriate model interface based on model name
        try:
            if "claude" in self.primary_model.lower():
                from .models.anthropic_interface import AnthropicInterface
                self.model_interface = AnthropicInterface(self.primary_model)
            elif "gpt" in self.primary_model.lower():
                from .models.openai_interface import OpenAIInterface
                self.model_interface = OpenAIInterface(self.primary_model)
            elif any(model_type in self.primary_model.lower() for model_type in ["llama", "mistral", "phi", "gemma", "qwen", "codellama", "deepseek", "gpt-oss"]):
                from .models.ollama_interface import OllamaInterface
                self.model_interface = OllamaInterface(self.primary_model)
            elif "gemini" in self.primary_model.lower():
                from .models.google_interface import GoogleInterface
                self.model_interface = GoogleInterface(self.primary_model)
            elif "grok" in self.primary_model.lower():
                from .models.xai_interface import XAIInterface
                self.model_interface = XAIInterface(self.primary_model)
            else:
                raise ValueError(f"Unknown model type for {self.primary_model}")
                
        except Exception as e:
            print(f"WARNING: Primary model {self.primary_model} failed to initialize: {e}")
            if self.backup_model:
                print(f"Trying backup model: {self.backup_model}")
                self._setup_backup_model()
            else:
                raise ValueError(f"No working model available for {self.name}")
    
    def _setup_backup_model(self):
        """Setup backup model if primary fails"""
        # Similar logic for backup model
        # TODO: Implement backup model switching
        pass
    
    def pre_process_query(self, query):
        """Override to modify query before sending to model"""
        return query
    
    def post_process_response(self, response):
        """Override to process response before returning"""
        return response
    
    def ask(self, query, context=None):
        """Main interface for asking questions"""
        if not self.model_interface:
            raise ValueError(f"Model interface not initialized for {self.name}")
        
        # Pre-process the query (personality can modify)
        processed_query = self.pre_process_query(query)
        
        # Add Oracle database context if enabled
        if self.enable_oracle_access:
            try:
                oracle_context = self._get_oracle_context(query)
                if oracle_context:
                    if context:
                        context = f"{context}\n\nDatabase Context:\n{oracle_context}"
                    else:
                        context = f"Database Context:\n{oracle_context}"
            except Exception as e:
                print(f"⚠️ Oracle access error for {self.name}: {e}")
        
        # Add context if provided
        if context:
            processed_query = f"Context: {context}\n\nQuestion: {processed_query}"
        
        try:
            # Send to model interface
            raw_response = self.model_interface.query(
                query=processed_query,
                system_prompt=self.system_prompt,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                conversation_history=self.conversation_history
            )
            
            # Post-process the response (personality can modify)
            final_response = self.post_process_response(raw_response)
            
            # Update conversation history
            self.conversation_history.append({
                'timestamp': datetime.now().isoformat(),
                'query': processed_query,
                'response': final_response
            })
            
            # Keep history manageable (last 10 exchanges)
            if len(self.conversation_history) > 10:
                self.conversation_history = self.conversation_history[-10:]
            
            return final_response
            
        except Exception as e:
            return f"❌ Error from {self.name}: {str(e)}"
    
    def interactive_mode(self):
        """Start interactive conversation mode"""
        print(f"\n{'='*60}")
        print(f"🎭 {self.name} - {self.specialty}")
        print(f"{'='*60}")
        print(f"Model: {self.primary_model}")
        if self.backstory:
            print(f"Background: {self.backstory[:100]}...")
        print(f"Type 'quit' to exit, 'info' for personality details")
        print(f"{'='*60}\n")
        
        while True:
            try:
                user_input = input(f"\n[You] >>> ")
                
                if user_input.lower() in ['quit', 'exit', 'q']:
                    print(f"\n👋 Goodbye from {self.name}!")
                    break
                
                if user_input.lower() == 'info':
                    self._show_personality_info()
                    continue
                
                if user_input.lower() == 'clear':
                    self.conversation_history = []
                    print("🧹 Conversation history cleared")
                    continue
                
                if not user_input.strip():
                    continue
                
                print(f"\n[{self.name}] >>> ", end="", flush=True)
                response = self.ask(user_input)
                print(response)
                
            except KeyboardInterrupt:
                print(f"\n\n👋 Goodbye from {self.name}!")
                break
            except Exception as e:
                print(f"\n❌ Error: {e}")
    
    def _show_personality_info(self):
        """Display detailed personality information"""
        print(f"\n{'='*60}")
        print(f"🎭 PERSONALITY PROFILE: {self.name}")
        print(f"{'='*60}")
        print(f"Code Name: {self.code_name}")
        print(f"Specialty: {self.specialty}")
        print(f"Primary Model: {self.primary_model}")
        print(f"Backup Model: {self.backup_model or 'None'}")
        print(f"Temperature: {self.temperature}")
        print(f"Conversation Style: {self.conversation_style}")
        
        if self.backstory:
            print(f"\nBackstory:\n{self.backstory}")
        
        if self.expertise_areas:
            print(f"\nExpertise Areas:")
            for area in self.expertise_areas:
                print(f"  • {area}")
        
        if self.behavioral_traits:
            print(f"\nBehavioral Traits:")
            for trait in self.behavioral_traits:
                print(f"  • {trait}")
        
        if self.signature_phrases:
            print(f"\nSignature Phrases:")
            for phrase in self.signature_phrases:
                print(f"  • \"{phrase}\"")
        
        print(f"{'='*60}")
    
    def _get_oracle_context(self, query):
        """Get relevant database context for the query (override in personalities that need it)"""
        # Default implementation - personalities can override for specific database queries
        try:
            # Import Oracle bridge dynamically
            import sys
            import os
            oracle_bridge_path = os.path.dirname(os.path.dirname(__file__))
            if oracle_bridge_path not in sys.path:
                sys.path.append(oracle_bridge_path)
            
            from oracle_bridge import OracleBridge
            oracle = OracleBridge(silent=True)
            
            # Simple keyword-based context (personalities should override for better logic)
            if any(word in query.lower() for word in ['alert', 'recent', 'today', 'yesterday']):
                result = oracle.raw_query("""
                    SELECT COUNT(*) as alert_count, symbol
                    FROM flow_alerts 
                    WHERE DATE(alert_timestamp) >= DATE('now', '-1 day')
                    GROUP BY symbol
                    ORDER BY alert_count DESC
                    LIMIT 5
                """)
                if result.get('success'):
                    return f"Recent alerts: {result['results']}"
            
            return None  # No relevant context found
            
        except Exception as e:
            return f"Oracle access error: {e}"
    
    def get_personality_summary(self):
        """Get a dictionary summary of this personality"""
        return {
            'name': self.name,
            'code_name': self.code_name,
            'specialty': self.specialty,
            'primary_model': self.primary_model,
            'backup_model': self.backup_model,
            'temperature': self.temperature,
            'conversation_style': self.conversation_style,
            'backstory': self.backstory,
            'expertise_areas': self.expertise_areas,
            'behavioral_traits': self.behavioral_traits,
            'signature_phrases': self.signature_phrases
        }


# CLI Support for individual personality files
def main_cli(personality_class):
    """Standard CLI interface for personality files"""
    if len(sys.argv) > 1:
        # Single query mode
        question = " ".join(sys.argv[1:])
        personality = personality_class()
        
        print(f"\n🎭 {personality.name} ({personality.specialty})")
        print(f"{'='*60}")
        
        response = personality.ask(question)
        print(f"{response}")
        
    else:
        # Interactive mode
        personality = personality_class()
        personality.interactive_mode()