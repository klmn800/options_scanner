/**
 * AI Council Chat Room - Frontend JavaScript
 * Phase 1: Basic WebSocket communication and UI management
 */

class ChatClient {
    constructor() {
        // Configuration from HTML
        this.config = window.USER_CONFIG || {
            name: 'Ben',
            room: 'council-main',
            avatar: '👤',
            theme: 'dark'
        };
        
        // Socket connection
        this.socket = null;
        this.isConnected = false;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        
        // UI elements
        this.elements = {};
        this.typingTimer = null;
        this.isTyping = false;
        
        // Message management
        this.messageQueue = [];
        this.lastMessageSender = null;
        
        // Initialize
        this.init();
    }
    
    /**
     * Initialize the chat client
     */
    init() {
        console.log('🚀 Initializing AI Council Chat Client...');
        
        // Get DOM elements
        this.getElements();
        
        // Set up event listeners
        this.setupEventListeners();
        
        // Connect to server
        this.connect();
        
        console.log('✅ Chat client initialized');
    }
    
    /**
     * Get references to DOM elements
     */
    getElements() {
        this.elements = {
            messagesContainer: document.getElementById('messagesContainer'),
            messageInput: document.getElementById('messageInput'),
            sendButton: document.getElementById('sendButton'),
            typingIndicators: document.getElementById('typingIndicators'),
            connectionStatus: document.getElementById('connectionStatus'),
            statusDot: document.getElementById('statusDot'),
            statusText: document.getElementById('statusText'),
            clearChatButton: document.getElementById('clearChatButton'),
            saveTranscriptButton: document.getElementById('saveTranscriptButton'),
            addPersonalitySelect: document.getElementById('addPersonalitySelect'),
            activePersonalities: document.getElementById('activePersonalities')
        };
        
        // Verify all elements exist
        for (const [key, element] of Object.entries(this.elements)) {
            if (!element) {
                console.error(`❌ Required element not found: ${key}`);
            }
        }
    }
    
