import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '';

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 10000,
});

// Request interceptor - add auth token
apiClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('auth_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    
    // Add correlation ID for distributed tracing
    config.headers['X-Correlation-ID'] = crypto.randomUUID();
    
    return config;
  },
  (error) => Promise.reject(error)
);

// Response interceptor - handle errors
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('auth_token');
      window.location.href = '/login';
    }
    
    console.error('API Error:', {
      url: error.config?.url,
      status: error.response?.status,
      message: error.response?.data?.detail || error.message,
    });
    
    return Promise.reject(error);
  }
);

// API endpoints
export const catalogAPI = {
  getProducts: (params = {}) => apiClient.get('/api/v1/products/', { params }),
  getProduct: (id, category) => apiClient.get(`/api/v1/products/${id}`, { params: { category } }),
  searchProducts: (query) => apiClient.get('/api/v1/products/search', { params: { q: query } }),
  getCategories: () => apiClient.get('/api/v1/products/categories/list'),
};

export const cartAPI = {
  getCart: () => apiClient.get('/api/v1/cart'),
  addItem: (item) => apiClient.post('/api/v1/cart/items', item),
  updateQuantity: (productId, quantity) => apiClient.put(`/api/v1/cart/items/${productId}`, { quantity }),
  removeItem: (productId) => apiClient.delete(`/api/v1/cart/items/${productId}`),
  clearCart: () => apiClient.delete('/api/v1/cart'),
};

export const userAPI = {
  register: (data) => apiClient.post('/api/v1/users/register', data),
  login: (data) => apiClient.post('/api/v1/users/login', data),
  getProfile: () => apiClient.get('/api/v1/users/me'),
  updateProfile: (data) => apiClient.put('/api/v1/users/me', data),
};

export const orderAPI = {
  createOrder: (data) => apiClient.post('/api/v1/orders', data),
  getOrders: () => apiClient.get('/api/v1/orders'),
  getOrder: (id) => apiClient.get(`/api/v1/orders/${id}`),
  cancelOrder: (id) => apiClient.post(`/api/v1/orders/${id}/cancel`),
};

export const paymentAPI = {
  createPayment: (data) => apiClient.post('/api/v1/payments', data),
  processPayment: (paymentId, orderId) => apiClient.post(`/api/v1/payments/${paymentId}/process`, null, { params: { order_id: orderId } }),
};

export default apiClient;
