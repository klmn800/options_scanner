#!/usr/bin/env python3
"""
Phase 1 Test Script
==================

Quick test to verify Phase 1 functionality:
1. Start the server
2. Open browser
3. Test message sending
4. Test typing indicators
"""

import subprocess
import webbrowser
import time
import sys
import os

def test_phase1():
    """Test Phase 1 functionality"""
    print("🧪 Testing AI Council Chat Room - Phase 1")
    print("=" * 60)
    
    # Check if we're in the right directory
    current_dir = os.getcwd()
    expected_path = "ai_council\\chat_room"
    
    if not current_dir.endswith(expected_path.replace('\\', os.sep)):
        print("❌ Please run this from the ai_council/chat_room directory")
        print(f"Current: {current_dir}")
        print(f"Expected to end with: {expected_path}")
        return False
    
    # Check if required files exist
    required_files = [
        'chat_server.py',
        'templates/chat.html',
        'static/chat.css',
        'static/chat.js'
    ]
    
    missing_files = []
    for file_path in required_files:
        if not os.path.exists(file_path):
            missing_files.append(file_path)
    
    if missing_files:
        print("❌ Missing required files:")
        for file_path in missing_files:
            print(f"   - {file_path}")
        return False
    
    print("✅ All required files present")
    
    # Check dependencies
    try:
        import flask
        import flask_socketio
        print("✅ Flask and SocketIO available")
    except ImportError as e:
        print(f"❌ Missing dependencies: {e}")
        print("Run: pip install flask flask-socketio")
        return False
    
    print("\n🚀 Phase 1 Test Plan:")
    print("1. Start the server (chat_server.py)")
    print("2. Open browser to http://localhost:5000")  
    print("3. Test message sending")
    print("4. Test with multiple browser tabs")
    print("5. Test typing indicators")
    
    print("\n📋 Manual Test Checklist:")
    print("[ ] Server starts without errors")
    print("[ ] Browser opens to chat interface")
    print("[ ] Dark theme looks good")
    print("[ ] Can send messages")
    print("[ ] Messages appear in chat")
    print("[ ] Multiple browser tabs sync messages")
    print("[ ] Typing indicators work")
    print("[ ] Connection status shows 'Connected'")
    
    input("\nPress Enter to start the server...")
    
    try:
        print("🚀 Starting chat server...")
        print("💡 Open multiple browser tabs to test multi-user chat")
        print("🛑 Press Ctrl+C to stop the server")
        print("-" * 60)
        
        # Start server and open browser
        import threading
        
        def open_browser():
            time.sleep(2)  # Give server time to start
            webbrowser.open('http://localhost:5000')
        
        browser_thread = threading.Thread(target=open_browser)
        browser_thread.start()
        
        # Start the server (this will block)
        subprocess.run([sys.executable, 'chat_server.py'])
        
    except KeyboardInterrupt:
        print("\n\n✅ Server stopped")
        print("🎯 Phase 1 test completed!")
        
        print("\n📊 Expected Results:")
        print("✅ Dark theme chat interface")
        print("✅ Real-time message sending/receiving") 
        print("✅ Typing indicators")
        print("✅ Connection status indicators")
        print("✅ Multiple browser tab synchronization")
        
        return True
    
    except Exception as e:
        print(f"\n❌ Error during test: {e}")
        return False

if __name__ == "__main__":
    success = test_phase1()
    
    if success:
        print("\n🎉 Phase 1 Complete!")
        print("➡️  Next: Phase 2 - AI Personality Integration")
    else:
        print("\n❌ Phase 1 test failed")
        print("Please fix issues before proceeding to Phase 2")