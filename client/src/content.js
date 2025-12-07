// Content script that injects the React sidebar into Polymarket event pages

// Wait for page to load
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initSidebar);
} else {
  initSidebar();
}

function initSidebar() {
  const sidebarWidth = 400;

  // Adjust page body to make room for sidebar
  document.body.style.marginRight = `${sidebarWidth}px`;
  document.body.style.transition = 'margin-right 0.3s ease';

  // Create shadow root container to isolate styles
  const container = document.createElement('div');
  container.id = 'grok-trader-root';
  document.body.appendChild(container);

  // Create shadow DOM for style isolation
  const shadowRoot = container.attachShadow({ mode: 'open' });

  // Create iframe for the sidebar
  const iframe = document.createElement('iframe');
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
      document.body.style.marginRight = '0';
    } else if (event.data.type === 'grok-sidebar-expanded') {
      document.body.style.marginRight = `${sidebarWidth}px`;
    }
  });
}
