"""
AI Council - Orchestrator for multi-personality discussions
"""
import os
import sys
import argparse
from typing import List, Dict, Any, Optional
from datetime import datetime
import json

from .base_personality import BasePersonality

class AICouncil:
    """Orchestrator for AI Council discussions"""
    
    def __init__(self):
        self.personalities = {}
        self.discussion_history = []
    
    def load_personality(self, code_name: str) -> Optional[BasePersonality]:
        """Load a personality by code name"""
        if code_name in self.personalities:
            return self.personalities[code_name]
        
        try:
            # Dynamic import
            module = __import__(f"ai_council.personalities.{code_name}", fromlist=[code_name])
            
            # Find the personality class in the module
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (isinstance(attr, type) and 
                    issubclass(attr, BasePersonality) and 
                    attr != BasePersonality):
                    
                    personality = attr()
                    self.personalities[code_name] = personality
                    return personality
            
            raise ValueError(f"No personality class found in {code_name}.py")
            
        except ImportError:
            raise ValueError(f"Personality '{code_name}' not found")
    
    def discuss(self, 
                question: str, 
                members: Optional[List[str]] = None,
                context: str = "",
                rounds: int = 1) -> Dict[str, Any]:
        """
        Hold a council discussion on a question
        
        Args:
            question: The question to discuss
            members: List of personality code_names to include (None = all available)
            context: Additional context for the discussion
            rounds: Number of discussion rounds (1 = just initial responses)
            
        Returns:
            Dictionary with discussion results
        """
        if members is None:
            members = self._discover_available_personalities()
        
        discussion = {
            'question': question,
            'context': context,
            'timestamp': datetime.now().isoformat(),
            'members': [],
            'responses': {},
            'rounds': [],
            'summary': ""
        }
        
        # Load all requested personalities
        loaded_personalities = {}
        for code_name in members:
            try:
                personality = self.load_personality(code_name)
                loaded_personalities[code_name] = personality
                discussion['members'].append({
                    'code_name': code_name,
                    'name': personality.name,
                    'specialty': personality.specialty,
                    'model': personality.primary_model
                })
            except Exception as e:
                print(f"⚠️  Could not load {code_name}: {e}")
        
        if not loaded_personalities:
            raise ValueError("No personalities could be loaded for discussion")
        
        # Conduct discussion rounds
        for round_num in range(rounds):
            round_responses = {}
            
            print(f"\n{'='*80}")
            print(f"🎯 COUNCIL DISCUSSION - ROUND {round_num + 1}")
            print(f"{'='*80}")
            print(f"Question: {question}")
            if context:
                print(f"Context: {context}")
            print(f"Participants: {', '.join([p.name for p in loaded_personalities.values()])}")
            print(f"{'='*80}\n")
            
            for code_name, personality in loaded_personalities.items():
                print(f"🎭 {personality.name} ({personality.specialty})...")
                
                # Build context for this round
                round_context = context
                if round_num > 0:
                    # Add previous round responses as context
                    prev_responses = discussion['rounds'][round_num - 1]['responses']
                    round_context += "\n\nPrevious council member responses:\n"
                    for prev_code, prev_response in prev_responses.items():
                        prev_personality = loaded_personalities[prev_code]
                        round_context += f"\n{prev_personality.name}: {prev_response[:200]}...\n"
                
                # Get response from personality
                try:
                    response = personality.ask(question, round_context)
                    round_responses[code_name] = response
                    
                    # Display response
                    print(f"Response: {response[:150]}{'...' if len(response) > 150 else ''}\n")
                    
                except Exception as e:
                    error_msg = f"Error getting response: {e}"
                    round_responses[code_name] = error_msg
                    print(f"❌ {error_msg}\n")
            
            discussion['rounds'].append({
                'round': round_num + 1,
                'responses': round_responses
            })
        
        # Store final responses (last round)
        discussion['responses'] = discussion['rounds'][-1]['responses']
        
        # Generate summary
        discussion['summary'] = self._generate_discussion_summary(discussion)
        
        # Store in history
        self.discussion_history.append(discussion)
        
        return discussion
    
    def _discover_available_personalities(self) -> List[str]:
        """Discover all available personality files"""
        personalities = []
        personalities_dir = os.path.join(os.path.dirname(__file__), 'personalities')
        
        if not os.path.exists(personalities_dir):
            return personalities
        
        for filename in os.listdir(personalities_dir):
            if (filename.endswith('.py') and 
                not filename.startswith('_') and 
                filename != 'personality_template.py'):
                
                code_name = filename[:-3]  # Remove .py extension
                personalities.append(code_name)
        
        return personalities
    
    def _generate_discussion_summary(self, discussion: Dict[str, Any]) -> str:
        """Generate a summary of the discussion"""
        summary_parts = []
        summary_parts.append(f"Council Discussion Summary")
        summary_parts.append(f"Question: {discussion['question']}")
        summary_parts.append(f"Participants: {len(discussion['members'])} personalities")
        summary_parts.append("")
        
        # Key themes/agreements
        responses = discussion['responses']
        if len(responses) > 1:
            summary_parts.append("Key Perspectives:")
            for code_name, response in responses.items():
                personality_name = next(
                    (m['name'] for m in discussion['members'] if m['code_name'] == code_name),
                    code_name
                )
                # Extract first sentence or key point
                first_sentence = response.split('.')[0] + '.'
                summary_parts.append(f"• {personality_name}: {first_sentence}")
        
        return "\n".join(summary_parts)
    
    def list_available_personalities(self) -> List[Dict[str, str]]:
        """List all available personalities with their info"""
        personalities = []
        available_codes = self._discover_available_personalities()
        
        for code_name in available_codes:
            try:
                personality = self.load_personality(code_name)
                personalities.append({
                    'code_name': code_name,
                    'name': personality.name,
                    'specialty': personality.specialty,
                    'model': personality.primary_model,
                    'description': personality.backstory[:100] if personality.backstory else ""
                })
            except Exception as e:
                personalities.append({
                    'code_name': code_name,
                    'name': f"Error loading {code_name}",
                    'specialty': "Unknown",
                    'model': "Unknown",
                    'description': str(e)
                })
        
        return personalities
    
    def save_discussion(self, discussion: Dict[str, Any], filename: Optional[str] = None):
        """Save a discussion to a JSON file"""
        if filename is None:
            timestamp = discussion['timestamp'].replace(':', '-').replace('.', '-')
            filename = f"council_discussion_{timestamp}.json"
        
        # Create discussions directory
        discussions_dir = os.path.join(os.path.dirname(__file__), 'discussions')
        os.makedirs(discussions_dir, exist_ok=True)
        
        filepath = os.path.join(discussions_dir, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(discussion, f, indent=2, ensure_ascii=False)
        
        print(f"💾 Discussion saved to: {filepath}")
        return filepath


def main():
    """CLI interface for AI Council"""
    parser = argparse.ArgumentParser(
        description="AI Council - Multi-personality discussions",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python council.py "Should I hedge my portfolio?" --members risk_hawk,options_guru
  python council.py "Is NVDA overvalued?" --full-council
  python council.py --list-personalities
  python council.py "Market outlook?" --context "VIX at 25, S&P down 5%"
        """
    )
    
    parser.add_argument('question', nargs='?', help='Question for the council to discuss')
    parser.add_argument('--members', '-m', 
                       help='Comma-separated list of personality code names')
    parser.add_argument('--full-council', '-f', action='store_true',
                       help='Include all available personalities')
    parser.add_argument('--context', '-c', default="",
                       help='Additional context for the discussion')
    parser.add_argument('--rounds', '-r', type=int, default=1,
                       help='Number of discussion rounds (default: 1)')
    parser.add_argument('--save', '-s', action='store_true',
                       help='Save discussion to JSON file')
    parser.add_argument('--list-personalities', '-l', action='store_true',
                       help='List all available personalities')
    parser.add_argument('--interactive', '-i', action='store_true',
                       help='Start interactive council session')
    
    args = parser.parse_args()
    
    council = AICouncil()
    
    if args.list_personalities:
        personalities = council.list_available_personalities()
        print(f"\n🎭 Available AI Council Personalities ({len(personalities)}):")
        print(f"{'='*80}")
        for p in personalities:
            print(f"Code: {p['code_name']:<15} | {p['name']:<25} | {p['specialty']}")
            if p['description']:
                print(f"{'':21} {p['description'][:60]}...")
            print()
        return
    
    if args.interactive:
        interactive_council_session(council)
        return
    
    if not args.question:
        parser.print_help()
        return
    
    # Determine members
    members = None
    if args.full_council:
        members = None  # Use all available
    elif args.members:
        members = [m.strip() for m in args.members.split(',')]
    else:
        # Default to a few key personalities if none specified
        available = council._discover_available_personalities()
        members = available[:3] if available else None
    
    if not members:
        available = council._discover_available_personalities()
        if not available:
            print("❌ No personalities found. Create personality files in ai_council/personalities/")
            return
        print(f"🎯 Using all available personalities: {', '.join(available)}")
    
    # Conduct discussion
    try:
        discussion = council.discuss(
            question=args.question,
            members=members,
            context=args.context,
            rounds=args.rounds
        )
        
        # Display summary
        print(f"\n{'='*80}")
        print(f"📋 COUNCIL DISCUSSION SUMMARY")
        print(f"{'='*80}")
        print(discussion['summary'])
        
        # Save if requested
        if args.save:
            council.save_discussion(discussion)
        
    except Exception as e:
        print(f"❌ Council discussion failed: {e}")


def interactive_council_session(council: AICouncil):
    """Start an interactive council session"""
    print(f"\n{'='*80}")
    print(f"🎭 AI COUNCIL - INTERACTIVE SESSION")
    print(f"{'='*80}")
    
    available = council.list_available_personalities()
    print(f"Available personalities: {len(available)}")
    for p in available[:5]:  # Show first 5
        print(f"  • {p['code_name']:<15} - {p['name']}")
    if len(available) > 5:
        print(f"  ... and {len(available) - 5} more (use 'list' command)")
    
    print(f"\nCommands:")
    print(f"  list                    - Show all personalities")
    print(f"  members <codes>         - Set active council members")
    print(f"  context <text>          - Set discussion context")
    print(f"  rounds <n>              - Set number of discussion rounds")
    print(f"  quit                    - Exit")
    print(f"{'='*80}\n")
    
    current_members = None
    current_context = ""
    current_rounds = 1
    
    while True:
        try:
            user_input = input(f"\n[Council] >>> ").strip()
            
            if user_input.lower() in ['quit', 'exit', 'q']:
                print("👋 Goodbye from the AI Council!")
                break
            
            if user_input.lower() == 'list':
                personalities = council.list_available_personalities()
                print(f"\n🎭 Available Personalities:")
                for p in personalities:
                    print(f"  {p['code_name']:<15} - {p['name']:<25} ({p['specialty']})")
                continue
            
            if user_input.lower().startswith('members '):
                member_codes = user_input[8:].strip().split(',')
                current_members = [m.strip() for m in member_codes]
                print(f"✅ Council members set to: {', '.join(current_members)}")
                continue
            
            if user_input.lower().startswith('context '):
                current_context = user_input[8:].strip()
                print(f"✅ Context set: {current_context[:50]}...")
                continue
            
            if user_input.lower().startswith('rounds '):
                try:
                    current_rounds = int(user_input[7:].strip())
                    print(f"✅ Discussion rounds set to: {current_rounds}")
                    continue
                except ValueError:
                    print("❌ Invalid rounds number")
                    continue
            
            if not user_input:
                continue
            
            # Treat as discussion question
            print(f"\n🎯 Starting council discussion...")
            discussion = council.discuss(
                question=user_input,
                members=current_members,
                context=current_context,
                rounds=current_rounds
            )
            
            print(f"\n📋 Summary:")
            print(discussion['summary'])
            
        except KeyboardInterrupt:
            print(f"\n\n👋 Goodbye from the AI Council!")
            break
        except Exception as e:
            print(f"❌ Error: {e}")


if __name__ == "__main__":
    main()