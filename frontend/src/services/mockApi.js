/**
 * Mock API Service
 * Simulates backend API calls with 1-second network latency
 */

// Simulated user database (in-memory storage)
let mockUserDatabase = [];

/**
 * Mock Login API
 * Simulates authentication by checking if user exists and password matches
 * @param {Object} credentials - { username, password }
 * @returns {Promise<Object>} - User data on success
 * @throws {Error} - If credentials are invalid
 */
export const mockLoginAPI = async (credentials) => {
  return new Promise((resolve, reject) => {
    setTimeout(() => {
      const { username, password } = credentials;

      // Validate input
      if (!username || !password) {
        reject(new Error('Username and password are required'));
        return;
      }

      // Check if user exists in mock database
      const user = mockUserDatabase.find((u) => u.username === username);

      if (!user) {
        reject(new Error('Username not found. Please register first.'));
        return;
      }

      // Check password
      if (user.password !== password) {
        reject(new Error('Invalid password'));
        return;
      }

      // Success: return user data (excluding password)
      resolve({
        id: user.id,
        username: user.username,
        email: user.email,
        message: 'Login successful!',
      });
    }, 1000); // 1-second delay to simulate network latency
  });
};

/**
 * Mock Register API
 * Simulates user registration by storing user data
 * @param {Object} userData - { username, email, password }
 * @returns {Promise<Object>} - Registered user data on success
 * @throws {Error} - If user already exists or validation fails
 */
export const mockRegisterAPI = async (userData) => {
  return new Promise((resolve, reject) => {
    setTimeout(() => {
      const { username, email, password } = userData;

      // Validate input
      if (!username || !email || !password) {
        reject(new Error('All fields are required'));
        return;
      }

      // Check if username already exists
      const userExists = mockUserDatabase.some((u) => u.username === username);
      if (userExists) {
        reject(new Error('Username already exists. Please choose another.'));
        return;
      }

      // Check if email already exists
      const emailExists = mockUserDatabase.some((u) => u.email === email);
      if (emailExists) {
        reject(new Error('Email already registered. Please use another email.'));
        return;
      }

      // Validate email format
      const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
      if (!emailRegex.test(email)) {
        reject(new Error('Please enter a valid email address'));
        return;
      }

      // Create new user
      const newUser = {
        id: Date.now(), // Simple ID generation
        username,
        email,
        password, // In production, this would be hashed
      };

      // Add to mock database
      mockUserDatabase.push(newUser);

      // Success: return user data (excluding password)
      resolve({
        id: newUser.id,
        username: newUser.username,
        email: newUser.email,
        message: 'Registration successful! You can now log in.',
      });
    }, 1000); // 1-second delay to simulate network latency
  });
};

/**
 * Clear mock database (for testing/demo purposes)
 */
export const clearMockDatabase = () => {
  mockUserDatabase = [];
};

/**
 * Get all registered users (for testing/demo purposes)
 */
export const getMockDatabaseUsers = () => {
  return mockUserDatabase.map(({ id, username, email }) => ({
    id,
    username,
    email,
  }));
};
