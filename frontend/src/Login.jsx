import { useState } from 'react';
import styles from './Login.module.css';
import { mockLoginAPI, mockRegisterAPI } from './services/mockApi';

export default function Login({ onLoginSuccess }) {
  const [isRegister, setIsRegister] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [formData, setFormData] = useState({
    username: '',
    email: '',
    password: '',
    confirmPassword: '',
  });

  const handleInputChange = (e) => {
    const { name, value } = e.target;
    setFormData((prev) => ({
      ...prev,
      [name]: value,
    }));
    // Clear error and success messages when user starts typing
    setError('');
    setSuccess('');
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setSuccess('');

    // Client-side validation
    if (isRegister) {
      if (formData.password !== formData.confirmPassword) {
        setError('Passwords do not match!');
        return;
      }
    }

    // Set loading state
    setLoading(true);

    try {
      if (isRegister) {
        // Call mock register API
        const response = await mockRegisterAPI({
          username: formData.username,
          email: formData.email,
          password: formData.password,
        });
        setSuccess(response.message);
        console.log('Register successful:', response);
        
        // Reset form after successful registration
        setFormData({
          username: '',
          email: '',
          password: '',
          confirmPassword: '',
        });
        
        // Switch to login mode after 2 seconds
        setTimeout(() => {
          setIsRegister(false);
          setSuccess('');
        }, 2000);
      } else {
        // Call mock login API
        const response = await mockLoginAPI({
          username: formData.username,
          password: formData.password,
        });
        setSuccess(response.message);
        console.log('Login successful:', response);
        
        // Call the onLoginSuccess callback to update parent component
        onLoginSuccess();
        
        // Reset form after successful login
        setFormData({
          username: '',
          email: '',
          password: '',
          confirmPassword: '',
        });
      }
    } catch (err) {
      setError(err.message || 'An error occurred. Please try again.');
      console.error('Authentication error:', err);
    } finally {
      setLoading(false);
    }
  };

  const toggleMode = () => {
    setIsRegister(!isRegister);
    setFormData({
      username: '',
      email: '',
      password: '',
      confirmPassword: '',
    });
    setError('');
    setSuccess('');
  };

  return (
    <div className={styles.container}>
      <div className={styles.card}>
        <h1 className={styles.title}>
          {isRegister ? 'Create Account' : 'Welcome back'}
        </h1>
        <p className={styles.subtitle}>
          {isRegister
            ? 'Join us today to get started'
            : 'Sign in to your account'}
        </p>

        {error && <div className={styles.errorMessage}>{error}</div>}
        {success && <div className={styles.successMessage}>{success}</div>}

        <form onSubmit={handleSubmit} className={styles.form}>
          <div className={styles.formGroup}>
            <label htmlFor="username" className={styles.label}>
              Username
            </label>
            <input
              type="text"
              id="username"
              name="username"
              value={formData.username}
              onChange={handleInputChange}
              placeholder="Enter your username"
              className={styles.input}
              required
              disabled={loading}
            />
          </div>

          {isRegister && (
            <div className={styles.formGroup}>
              <label htmlFor="email" className={styles.label}>
                Email
              </label>
              <input
                type="email"
                id="email"
                name="email"
                value={formData.email}
                onChange={handleInputChange}
                placeholder="Enter your email"
                className={styles.input}
                required
                disabled={loading}
              />
            </div>
          )}

          <div className={styles.formGroup}>
            <label htmlFor="password" className={styles.label}>
              Password
            </label>
            <input
              type="password"
              id="password"
              name="password"
              value={formData.password}
              onChange={handleInputChange}
              placeholder="Enter your password"
              className={styles.input}
              required
              disabled={loading}
            />
          </div>

          {isRegister && (
            <div className={styles.formGroup}>
              <label htmlFor="confirmPassword" className={styles.label}>
                Confirm Password
              </label>
              <input
                type="password"
                id="confirmPassword"
                name="confirmPassword"
                value={formData.confirmPassword}
                onChange={handleInputChange}
                placeholder="Confirm your password"
                className={styles.input}
                required
                disabled={loading}
              />
            </div>
          )}

          <button 
            type="submit" 
            className={styles.button}
            disabled={loading}
          >
            {loading ? 'Processing...' : (isRegister ? 'Register' : 'Sign In')}
          </button>
        </form>

        <div className={styles.footer}>
          <p className={styles.toggleText}>
            {isRegister ? 'Already have an account? ' : "Don't have an account? "}
            <button
              type="button"
              onClick={toggleMode}
              className={styles.toggleLink}
              disabled={loading}
            >
              {isRegister ? 'Sign In' : 'Register'}
            </button>
          </p>
        </div>
      </div>
    </div>
  );
}
