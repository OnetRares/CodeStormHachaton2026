import { useState } from 'react';
import Login from './Login';
import Dashboard from './Dashboard'; // Pasul 1 din poza ta

export default function App() {
  // Această stare decide dacă utilizatorul a trecut de login
  const [isAuthenticated, setIsAuthenticated] = useState(false);

  const handleLoginSuccess = () => {
    setIsAuthenticated(true); // Schimbăm starea în "adevărat"
  };

  const handleLogout = () => {
    setIsAuthenticated(false); // Revenim la login
  };

  return (
    <main>
      {/* Aceasta este logica de "Routing" manuală */}
      {isAuthenticated ? (
        <Dashboard onLogout={handleLogout} />
      ) : (
        <Login onLoginSuccess={handleLoginSuccess} />
      )}
    </main>
  );
}