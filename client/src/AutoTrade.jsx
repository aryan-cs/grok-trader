import React, { useState, useEffect } from 'react';

const AutoTrade = ({ eventSlug, selectedMarket, clientId }) => {
  const [autoTrade, setAutoTrade] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Form state
  const [xHandles, setXHandles] = useState('');
  const [condition, setCondition] = useState('');
  const [amount, setAmount] = useState('');
  const [limit, setLimit] = useState('');

  // Fetch auto trade for the selected market
  const fetchAutoTrade = async () => {
    if (!selectedMarket) return;

    setLoading(true);
    setError(null);

    try {
      const response = await fetch(`http://localhost:8765/autotrade/market/${encodeURIComponent(selectedMarket)}`);
      const data = await response.json();

      if (data.auto_trade) {
        setAutoTrade(data.auto_trade);
      } else {
        setAutoTrade(null);
      }
    } catch (err) {
      console.error('Error fetching auto trade:', err);
      setError('Failed to load auto trade');
    } finally {
      setLoading(false);
    }
  };

  // Load auto trade when market changes or tab is focused
  useEffect(() => {
    fetchAutoTrade();
  }, [selectedMarket]);

  // Handle form submission
  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    // Parse X handles (comma or newline separated)
    const handlesArray = xHandles
      .split(/[,\n]/)
      .map(h => h.trim())
      .filter(h => h.length > 0);

    if (handlesArray.length === 0) {
      setError('Please enter at least one X handle');
      setLoading(false);
      return;
    }

    try {
      const response = await fetch('http://localhost:8765/autotrade/start', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          client_id: clientId,
          market_slug: selectedMarket,
          x_handles: handlesArray,
          condition: condition,
          amount: parseFloat(amount),
          limit: parseFloat(limit),
        }),
      });

      const data = await response.json();

      if (data.status === 'success') {
        // Reload to show the active auto trade
        fetchAutoTrade();
        // Clear form
        setXHandles('');
        setCondition('');
        setAmount('');
        setLimit('');
      } else {
        setError(data.message || 'Failed to start auto trade');
      }
    } catch (err) {
      console.error('Error starting auto trade:', err);
      setError('Failed to start auto trade');
    } finally {
      setLoading(false);
    }
  };

  // Handle stop auto trade
  const handleStop = async () => {
    if (!autoTrade) return;

    setLoading(true);
    setError(null);

    try {
      const response = await fetch(`http://localhost:8765/autotrade/stop/${autoTrade.id}`, {
        method: 'POST',
      });

      const data = await response.json();

      if (data.status === 'stopped') {
        // Reload to show the form again
        fetchAutoTrade();
      } else {
        setError(data.message || 'Failed to stop auto trade');
      }
    } catch (err) {
      console.error('Error stopping auto trade:', err);
      setError('Failed to stop auto trade');
    } finally {
      setLoading(false);
    }
  };

  // Show message if no market selected
  if (!selectedMarket) {
    return (
      <div className="grok-auto-trade">
        <div className="grok-section">
          <h3>Auto Trader</h3>
          <p className="grok-auto-trade-description">
            <i>Select a market above to get started with auto trade.</i>
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="grok-auto-trade">
      <div className="grok-section">
        <h3>Auto Trader</h3>
        <p className="grok-auto-trade-description">
          <i>Automatically execute trades based on X activity and conditions.</i>
        </p>
      </div>

      {error && (
        <div className="grok-section">
          <div className="grok-error-message">{error}</div>
        </div>
      )}

      {loading && (
        <div className="grok-section">
          <div className="grok-loading">
            <div className="grok-spinner"></div>
            <p>Loading...</p>
          </div>
        </div>
      )}

      {!loading && autoTrade && (
        <div className="grok-section">
          <div className="grok-auto-trade-active">
            <h4>Active Auto Trade</h4>
            <p className="grok-auto-trade-id">ID: {autoTrade.id}</p>

            <div className="grok-auto-trade-details">
              <div className="grok-auto-trade-detail">
                <strong>Watching:</strong>
                <span>{autoTrade.x_handles.join(', ')}</span>
              </div>
              <div className="grok-auto-trade-detail">
                <strong>Condition:</strong>
                <span>{autoTrade.condition}</span>
              </div>
              <div className="grok-auto-trade-detail">
                <strong>Amount:</strong>
                <span>${autoTrade.amount}</span>
              </div>
              <div className="grok-auto-trade-detail">
                <strong>Limit Price:</strong>
                <span>{autoTrade.limit}</span>
              </div>
            </div>

            <p className="grok-auto-trade-status">
              Status: <span className="grok-status-active">Monitoring</span>
            </p>
            <button
              className="grok-stop-autotrade-btn"
              onClick={handleStop}
              disabled={loading}
            >
              Stop Auto Trade
            </button>
          </div>
        </div>
      )}

      {!loading && !autoTrade && (
        <form onSubmit={handleSubmit}>
          <div className="grok-section">
            <label className="grok-input-label">X Handles to Monitor</label>
            <textarea
              className="grok-textarea"
              placeholder="Enter X handles (comma or newline separated)&#10;Example: @elonmusk, @paulg, @sama"
              value={xHandles}
              onChange={(e) => setXHandles(e.target.value)}
              rows={3}
              required
            />
          </div>

          <div className="grok-section">
            <label className="grok-input-label">Condition</label>
            <textarea
              className="grok-textarea"
              placeholder="Describe the condition that triggers the trade&#10;Example: Elon tweets that Tesla will acquire xAI"
              value={condition}
              onChange={(e) => setCondition(e.target.value)}
              rows={3}
              required
            />
          </div>

          <div className="grok-section">
            <label className="grok-input-label">Amount ($)</label>
            <input
              type="number"
              className="grok-input"
              placeholder="Dollar amount to trade"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              step="0.01"
              min="0"
              required
            />
          </div>

          <div className="grok-section">
            <label className="grok-input-label">Limit Price</label>
            <input
              type="number"
              className="grok-input"
              placeholder="Maximum price per contract"
              value={limit}
              onChange={(e) => setLimit(e.target.value)}
              step="0.01"
              min="0"
              max="1"
              required
            />
          </div>

            <button
              type="submit"
              className="grok-start-autotrade-btn"
              disabled={loading}
            >
              Start Auto Trade
            </button>
        </form>
      )}
    </div>
  );
};

export default AutoTrade;
