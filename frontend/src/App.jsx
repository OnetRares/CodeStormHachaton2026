import { useState } from 'react';
import Login from './Login';
import Dashboard from './Dashboard';
import './App.css';

const AssistantIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <rect x="4" y="7" width="16" height="12" rx="4" />
    <path d="M12 4v3" />
    <circle cx="9" cy="13" r="1" />
    <circle cx="15" cy="13" r="1" />
    <path d="M9 16h6" />
  </svg>
);

export default function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false);

  const handleLoginSuccess = () => {
    setIsAuthenticated(true);
  };

  const handleLogout = () => {
    setIsAuthenticated(false);
  };

  return (
    <main className="appShell">
      {isAuthenticated ? (
        <Dashboard onLogout={handleLogout} />
      ) : (
        <Login onLoginSuccess={handleLoginSuccess} />
      )}

      <button
        type="button"
        className="assistantFab"
        aria-label="AI Assistant (coming soon)"
        title="AI Assistant (coming soon)"
      >
        <span className="assistantPulse" aria-hidden="true" />
        <span className="assistantIconWrap">
          <AssistantIcon />
        </span>
        <span className="assistantText">
          <strong>AI Assistant</strong>
          <small>Coming soon</small>
        </span>
      </button>
    </main>
  );
}
