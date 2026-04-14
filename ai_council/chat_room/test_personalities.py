#!/usr/bin/env python3
"""
Test Chat Personality Integration
================================

Test that we can load existing AI Council personalities into the chat room
without duplicating or modifying them.
"""

import sys
import os

# Add paths
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_personality_loading():
    """Test loading personalities from ai_council/personalities/"""
    print("Testing Chat Personality Integration")
    print("=" * 60)
    
    try:
        from chat_personalities import (
            get_available_personalities, 
            get_personality_info, 
            load_personality_for_chat,
            list_and_load_demo_personalities
        )
        
        # Step 1: Check if we can discover personalities
        print("Step 1: Discovering available personalities...")
        available = get_available_personalities()
        print(f"Found {len(available)} personalities: {available}")
        
        if not available:
            print("ERROR: No personalities found!")
            print("Make sure you have personality files in ai_council/personalities/")
            return False
        
        # Step 2: Get info about each personality
        print("\nStep 2: Getting personality details...")
        for code_name in available:
            info = get_personality_info(code_name)
            if info:
                print(f"  OK {code_name}: {info.get('name', 'Unknown')} - {info.get('specialty', 'Unknown')}")
            else:
                print(f"  ERROR {code_name}: Could not get info")
        
        # Step 3: Try loading a personality for chat
        print("\nStep 3: Loading personality for chat...")
        
        # Try demo_guru first, then any available
        test_personality = None
        if 'demo_guru' in available:
            test_personality = 'demo_guru'
        elif available:
            test_personality = available[0]
        
        if test_personality:
            print(f"Loading: {test_personality}")
            chat_personality = load_personality_for_chat(test_personality)
            
            if chat_personality:
                print(f"OK Successfully loaded: {chat_personality.display_name}")
                print(f"   Model: {chat_personality.primary_model}")
                print(f"   Specialty: {chat_personality.specialty}")
                print(f"   Avatar: {chat_personality.avatar}")
                print(f"   Color: {chat_personality.message_color}")
                
                # Step 4: Test getting a response
                print(f"\nStep 4: Testing chat response...")
                test_message = "Hello, this is a test message for the chat room!"
                
                try:
                    response = chat_personality.ask_for_chat(test_message)
                    print(f"OK Response received:")
                    print(f"   '{response[:100]}{'...' if len(response) > 100 else ''}'")
                    print(f"   Length: {len(response)} characters")
                    
                    return True
                    
                except Exception as e:
                    print(f"ERROR getting response: {e}")
                    return False
                    
            else:
                print(f"ERROR Failed to load {test_personality}")
                return False
        else:
            print("ERROR No suitable personality found for testing")
            return False
    
    except Exception as e:
        print(f"ERROR Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False

def interactive_test():
    """Interactive test to chat with a personality"""
    print("\n" + "="*60)
    print("Interactive Personality Test")
    print("="*60)
    
    try:
        from chat_personalities import list_and_load_demo_personalities
        
        # Show available personalities and try to load one
        demo = list_and_load_demo_personalities()
        
        if demo:
            print(f"\nChat test with {demo.display_name}")
            print("Type messages (or 'quit' to exit):")
            print("-" * 40)
            
            while True:
                user_input = input("\nYou: ").strip()
                
                if user_input.lower() in ['quit', 'exit', 'q']:
                    break
                
                if not user_input:
                    continue
                
                try:
                    response = demo.ask_for_chat(user_input)
                    print(f"{demo.display_name}: {response}")
                    
                except Exception as e:
                    print(f"ERROR: {e}")
            
            print("\nInteractive test completed")
        else:
            print("ERROR Could not load a personality for testing")
    
    except Exception as e:
        print(f"ERROR Interactive test failed: {e}")

if __name__ == "__main__":
    success = test_personality_loading()
    
    if success:
        print("\nAll tests passed!")
        
        # Ask if they want to try interactive test
        try:
            response = input("\nWould you like to try interactive chat test? (y/N): ").strip().lower()
            if response in ['y', 'yes']:
                interactive_test()
        except KeyboardInterrupt:
            print("\nTest completed.")
    else:
        print("\nTests failed. Check the issues above.")
        
    print("\nNext steps:")
    print("- If tests passed: integrate with WebSocket server")  
    print("- If tests failed: fix personality loading issues")
    print("- Available personalities can be loaded into chat room")