import React, { useState } from 'react';
import './Sidebar.css';

const Sidebar = () => {
  const [isCollapsed, setIsCollapsed] = useState(false);

  const toggleSidebar = () => {
    const newCollapsed = !isCollapsed;
    setIsCollapsed(newCollapsed);

    // Notify parent window about collapse state
    window.parent.postMessage({
      type: newCollapsed ? 'grok-sidebar-collapsed' : 'grok-sidebar-expanded'
    }, '*');
  };

  return (
    <div className={`grok-sidebar ${isCollapsed ? 'collapsed' : ''}`}>
      <button className="grok-toggle-btn" onClick={toggleSidebar}>
        {isCollapsed ? '◀' : '▶'}
      </button>

      <div className="grok-sidebar-content">
        <div className="grok-header">
          <h2>Grok Trade</h2>
          <p className="grok-subtitle">AI Market Analysis</p>
        </div>

        <div className="grok-body">
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
        </div>

        <div className="grok-footer">
          <p className="grok-disclaimer">
            Powered by Grok AI • Not financial advice
          </p>
        </div>
      </div>
    </div>
  );
};

export default Sidebar;
