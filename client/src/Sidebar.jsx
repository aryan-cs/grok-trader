import React, { useState, useEffect, useRef } from 'react';
import './Sidebar.css';
import Chat from './Chat';
import DeepResearch from './DeepResearch';
import AutoTrade from './AutoTrade';

const Sidebar = () => {
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [wsStatus, setWsStatus] = useState('connecting');
  const [eventSlug, setEventSlug] = useState(null);
  const [activeTab, setActiveTab] = useState('feed');
  const [chatMessages, setChatMessages] = useState([]);
  const [sentimentItems, setSentimentItems] = useState([]);
  const [feedLoading, setFeedLoading] = useState(true);
  const [clientId] = useState(() => `client_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`);
  const [marketSlugs, setMarketSlugs] = useState([]);
  const [selectedMarket, setSelectedMarket] = useState(null);
  const [loadingMarkets, setLoadingMarkets] = useState(false);
  const wsRef = useRef(null);
  const previousEventSlug = useRef(null);

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

  // Listen for feed (sentiment items) messages
  useEffect(() => {
    const ws = wsRef.current;
    if (!ws) return;

    const handleFeedMessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.message_type !== 'feed') return;

        console.log('📥 Feed message received:', data);

        if (data.type === 'sentiment_items') {
          setSentimentItems(data.items || []);
          setFeedLoading(false);
        } else if (data.type === 'sentiment_item') {
          setSentimentItems(prev => {
            // Avoid duplicates based on link or content
            const exists = prev.some(p => p.link === data.item.link && p.content === data.item.content);
            if (exists) return prev;
            return [...prev, data.item];
          });
          setFeedLoading(false);
        } else if (data.type === 'error') {
          console.error('⚠️ Feed error message:', data.error);
          setFeedLoading(false);
        }
      } catch (err) {
        console.error('Error parsing feed message:', err);
      }
    };

    ws.addEventListener('message', handleFeedMessage);
    return () => ws.removeEventListener('message', handleFeedMessage);
  }, [wsStatus]);

  // Fetch market slugs when event slug changes
  useEffect(() => {
    const fetchMarkets = async () => {
      if (!eventSlug) {
        setMarketSlugs([]);
        setSelectedMarket(null);
        return;
      }

      setLoadingMarkets(true);
      try {
        const response = await fetch(`http://localhost:8765/market-slugs?event_slug=${encodeURIComponent(eventSlug)}`);
        const data = await response.json();

        if (data.status === 'success') {
          setMarketSlugs(data.market_slugs);
          // Auto-select the first market so feed can populate immediately
          if (!selectedMarket && data.market_slugs.length > 0) {
            setSelectedMarket(data.market_slugs[0]);
          }
          console.log('📊 Fetched markets:', data.market_slugs);
        } else {
          console.error('Error fetching markets:', data.error);
          setMarketSlugs([]);
        }
      } catch (error) {
        console.error('Error fetching markets:', error);
        setMarketSlugs([]);
      } finally {
        setLoadingMarkets(false);
      }
    };

    fetchMarkets();
  }, [eventSlug]);

  // When a market is selected and WebSocket is ready, request feed data immediately
  useEffect(() => {
    if (!selectedMarket) return;
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;

    setFeedLoading(true);
    setSentimentItems([]);

    wsRef.current.send(JSON.stringify({
      type: 'feed_request',
      market_title: selectedMarket,
      client_id: clientId,
    }));

    console.log('📤 Sent feed request for market:', selectedMarket, 'client:', clientId);
  }, [selectedMarket, wsStatus]);

  // Reset state when navigating to a new event
  useEffect(() => {
    if (eventSlug && previousEventSlug.current && eventSlug !== previousEventSlug.current) {
      // New event detected, reset state
      setActiveTab('feed');
      setChatMessages([]);
      setSelectedMarket(null);
      setSentimentItems([]);
      setFeedLoading(false);
      console.log('🔄 Navigated to new event, resetting state:', eventSlug);
    }
    previousEventSlug.current = eventSlug;
  }, [eventSlug]);

  const handleResearchStart = () => {
    setFeedLoading(true);
    setSentimentItems([]);
  };

  // Failsafe: if feed loading hangs, stop spinner after 12s
  useEffect(() => {
    if (!feedLoading) return;
    const t = setTimeout(() => {
      console.warn('⏳ Feed loading timed out; stopping spinner');
      setFeedLoading(false);
    }, 12000);
    return () => clearTimeout(t);
  }, [feedLoading]);

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
              <>
                <p className="grok-event-slug">{eventSlug}</p>
                <div className="grok-market-selector">
                  {loadingMarkets ? (
                    <select className="grok-market-select" disabled>
                      <option>Loading markets...</option>
                    </select>
                  ) : (
                    <select
                      className="grok-market-select"
                      value={selectedMarket || ''}
                      onChange={(e) => setSelectedMarket(e.target.value || null)}
                    >
                      <option value="">Select a market to get started</option>
                      {marketSlugs.map((slug) => (
                        <option key={slug} value={slug}>
                          {slug}
                        </option>
                      ))}
                    </select>
                  )}
                </div>
              </>
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
            <button
              className={`grok-tab ${activeTab === 'autotrade' ? 'active' : ''}`}
              onClick={() => setActiveTab('autotrade')}
            >
              Auto Trader
            </button>
          </div>

          <div className="grok-body">
            {activeTab === 'feed' && (
              <>
                <div className="grok-section">
                  <h3>Market Analysis</h3>
                  {feedLoading ? (
                    <div className="grok-loading">
                      <div className="grok-spinner"></div>
                      <p>Analyzing market...</p>
                    </div>
                  ) : sentimentItems.length === 0 ? (
                    <div className="grok-placeholder">No signals yet. Signals load automatically when a market is selected.</div>
                  ) : (
                    <div className="grok-feed-list">
                      {sentimentItems.map((item, idx) => {
                        const sentiment = (item.sentiment || 'neutral').toLowerCase();
                        const source = item.source || 'tweet';
                        const author = item.meta || item.username || 'unknown';
                        const label = `${source} • ${author}`;
                        return (
                          <div
                            key={item.link || `${source}-${idx}`}
                            className={`grok-feed-card sentiment-${sentiment}`}
                          >
                            <div className="grok-feed-card-header">
                              <span className="grok-feed-source">{label}</span>
                              <span className={`grok-feed-pill sentiment-${sentiment}`}>
                                {(item.sentiment || 'neutral').toUpperCase()}
                              </span>
                            </div>
                            <div className="grok-feed-text">{item.content}</div>
                            {item.reasoning && (
                              <div className="grok-feed-reason">{item.reasoning}</div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  )}
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
                selectedMarket={selectedMarket}
                websocket={wsRef.current}
                clientId={clientId}
                onResearchStart={handleResearchStart}
              />
            )}

            {activeTab === 'autotrade' && (
              <AutoTrade
                eventSlug={eventSlug}
                selectedMarket={selectedMarket}
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
