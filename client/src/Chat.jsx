import React, { useState, useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';

const Chat = ({ websocket, clientId, eventSlug, chatMessages, setChatMessages }) => {
  const [chatInput, setChatInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [shouldAutoScroll, setShouldAutoScroll] = useState(true);
  const streamingMessageRef = useRef('');
  const messagesEndRef = useRef(null);
  const messagesContainerRef = useRef(null);

  // Listen for streaming messages from WebSocket
  useEffect(() => {
    if (!websocket) return;

    const handleWebSocketMessage = (event) => {
      try {
        const data = JSON.parse(event.data);

        // Only handle chat messages
        if (data.message_type !== 'chat') return;

        // Handle chat deltas
        if (data.type === 'delta') {
          setIsStreaming(true);
          streamingMessageRef.current += data.content;

          // Update the last message (assistant's message)
          setChatMessages((prev) => {
            const newMessages = [...prev];
            if (newMessages.length > 0 && newMessages[newMessages.length - 1].role === 'assistant') {
              newMessages[newMessages.length - 1].content = streamingMessageRef.current;
            } else {
              newMessages.push({ role: 'assistant', content: streamingMessageRef.current });
            }
            return newMessages;
          });
        }

        // Handle chat completion
        else if (data.type === 'complete') {
          console.log('✅ Chat response complete');
          setIsStreaming(false);
          streamingMessageRef.current = '';
        }

        // Handle errors
        else if (data.type === 'error') {
          console.error('Chat error:', data.error);
          setIsStreaming(false);
          setChatMessages((prev) => [
            ...prev,
            { role: 'assistant', content: `Error: ${data.error}` }
          ]);
        }
      } catch (e) {
        console.error('Error parsing WebSocket message:', e);
      }
    };

    websocket.addEventListener('message', handleWebSocketMessage);

    return () => {
      websocket.removeEventListener('message', handleWebSocketMessage);
    };
  }, [websocket]);

  const handleSendMessage = async () => {
    if (!chatInput.trim() || !clientId) return;

    const userMessage = { role: 'user', content: chatInput.trim() };
    const newMessages = [...chatMessages, userMessage];

    // Add user message to chat
    setChatMessages(newMessages);
    setChatInput('');
    setIsStreaming(true);
    streamingMessageRef.current = '';

    try {
      // Send POST request to server
      const response = await fetch('http://localhost:8765/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          client_id: clientId,
          messages: newMessages,
          event_slug: eventSlug
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      console.log('📤 Sent chat message, waiting for stream...');
    } catch (error) {
      console.error('Error sending chat message:', error);
      setIsStreaming(false);
      setChatMessages((prev) => [
        ...prev,
        { role: 'assistant', content: 'Error: Failed to send message' }
      ]);
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey && chatInput.trim() && !isStreaming) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  // Check if user is at the bottom of the chat
  const isAtBottom = () => {
    if (!messagesContainerRef.current) return true;
    const { scrollTop, scrollHeight, clientHeight } = messagesContainerRef.current;
    return scrollHeight - scrollTop - clientHeight < 50; // 50px threshold
  };

  // Handle scroll events
  const handleScroll = () => {
    setShouldAutoScroll(isAtBottom());
  };

  // Auto-scroll to bottom when messages change (if user is at bottom)
  useEffect(() => {
    if (shouldAutoScroll && messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [chatMessages, shouldAutoScroll]);

  return (
    <div className="grok-chat">
      <div
        className="grok-chat-messages"
        ref={messagesContainerRef}
        onScroll={handleScroll}
      >
        {chatMessages.length === 0 ? (
          <div className="grok-chat-empty">
            <p>Start a conversation about this market</p>
          </div>
        ) : (
          <>
            {chatMessages.map((msg, idx) => (
              <div key={idx} className={`grok-chat-message ${msg.role}`}>
                <div className="grok-chat-message-content">
                  <ReactMarkdown>{msg.content}</ReactMarkdown>
                  {isStreaming && idx === chatMessages.length - 1 && msg.role === 'assistant' && (
                    <span className="grok-streaming-cursor">▊</span>
                  )}
                </div>
              </div>
            ))}
            <div ref={messagesEndRef} />
          </>
        )}
      </div>
      <div className="grok-chat-input-container">
        <input
          type="text"
          className="grok-chat-input"
          placeholder="Ask about this market..."
          value={chatInput}
          onChange={(e) => setChatInput(e.target.value)}
          onKeyPress={handleKeyPress}
          disabled={isStreaming}
        />
        <button
          className="grok-chat-send"
          onClick={handleSendMessage}
          disabled={isStreaming || !chatInput.trim()}
        >
          {isStreaming ? 'Streaming...' : 'Send'}
        </button>
      </div>
    </div>
  );
};

export default Chat;
