import React, { useState, useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';

const DeepResearch = ({
  eventSlug,
  selectedMarket,
  websocket,
  clientId,
  onResearchStart,
  thinkingMessages,
  setThinkingMessages,
  report,
  setReport,
  recommendation,
  setRecommendation,
  citations,
  setCitations,
  followupMessages,
  setFollowupMessages,
  isGenerating,
  setIsGenerating,
  isFollowupStreaming,
  setIsFollowupStreaming
}) => {
  const [customNotes, setCustomNotes] = useState('');
  const [followupInput, setFollowupInput] = useState('');
  const [shouldAutoScroll, setShouldAutoScroll] = useState(true);
  const followupStreamRef = useRef('');
  const reportStreamRef = useRef('');
  const messagesEndRef = useRef(null);
  const messagesContainerRef = useRef(null);

  // Listen for research messages from WebSocket
  useEffect(() => {
    if (!websocket) {
      console.warn('⚠️ DeepResearch: WebSocket not available');
      return;
    }

    console.log('🔌 DeepResearch: WebSocket connection state:', websocket.readyState);
    console.log('🔌 WebSocket states: CONNECTING=0, OPEN=1, CLOSING=2, CLOSED=3');

    const handleWebSocketMessage = (event) => {
      const receiveTime = Date.now();
      console.log(`⏰ [${receiveTime}] WebSocket message received in DeepResearch`);

      try {
        const data = JSON.parse(event.data);
        console.log(`📦 [${receiveTime}] Parsed message:`, data);

        // Log ALL messages for debugging
        if (data.message_type === 'research' || data.message_type === 'research_followup') {
          console.log('🔍 DeepResearch received message:', JSON.stringify(data, null, 2));
        }

        // Handle research messages
        if (data.message_type === 'research') {
          console.log('📊 Research message type:', data.type);

          // Handle thinking updates
          if (data.type === 'thinking') {
            console.log('💭 Adding thinking message:', data.content);
            setThinkingMessages((prev) => {
              const newMessages = [...prev, data.content];
              console.log('📝 Updated thinking messages count:', newMessages.length);
              return newMessages;
            });
          }

          // Handle streaming delta content
          else if (data.type === 'delta') {
            console.log('📄 Received delta, length:', data.content?.length);
            reportStreamRef.current += data.content;
            setReport(reportStreamRef.current);
          }

          // Handle completion
          else if (data.type === 'complete') {
            console.log('✅ Research complete:', data.recommendation);
            console.log('📚 Citations received:', data.citations?.length || 0);
            reportStreamRef.current = '';
            setIsGenerating(false);
            setRecommendation(data.recommendation);
            if (data.citations) {
              setCitations(data.citations);
            }
          }

          // Handle errors
          else if (data.type === 'error') {
            console.error('❌ Research error:', data.error);
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

          // Handle streaming delta content
          else if (data.type === 'delta') {
            followupStreamRef.current += data.content;

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
    if (!clientId || !selectedMarket) {
      console.error('Missing clientId or selectedMarket');
      return;
    }

    if (onResearchStart) {
      onResearchStart();
    }

    setIsGenerating(true);
    setThinkingMessages([]);
    setReport('');
    setRecommendation(null);
    setCitations([]);
    reportStreamRef.current = '';

    try {
      const response = await fetch('http://localhost:8765/research', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          client_id: clientId,
          market_title: selectedMarket,
          event_slug: eventSlug || '',
          custom_notes: customNotes
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      console.log('📤 Sent research request, status:', data.status);
    } catch (error) {
      console.error('Error sending research request:', error);
      setIsGenerating(false);
      setReport(`Error: ${error.message}`);
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

  // Check if user is at the bottom of the messages
  const isAtBottom = () => {
    if (!messagesContainerRef.current) return true;
    const { scrollTop, scrollHeight, clientHeight } = messagesContainerRef.current;
    return scrollHeight - scrollTop - clientHeight < 50; // 50px threshold
  };

  // Handle scroll events
  const handleScroll = () => {
    setShouldAutoScroll(isAtBottom());
  };

  // Auto-scroll to bottom when content changes (if user is at bottom)
  useEffect(() => {
    if (shouldAutoScroll && messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [report, thinkingMessages, followupMessages, shouldAutoScroll]);

  const hasStartedResearch = isGenerating || thinkingMessages.length > 0 || report;

  // Debug logging
  console.log('🎨 DeepResearch render - isGenerating:', isGenerating, 'thinkingMessages:', thinkingMessages.length, 'report:', !!report);

  return (
    <div className="grok-deep-research">
      {/* Initial Form - Show only if research hasn't started */}
      {!hasStartedResearch && (
        <>
          <div className="grok-section">
            <h3>Deep Research</h3>
            <p className="grok-deep-research-description">
              <i>
                {!selectedMarket
                  ? 'Select a market above to get started with deep research.'
                  : 'Find value in this market by analyzing the latest trends and news.'}
              </i>
            </p>
          </div>

          <div className="grok-section">
            <label className="grok-input-label">Custom Notes (Optional)</label>
            <textarea
              className="grok-custom-notes"
              placeholder="Add any specific areas you'd like the report to focus on..."
              value={customNotes}
              onChange={(e) => setCustomNotes(e.target.value)}
              rows={4}
              disabled={!selectedMarket}
            />
          </div>

          <div className="grok-section">
            <button
              className="grok-generate-report-btn"
              onClick={handleGenerateReport}
              disabled={!selectedMarket}
            >
              {!selectedMarket ? 'Select a market to research' : 'Generate Report'}
            </button>
          </div>
        </>
      )}

      {/* Chat-like Interface - Show after research starts */}
      {hasStartedResearch && (
        <div className="grok-research-chat">
          {/* Messages Container */}
          <div
            className="grok-research-messages"
            ref={messagesContainerRef}
            onScroll={handleScroll}
          >
            {/* Thinking Messages */}
            {thinkingMessages.length > 0 && thinkingMessages.map((msg, idx) => {
              const isLast = idx === thinkingMessages.length - 1;
              const isActive = isLast && !report; // Last message is active only if report hasn't started

              return (
                <div key={`thinking-${idx}`} className="grok-research-thinking">
                  <div className="grok-thinking-icon">
                    {isActive ? (
                      <div className="grok-spinner-small"></div>
                    ) : (
                      <div className="grok-checkmark">✓</div>
                    )}
                  </div>
                  <span className="grok-thinking-text">{msg}</span>
                </div>
              );
            })}

            {/* Show spinner if generating but no messages yet */}
            {isGenerating && thinkingMessages.length === 0 && !report && (
              <div className="grok-research-loading">
                <div className="grok-spinner"></div>
                <p>Starting research analysis...</p>
              </div>
            )}

            {/* Report Content */}
            {report && (
              <div className="grok-research-report">
                <div className="grok-report-header">
                  <h4>Research Report</h4>
                  {recommendation && (
                    <div className={`grok-recommendation-badge grok-recommendation-${recommendation.toLowerCase()}`}>
                      {recommendation}
                    </div>
                  )}
                </div>
                <div className="grok-report-body">
                  <ReactMarkdown>{report}</ReactMarkdown>
                  {isGenerating && <span className="grok-streaming-cursor">▊</span>}
                </div>

                {/* Citations Section */}
                {citations.length > 0 && (
                  <div className="grok-citations">
                    <h5 className="grok-citations-title">Sources & Citations</h5>
                    <div className="grok-citations-list">
                      {citations.map((citation) => (
                        <a
                          key={citation.id}
                          href={citation.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="grok-citation-item"
                        >
                          <span className="grok-citation-number">[{citation.id}]</span>
                          <span className="grok-citation-source">{citation.source}</span>
                          {citation.author && (
                            <span className="grok-citation-author">by {citation.author}</span>
                          )}
                          <span className={`grok-citation-sentiment grok-sentiment-${citation.sentiment.toLowerCase()}`}>
                            {citation.sentiment}
                          </span>
                        </a>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Follow-up Conversation */}
            {followupMessages.map((msg, idx) => (
              <div key={`followup-${idx}`} className={`grok-chat-message ${msg.role}`}>
                <div className="grok-chat-message-content">
                  <ReactMarkdown>{msg.content}</ReactMarkdown>
                </div>
              </div>
            ))}

            {/* Streaming indicator for follow-up */}
            {isFollowupStreaming && followupMessages.length > 0 &&
             followupMessages[followupMessages.length - 1].role === 'assistant' && (
              <span className="grok-streaming-cursor">▊</span>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* Input Container - Always at bottom after report */}
          {report && (
            <div className="grok-research-input-container">
              <input
                type="text"
                className="grok-research-input"
                placeholder="Ask a follow-up question or challenge the report..."
                value={followupInput}
                onChange={(e) => setFollowupInput(e.target.value)}
                onKeyPress={handleFollowupKeyPress}
                disabled={isFollowupStreaming}
              />
              <button
                className="grok-research-send"
                onClick={handleSendFollowup}
                disabled={isFollowupStreaming || !followupInput.trim()}
              >
                {isFollowupStreaming ? 'Sending...' : 'Send'}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default DeepResearch;
