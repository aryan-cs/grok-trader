import React, { useState } from 'react';

const Chat = () => {
  const [chatMessages, setChatMessages] = useState([]);
  const [chatInput, setChatInput] = useState('');

  const handleSendMessage = () => {
    if (chatInput.trim()) {
      setChatMessages([...chatMessages, { role: 'user', content: chatInput }]);
      setChatInput('');
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && chatInput.trim()) {
      handleSendMessage();
    }
  };

  return (
    <div className="grok-chat">
      <div className="grok-chat-messages">
        {chatMessages.length === 0 ? (
          <div className="grok-chat-empty">
            <p>Start a conversation about this market</p>
          </div>
        ) : (
          chatMessages.map((msg, idx) => (
            <div key={idx} className={`grok-chat-message ${msg.role}`}>
              <div className="grok-chat-message-content">{msg.content}</div>
            </div>
          ))
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
        />
        <button
          className="grok-chat-send"
          onClick={handleSendMessage}
        >
          Send
        </button>
      </div>
    </div>
  );
};

export default Chat;
