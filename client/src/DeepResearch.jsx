import React, { useState, useEffect, useRef } from 'react';

const DeepResearch = ({ eventSlug, websocket, clientId }) => {
  const [customNotes, setCustomNotes] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [thinkingMessages, setThinkingMessages] = useState([]);
  const [report, setReport] = useState('');
  const [recommendation, setRecommendation] = useState(null);
  const [followupMessages, setFollowupMessages] = useState([]);
  const [followupInput, setFollowupInput] = useState('');
  const [isFollowupStreaming, setIsFollowupStreaming] = useState(false);
  const followupStreamRef = useRef('');

  // Listen for research messages from WebSocket
  useEffect(() => {
    if (!websocket) return;

    const handleWebSocketMessage = (event) => {
      try {
        const data = JSON.parse(event.data);

        // Handle research messages
        if (data.message_type === 'research') {
          // Handle thinking updates
          if (data.type === 'thinking') {
            setThinkingMessages((prev) => [...prev, data.content]);
          }

          // Handle report content
          else if (data.type === 'report') {
            setReport(data.content);
          }

          // Handle completion
          else if (data.type === 'complete') {
            console.log('✅ Research complete:', data.recommendation);
            setIsGenerating(false);
            setRecommendation(data.recommendation);
          }

          // Handle errors
          else if (data.type === 'error') {
            console.error('Research error:', data.error);
            setIsGenerating(false);
            setReport(`Error: ${data.error}`);
          }
        }

        // Handle research follow-up messages
        else if (data.message_type === 'research_followup') {
          // Handle thinking updates
          if (data.type === 'thinking') {
            // Could show thinking indicator for followup
          }

          // Handle response content
          else if (data.type === 'response') {
            followupStreamRef.current = data.content;

            // Update or add assistant message
            setFollowupMessages((prev) => {
              const newMessages = [...prev];
              if (newMessages.length > 0 && newMessages[newMessages.length - 1].role === 'assistant') {
                newMessages[newMessages.length - 1].content = followupStreamRef.current;
              } else {
                newMessages.push({ role: 'assistant', content: followupStreamRef.current });
              }
              return newMessages;
            });
          }

          // Handle completion
          else if (data.type === 'complete') {
            console.log('✅ Follow-up complete');
            setIsFollowupStreaming(false);
            followupStreamRef.current = '';
          }

          // Handle errors
          else if (data.type === 'error') {
            console.error('Follow-up error:', data.error);
            setIsFollowupStreaming(false);
            setFollowupMessages((prev) => [
              ...prev,
              { role: 'assistant', content: `Error: ${data.error}` }
            ]);
          }
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

  const handleGenerateReport = async () => {
    if (!clientId || !eventSlug) {
      console.error('Missing clientId or eventSlug');
      return;
    }

    setIsGenerating(true);
    setThinkingMessages([]);
    setReport('');
    setRecommendation(null);

    try {
      const response = await fetch('http://localhost:8765/research', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          client_id: clientId,
          market_title: eventSlug,
          custom_notes: customNotes
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      console.log('📤 Sent research request, waiting for stream...');
    } catch (error) {
      console.error('Error sending research request:', error);
      setIsGenerating(false);
      setReport('Error: Failed to send research request');
    }
  };

  const handleSendFollowup = async () => {
    if (!followupInput.trim() || !clientId || !report) {
      return;
    }

    const userMessage = { role: 'user', content: followupInput.trim() };

    // Build conversation history: original report + all follow-ups + new message
    const conversationHistory = [
      { role: 'assistant', content: `Original Research Report:\n\n${report}` },
      ...followupMessages,
      userMessage
    ];

    // Add user message to UI
    setFollowupMessages((prev) => [...prev, userMessage]);
    setFollowupInput('');
    setIsFollowupStreaming(true);
    followupStreamRef.current = '';

    try {
      const response = await fetch('http://localhost:8765/research/followup', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          client_id: clientId,
          messages: conversationHistory
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      console.log('📤 Sent follow-up message, waiting for stream...');
    } catch (error) {
      console.error('Error sending follow-up:', error);
      setIsFollowupStreaming(false);
      setFollowupMessages((prev) => [
        ...prev,
        { role: 'assistant', content: 'Error: Failed to send follow-up' }
      ]);
    }
  };

  const handleFollowupKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey && followupInput.trim() && !isFollowupStreaming) {
      e.preventDefault();
      handleSendFollowup();
    }
  };

  return (
    <div className="grok-deep-research">
      <div className="grok-section">
        <h3>Deep Research</h3>
        <p className="grok-deep-research-description">
          <i>Find value in this market by analyzing the latest trends and news.</i>
        </p>
      </div>

      <div className="grok-section">
        <label className="grok-input-label">Custom Notes</label>
        <textarea
          className="grok-custom-notes"
          placeholder="Add any specific areas you'd like the report to focus on..."
          value={customNotes}
          onChange={(e) => setCustomNotes(e.target.value)}
          rows={4}
          disabled={isGenerating}
        />
      </div>

      <div className="grok-section">
        <button
          className="grok-generate-report-btn"
          onClick={handleGenerateReport}
          disabled={isGenerating || !eventSlug}
        >
          {isGenerating ? 'Generating Report...' : 'Generate Report'}
        </button>
      </div>

      {/* Thinking Messages */}
      {thinkingMessages.length > 0 && (
        <div className="grok-section">
          <h4>Analysis Progress</h4>
          <div className="grok-thinking-messages">
            {thinkingMessages.map((msg, idx) => (
              <div key={idx} className="grok-thinking-message">
                <span className="grok-thinking-icon">🔄</span> {msg}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Report */}
      {report && (
        <div className="grok-section">
          <h4>Research Report</h4>
          <div className="grok-report-content">
            {report}
          </div>
        </div>
      )}

      {/* Recommendation */}
      {recommendation && (
        <div className="grok-section">
          <h4>Recommendation</h4>
          <div className={`grok-recommendation grok-recommendation-${recommendation.toLowerCase()}`}>
            <strong>{recommendation}</strong>
          </div>
        </div>
      )}

      {/* Follow-up Discussion */}
      {report && (
        <div className="grok-section">
          <h4>Follow-up Questions</h4>
          <p className="grok-followup-description">
            <i>Ask questions or challenge the report findings</i>
          </p>

          {/* Follow-up messages */}
          {followupMessages.length > 0 && (
            <div className="grok-followup-messages">
              {followupMessages.map((msg, idx) => (
                <div key={idx} className={`grok-followup-message ${msg.role}`}>
                  <div className="grok-followup-message-content">
                    {msg.content}
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Follow-up input */}
          <div className="grok-followup-input-container">
            <input
              type="text"
              className="grok-followup-input"
              placeholder="Ask a follow-up question..."
              value={followupInput}
              onChange={(e) => setFollowupInput(e.target.value)}
              onKeyPress={handleFollowupKeyPress}
              disabled={isFollowupStreaming}
            />
            <button
              className="grok-followup-send"
              onClick={handleSendFollowup}
              disabled={isFollowupStreaming || !followupInput.trim()}
            >
              {isFollowupStreaming ? 'Sending...' : 'Send'}
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default DeepResearch;