    /**
     * Set up event listeners for UI interactions
     */
    setupEventListeners() {
        // Send button click
        this.elements.sendButton.addEventListener('click', () => {
            this.sendMessage();
        });
        
        // Enter key to send message
        this.elements.messageInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });
        
        // Typing indicator management
        this.elements.messageInput.addEventListener('input', () => {
            this.handleTypingStart();
        });
        
        this.elements.messageInput.addEventListener('blur', () => {
            this.handleTypingStop();
        });
        
        // Focus message input when page loads
        window.addEventListener('load', () => {
            if (this.elements.messageInput) {
                this.elements.messageInput.focus();
            }
        });
        
        // Control button event listeners
        this.elements.clearChatButton.addEventListener('click', () => {
            this.clearChat();
        });
        
        this.elements.saveTranscriptButton.addEventListener('click', () => {
            this.saveTranscript();
        });
        
        this.elements.addPersonalitySelect.addEventListener('change', (e) => {
            if (e.target.value) {
                this.addPersonality(e.target.value);
                e.target.value = ''; // Reset selection
            }
        });
        
        // Handle browser close/refresh
        window.addEventListener('beforeunload', () => {
            if (this.socket) {
                this.socket.disconnect();
            }
        });
    }
    
    /**
     * Connect to the WebSocket server
     */
    connect() {
        console.log('Connecting to server...');
        
        this.updateConnectionStatus('connecting', 'Connecting...');
        
        try {
            // Initialize socket connection
            this.socket = io();
            
            // Connection event handlers
            this.socket.on('connect', () => {
                console.log('✅ Connected to server');
                this.isConnected = true;
                this.reconnectAttempts = 0;
                this.updateConnectionStatus('connected', 'Connected');
                
                // Join the chat room
                this.joinRoom();
                
                // Enable input
                this.enableInput();
            });
            
            this.socket.on('disconnect', () => {
                console.log('❌ Disconnected from server');
                this.isConnected = false;
                this.updateConnectionStatus('disconnected', 'Disconnected');
                
                // Disable input
                this.disableInput();
                
                // Attempt reconnection
                this.attemptReconnect();
            });
            
            this.socket.on('connect_error', (error) => {
                console.error('Connection error:', error);
                this.updateConnectionStatus('error', 'Connection Error');
                this.disableInput();
            });
            
            // Chat event handlers
            this.setupChatEventHandlers();
            
        } catch (error) {
            console.error('❌ Failed to initialize socket:', error);
            this.updateConnectionStatus('error', 'Failed to Connect');
        }
    }
    
    /**
     * Set up chat-specific WebSocket event handlers
     */
    setupChatEventHandlers() {
        // Room events
        this.socket.on('room_joined', (data) => {
            console.log('Joined room:', data.room_id);
            this.addSystemMessage(`Welcome to ${data.room_id}!`);
            
            if (data.message_count > 0) {
                this.addSystemMessage(`Loading ${data.message_count} previous messages...`);
            }
            
            // Request available personalities to populate dropdown
            this.socket.emit('get_available_personalities');
        });
        
        this.socket.on('message_history', (data) => {
            console.log('Received message history:', data.messages.length, 'messages');
            this.loadMessageHistory(data.messages);
        });
        
        this.socket.on('user_joined', (data) => {
            this.addSystemMessage(`${data.user_name} joined the chat`);
        });
        
        this.socket.on('user_left', (data) => {
            this.addSystemMessage(`${data.user_name} left the chat`);
        });
        
        // Message events
        this.socket.on('new_message', (message) => {
            console.log('💬 New message received:', message);
            console.log('📝 Message details:', JSON.stringify(message, null, 2));
            this.displayMessage(message);
        });
        
        // Typing events
        this.socket.on('user_typing', (data) => {
            if (data.user_name !== this.config.name) {
                this.showTypingIndicator(data.user_name, data.typing);
            }
        });
        
        // Error handling
        this.socket.on('error', (error) => {
            console.error('❌ Chat error:', error);
            this.addSystemMessage(`Error: ${error.message}`, 'error');
        });
        
        // Room info updates
        this.socket.on('room_info', (info) => {
            console.log('Room info:', info);
            // Could display participant count, etc.
        });
        
        // Chat control events
        this.socket.on('chat_cleared', (data) => {
            console.log('Chat cleared by:', data.cleared_by);
            this.elements.messagesContainer.innerHTML = `
                <div class="welcome-message">
                    <p>Chat cleared by ${data.cleared_by}. Start a new conversation!</p>
                </div>
            `;
        });
        
        this.socket.on('personality_added', (data) => {
            console.log('Personality added:', data);
            this.addSystemMessage(`${data.personality_code} joined the conversation (added by ${data.added_by})`);
            this.updateActivePersonalities(data.active_personalities);
            // Request updated personality list for dropdown
            this.socket.emit('get_available_personalities');
        });
        
        this.socket.on('personality_removed', (data) => {
            console.log('Personality removed:', data);
            this.addSystemMessage(`${data.personality_code} left the conversation (removed by ${data.removed_by})`);
            this.updateActivePersonalities(data.active_personalities);
            // Request updated personality list for dropdown
            this.socket.emit('get_available_personalities');
        });
        
        this.socket.on('available_personalities', (data) => {
            console.log('Available personalities received:', data.personalities);
            // Get current active personalities for comparison
            const activePersonalities = [];
            this.populatePersonalitySelector(data.personalities, activePersonalities);
        });
    }
    
    /**
     * Join the chat room
     */
    joinRoom() {
        const roomData = {
            room_id: this.config.room,
            user_name: this.config.name
        };
        
        console.log('Joining room:', roomData);
        this.socket.emit('join_room', roomData);
    }
    
    /**
     * Send a message
     */
    sendMessage() {
        const messageText = this.elements.messageInput.value.trim();
        
        if (!messageText || !this.isConnected) {
            return;
        }
        
        console.log('📤 Sending message:', messageText);
        
        // Send to server
        this.socket.emit('send_message', {
            message: messageText
        });
        
        // Clear input
        this.elements.messageInput.value = '';
        
        // Stop typing indicator
        this.handleTypingStop();
        
        // Focus back to input
        this.elements.messageInput.focus();
    }
    
    /**
     * Display a message in the chat
     */
    displayMessage(message) {
        console.log('🔍 displayMessage called with:', message);
        
        try {
            const messageElement = this.createMessageElement(message);
            console.log('📦 Message element created:', messageElement);
            
            if (this.elements.messagesContainer) {
                this.elements.messagesContainer.appendChild(messageElement);
                console.log('✅ Message element appended to container');
            } else {
                console.error('❌ messagesContainer not found!');
                return;
            }
            
            // Remove welcome message if it exists
            const welcomeMessage = this.elements.messagesContainer.querySelector('.welcome-message');
            if (welcomeMessage) {
                welcomeMessage.remove();
                console.log('🗑️ Welcome message removed');
            }
            
            // Scroll to bottom
            this.scrollToBottom();
            
            // Update last message sender
            this.lastMessageSender = message.sender;
            
            console.log('✨ Message display completed successfully');
        } catch (error) {
            console.error('💥 Error in displayMessage:', error);
        }
    }
    
    /**
     * Create a message DOM element
     */
    createMessageElement(message) {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message';
        
        // Determine message type
        const isOwnMessage = message.sender === this.config.name;
        const isSystemMessage = message.sender_type === 'system';
        
        if (isOwnMessage) {
            messageDiv.classList.add('own');
        } else if (isSystemMessage) {
            messageDiv.classList.add('system');
        } else {
            messageDiv.classList.add('other');
        }
        
        // Create message header (sender & time)
        if (!isSystemMessage) {
            const headerDiv = document.createElement('div');
            headerDiv.className = 'message-header';
            
            const senderSpan = document.createElement('span');
            senderSpan.className = 'message-sender';
            senderSpan.textContent = message.sender;
            
            const timeSpan = document.createElement('span');
            timeSpan.className = 'message-time';
            timeSpan.textContent = this.formatTimestamp(message.timestamp);
            
            headerDiv.appendChild(senderSpan);
            headerDiv.appendChild(timeSpan);
            messageDiv.appendChild(headerDiv);
        }
        
        // Create message content
        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';
        contentDiv.textContent = message.message;
        
        messageDiv.appendChild(contentDiv);
        
        // Add animation
        messageDiv.classList.add('fade-in');
        
        return messageDiv;
    }
    
    /**
     * Add a system message
     */
    addSystemMessage(text, type = 'info') {
        const systemMessage = {
            sender: 'System',
            sender_type: 'system',
            message: text,
            timestamp: new Date().toISOString(),
            type: type
        };
        
        this.displayMessage(systemMessage);
    }
    
    /**
     * Load message history
     */
    loadMessageHistory(messages) {
        // Clear existing messages except welcome
        const existingMessages = this.elements.messagesContainer.querySelectorAll('.message');
        existingMessages.forEach(msg => msg.remove());
        
        // Add historical messages
        messages.forEach(message => {
            this.displayMessage(message);
        });
        
        console.log(`📜 Loaded ${messages.length} historical messages`);
    }
    
    /**
     * Handle typing start
     */
    handleTypingStart() {
        if (!this.isConnected) return;
        
        if (!this.isTyping) {
            this.isTyping = true;
            this.socket.emit('typing_start', {});
            console.log('✍️ Started typing');
        }
        
        // Reset typing timer
        clearTimeout(this.typingTimer);
        this.typingTimer = setTimeout(() => {
            this.handleTypingStop();
        }, 3000); // Stop typing after 3 seconds of inactivity
    }
    
    /**
     * Handle typing stop
     */
    handleTypingStop() {
        if (this.isTyping) {
            this.isTyping = false;
            if (this.isConnected) {
                this.socket.emit('typing_stop', {});
                console.log('🛑 Stopped typing');
            }
        }
        
        clearTimeout(this.typingTimer);
    }
    
    /**
     * Show/hide typing indicator for other users
     */
    showTypingIndicator(userName, isTyping) {
        const indicatorId = `typing-${userName.replace(/\s+/g, '-')}`;
        let indicator = document.getElementById(indicatorId);
        
        if (isTyping) {
            if (!indicator) {
                indicator = document.createElement('div');
                indicator.id = indicatorId;
                indicator.className = 'typing-indicator';
                indicator.innerHTML = `<strong>${userName}</strong> is typing<span class="typing-dots">...</span>`;
                this.elements.typingIndicators.appendChild(indicator);
                this.scrollToBottom();
            }
        } else {
            if (indicator) {
                indicator.remove();
            }
        }
    }
    
    /**
     * Update connection status indicator
     */
    updateConnectionStatus(status, text) {
        this.elements.statusDot.className = `status-dot ${status}`;
        this.elements.statusText.textContent = text;
        
        console.log(`🔌 Connection status: ${status} - ${text}`);
    }
    
    /**
     * Enable input controls
     */
    enableInput() {
        this.elements.messageInput.disabled = false;
        this.elements.sendButton.disabled = false;
        this.elements.messageInput.placeholder = 'Type your message...';
    }
    
    /**
     * Disable input controls
     */
    disableInput() {
        this.elements.messageInput.disabled = true;
        this.elements.sendButton.disabled = true;
        this.elements.messageInput.placeholder = 'Disconnected...';
    }
    
    /**
     * Attempt to reconnect to server
     */
    attemptReconnect() {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts - 1), 10000);
            
            console.log(`🔄 Reconnection attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts} in ${delay}ms`);
            
            this.updateConnectionStatus('connecting', `Reconnecting (${this.reconnectAttempts}/${this.maxReconnectAttempts})...`);
            
            setTimeout(() => {
                if (!this.isConnected) {
                    this.connect();
                }
            }, delay);
        } else {
            console.error('❌ Max reconnection attempts reached');
            this.updateConnectionStatus('error', 'Connection Failed');
            this.addSystemMessage('Connection lost. Please refresh the page to reconnect.', 'error');
        }
    }
    
    /**
     * Scroll messages container to bottom
     */
    scrollToBottom() {
        setTimeout(() => {
            this.elements.messagesContainer.scrollTop = this.elements.messagesContainer.scrollHeight;
        }, 10);
    }
    
    /**
     * Format timestamp for display
     */
    formatTimestamp(timestamp) {
        if (!timestamp) return '';
        
        const date = new Date(timestamp);
        const now = new Date();
        
        // Same day: show time only
        if (date.toDateString() === now.toDateString()) {
            return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        }
        
        // Different day: show date and time
        return date.toLocaleDateString([], { 
            month: 'short', 
            day: 'numeric',
            hour: '2-digit', 
            minute: '2-digit' 
        });
    }
    
    /**
     * Get current configuration (for debugging)
     */
    getConfig() {
        return this.config;
    }
    
    /**
     * Get connection status (for debugging)
     */
    getStatus() {
        return {
            connected: this.isConnected,
            reconnectAttempts: this.reconnectAttempts,
            typing: this.isTyping,
            messageCount: this.elements.messagesContainer.querySelectorAll('.message').length
        };
    }
    
    /**
     * Clear all messages from the chat
     */
    clearChat() {
        if (!confirm('Are you sure you want to clear the chat? This cannot be undone.')) {
            return;
        }
        
        console.log('Clearing chat...');
        
        if (this.isConnected) {
            this.socket.emit('clear_chat', {});
        }
        
        // Clear local messages
        this.elements.messagesContainer.innerHTML = `
            <div class="welcome-message">
                <p>Chat cleared. Start a new conversation!</p>
            </div>
        `;
        
        console.log('Chat cleared');
    }
    
    /**
     * Save chat transcript as a file
     */
    saveTranscript() {
        const messages = this.elements.messagesContainer.querySelectorAll('.message');
        if (messages.length === 0) {
            alert('No messages to save!');
            return;
        }
        
        console.log('Saving transcript...');
        
        let transcript = '# AI Council Chat Transcript\n';
        transcript += `Generated: ${new Date().toLocaleString()}\n`;
        transcript += `Room: ${this.config.room}\n\n`;
        
        messages.forEach(message => {
            const sender = message.querySelector('.message-sender')?.textContent || 'Unknown';
            const time = message.querySelector('.message-time')?.textContent || '';
            const content = message.querySelector('.message-content')?.textContent || '';
            
            transcript += `**${sender}** (${time})\n`;
            transcript += `${content}\n\n`;
        });
        
        // Create and download file
        const blob = new Blob([transcript], { type: 'text/markdown' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `chat-transcript-${new Date().toISOString().split('T')[0]}.md`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        
        console.log('Transcript saved');
    }
    
    /**
     * Add a personality to the chat
     */
    addPersonality(personalityCode) {
        console.log(`Adding personality: ${personalityCode}`);
        
        if (this.isConnected) {
            this.socket.emit('add_personality', { personality_code: personalityCode });
        } else {
            alert('Not connected to server. Cannot add personality.');
        }
    }
    
    /**
     * Remove a personality from the chat
     */
    removePersonality(personalityCode) {
        console.log(`Removing personality: ${personalityCode}`);
        
        if (this.isConnected) {
            this.socket.emit('remove_personality', { personality_code: personalityCode });
        }
    }
    
    /**
     * Update the active personalities display
     */
    updateActivePersonalities(personalities) {
        const container = this.elements.activePersonalities;
        container.innerHTML = '';
        
        personalities.forEach(personality => {
            const chip = document.createElement('div');
            chip.className = 'personality-chip';
            chip.innerHTML = `
                <span class="avatar">${personality.avatar}</span>
                <span>${personality.name}</span>
                <button class="remove-btn" onclick="window.chatClient.removePersonality('${personality.code_name}')" title="Remove ${personality.name}">×</button>
            `;
            container.appendChild(chip);
        });
    }
    
    /**
     * Populate the personality selector dropdown
     */
    populatePersonalitySelector(availablePersonalities, activePersonalities) {
        const select = this.elements.addPersonalitySelect;
        
        // Clear existing options except the first
        while (select.children.length > 1) {
            select.removeChild(select.lastChild);
        }
        
        const activeNames = new Set(activePersonalities.map(p => p.code_name));
        
        availablePersonalities.forEach(personality => {
            if (!activeNames.has(personality.code_name)) {
                const option = document.createElement('option');
                option.value = personality.code_name;
                option.textContent = `${personality.name} (${personality.specialty})`;
                select.appendChild(option);
            }
        });
    }
}

// Initialize chat client when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    console.log('AI Council Chat Room starting...');
    
    // Create global chat client instance
    window.chatClient = new ChatClient();
    
    // Add to global scope for debugging
    window.chat = {
        client: window.chatClient,
        config: () => window.chatClient.getConfig(),
        status: () => window.chatClient.getStatus(),
        send: (msg) => {
            window.chatClient.elements.messageInput.value = msg;
            window.chatClient.sendMessage();
        }
    };
    
    console.log('✅ Chat client ready! Use window.chat for debugging.');
});