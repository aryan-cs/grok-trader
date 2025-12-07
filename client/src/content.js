// Content script that injects the React sidebar into Polymarket event pages

const sidebarWidth = 400;
let container = null;
let iframe = null;
let isCollapsed = false;

// Check if current URL is an event page
function isEventPage() {
  const path = window.location.pathname;
  // Polymarket event pages typically have /event/ or /market/ in the URL
  return path.includes('/event/') || path.includes('/market/');
}

// Show the sidebar
function showSidebar() {
  if (container && container.isConnected) {
    container.style.display = 'block';
    if (!isCollapsed) {
      document.body.style.marginRight = `${sidebarWidth}px`;
    }
    return;
  }

  initSidebar();
}

// Hide the sidebar
function hideSidebar() {
  if (container) {
    container.style.display = 'none';
    document.body.style.marginRight = '0';
  }
}

// Initialize sidebar
function initSidebar() {
  if (container && container.isConnected) return;

  // Adjust page body to make room for sidebar initially
  document.body.style.marginRight = `${sidebarWidth}px`;
  document.body.style.transition = 'margin-right 0.3s ease';

  // Create shadow root container to isolate styles
  container = document.createElement('div');
  container.id = 'grok-trader-root';
  document.body.appendChild(container);

  // Create shadow DOM for style isolation
  const shadowRoot = container.attachShadow({ mode: 'open' });

  // Create iframe for the sidebar
  iframe = document.createElement('iframe');
  iframe.style.cssText = `
    position: fixed;
    top: 0;
    right: 0;
    width: ${sidebarWidth}px;
    height: 100vh;
    border: none;
    z-index: 2147483647;
    pointer-events: all;
  `;
  iframe.src = chrome.runtime.getURL('sidebar.html');

  shadowRoot.appendChild(iframe);

  // Listen for collapse/expand events from the sidebar
  window.addEventListener('message', (event) => {
    if (event.data.type === 'grok-sidebar-collapsed') {
      isCollapsed = true;
      document.body.style.marginRight = '0'; // Remove margin, overlay on top
      iframe.style.width = '70px'; // Just enough for reopen button
    } else if (event.data.type === 'grok-sidebar-expanded') {
      isCollapsed = false;
      document.body.style.marginRight = `${sidebarWidth}px`;
      iframe.style.width = `${sidebarWidth}px`;
    } else if (event.data.type === 'grok-request-url') {
      // Send current URL to the sidebar iframe
      iframe.contentWindow.postMessage({
        type: 'grok-page-url',
        url: window.location.href
      }, '*');
    }
  });

  // Send initial URL to sidebar after it loads
  iframe.addEventListener('load', () => {
    setTimeout(() => {
      iframe.contentWindow.postMessage({
        type: 'grok-page-url',
        url: window.location.href
      }, '*');
    }, 100);
  });
}

// Handle route changes
function handleRouteChange() {
  if (isEventPage()) {
    showSidebar();
    // Send updated URL to sidebar
    if (iframe && iframe.contentWindow) {
      setTimeout(() => {
        iframe.contentWindow.postMessage({
          type: 'grok-page-url',
          url: window.location.href
        }, '*');
      }, 100);
    }
  } else {
    hideSidebar();
  }
}

// Intercept pushState and replaceState to detect SPA navigation
const originalPushState = history.pushState;
const originalReplaceState = history.replaceState;

history.pushState = function(...args) {
  originalPushState.apply(this, args);
  handleRouteChange();
};

history.replaceState = function(...args) {
  originalReplaceState.apply(this, args);
  handleRouteChange();
};

// Listen for popstate (back/forward navigation)
window.addEventListener('popstate', handleRouteChange);

// Track last URL to detect changes
let lastUrl = window.location.href;
function checkUrlChange() {
  const currentUrl = window.location.href;
  if (currentUrl !== lastUrl) {
    lastUrl = currentUrl;
    handleRouteChange();
  }
}

// Poll for URL changes every 500ms (most reliable for SPAs)
setInterval(checkUrlChange, 500);

// Wait for page to load and initialize
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => {
    handleRouteChange();
  });
} else {
  handleRouteChange();
}
