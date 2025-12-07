import React, { useState, useEffect, useRef } from 'react';
import './Sidebar.css';
import Chat from './Chat';
import DeepResearch from './DeepResearch';

const Sidebar = () => {
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [wsStatus, setWsStatus] = useState('connecting');
  const [eventSlug, setEventSlug] = useState(null);
  const [activeTab, setActiveTab] = useState('feed');
  const [chatMessages, setChatMessages] = useState([]);
  const [clientId] = useState(() => `client_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`);
  const wsRef = useRef(null);

  // Extract event slug from URL and connect to WebSocket
  useEffect(() => {
    let slug = null;

    // Listen for URL from parent window
    const handleMessage = (event) => {
      if (event.data.type === 'grok-page-url') {
        const url = event.data.url;
        // Extract event slug from URL like https://polymarket.com/event/romania-bucharest-mayoral-election
        const match = url.match(/\/event\/([^/?#]+)/);
        if (match && match[1]) {
          slug = match[1];
          setEventSlug(slug);

          // Send to WebSocket if connected
          if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
            wsRef.current.send(JSON.stringify({ event_slug: slug }));
            console.log('Sent event slug to server:', slug);
          }
        }
      }
    };

    window.addEventListener('message', handleMessage);

    // Request URL from parent
    window.parent.postMessage({ type: 'grok-request-url' }, '*');

    // Connect to WebSocket server
    const connectWebSocket = () => {
      const ws = new WebSocket('ws://localhost:8765/ws');

      ws.onopen = () => {
        console.log('✅ WebSocket connected to ws://localhost:8765/ws');
        setWsStatus('connected');

        // Register client ID
        ws.send(JSON.stringify({
          type: 'register',
          client_id: clientId
        }));
        console.log('📝 Registering client:', clientId);

        // Send event slug to server
        if (slug) {
          ws.send(JSON.stringify({ event_slug: slug }));
          console.log('📤 Sent event slug to server:', slug);
        }
      };

      // Note: Message handling is done in Chat.jsx and DeepResearch.jsx
      // using addEventListener, so we don't set onmessage here

      ws.onerror = (error) => {
        console.error('❌ WebSocket error:', error);
        setWsStatus('error');
      };

      ws.onclose = (event) => {
        console.log(`❌ WebSocket disconnected (code: ${event.code}, reason: ${event.reason || 'none'})`);
        setWsStatus('disconnected');
        // Attempt to reconnect after 3 seconds
        console.log('🔄 Reconnecting in 3 seconds...');
        setTimeout(connectWebSocket, 3000);
      };

      wsRef.current = ws;
    };

    connectWebSocket();

    // Cleanup on unmount
    return () => {
      window.removeEventListener('message', handleMessage);
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, []);

  const handleCollapse = () => {
    setIsCollapsed(true);
    // Notify parent window about collapse state
    window.parent.postMessage({
      type: 'grok-sidebar-collapsed'
    }, '*');
  };

  const handleExpand = () => {
    setIsCollapsed(false);
    // Notify parent window about expand state
    window.parent.postMessage({
      type: 'grok-sidebar-expanded'
    }, '*');
  };

  return (
    <div className="grok-sidebar">
      {isCollapsed ? (
        <button className="grok-reopen-btn" onClick={handleExpand}>
          ‹
        </button>
      ) : (
        <div className="grok-sidebar-content">
          <div className="grok-header">
            <div className="grok-header-content">
              <div className="grok-title-section">
                <img
                  src={chrome?.runtime?.getURL('xAI_Logomark_Light.png') || './xAI_Logomark_Light.png'}
                  alt="xAI Logo"
                  className="grok-logo"
                />
                <div>
                  <h2>Grok Trade</h2>
                </div>
              </div>
              <button className="grok-collapse-btn" onClick={handleCollapse}>
                ›
              </button>
            </div>
            {eventSlug && (
              <p className="grok-event-slug">{eventSlug}</p>
            )}
          </div>

          <div className="grok-tabs">
            <button
              className={`grok-tab ${activeTab === 'feed' ? 'active' : ''}`}
              onClick={() => setActiveTab('feed')}
            >
              Feed
            </button>
            <button
              className={`grok-tab ${activeTab === 'chat' ? 'active' : ''}`}
              onClick={() => setActiveTab('chat')}
            >
              Chat
            </button>
            <button
              className={`grok-tab ${activeTab === 'research' ? 'active' : ''}`}
              onClick={() => setActiveTab('research')}
            >
              Deep Research
            </button>
          </div>

          <div className="grok-body">
            {activeTab === 'feed' && (
              <>
                <div className="grok-section">
                  <h3>Market Analysis</h3>
                  <div className="grok-loading">
                    <div className="grok-spinner"></div>
                    <p>Analyzing market...</p>
                  </div>
                </div>

                <div className="grok-section">
                  <h3>Recommendation</h3>
                  <div className="grok-recommendation-placeholder">
                    <p>Waiting for analysis...</p>
                  </div>
                </div>

                <div className="grok-section">
                  <h3>Key Insights</h3>
                  <ul className="grok-insights-list">
                    <li>Loading insights...</li>
                  </ul>
                </div>
              </>
            )}

            {activeTab === 'chat' && (
              <Chat
                websocket={wsRef.current}
                clientId={clientId}
                eventSlug={eventSlug}
                chatMessages={chatMessages}
                setChatMessages={setChatMessages}
              />
            )}

            {activeTab === 'research' && (
              <DeepResearch
                eventSlug={eventSlug}
                websocket={wsRef.current}
                clientId={clientId}
              />
            )}
          </div>
      </div>
      )}
    </div>
  );
};

export default Sidebar;
