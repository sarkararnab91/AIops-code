# Session 6: Vue.js Frontend & API Gateway

## 📋 Session Details
- **Duration**: 1 hour
- **Week**: 2, Day 1 (Monday)
- **Prerequisites**: Sessions 1-5 completed, all services running
- **Deliverable**: Complete e-commerce UI functional with API gateway

---

## 🎯 Learning Objectives

By the end of this session, you will:
1. Set up a Vue.js frontend for the e-commerce application
2. Configure Kubernetes Ingress as API gateway
3. Connect frontend to backend services
4. Understand frontend observability basics

---

## 📚 Concepts

### Frontend Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              VUE.JS FRONTEND                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                           VIEWS                                      │   │
│   │  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐       │   │
│   │  │   Home     │ │  Products  │ │    Cart    │ │  Checkout  │       │   │
│   │  │   View     │ │   List     │ │    View    │ │    View    │       │   │
│   │  └────────────┘ └────────────┘ └────────────┘ └────────────┘       │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                        COMPOSABLES / STORES                          │   │
│   │  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐       │   │
│   │  │  useAuth   │ │  useCart   │ │ useProducts│ │  useOrders │       │   │
│   │  └────────────┘ └────────────┘ └────────────┘ └────────────┘       │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                          API CLIENT                                  │   │
│   │              Axios with interceptors for auth & error handling       │   │
│   └───────────────────────────────────┬─────────────────────────────────┘   │
│                                       │                                      │
└───────────────────────────────────────┼──────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           KUBERNETES INGRESS                                 │
│                    (API Gateway / Load Balancer)                            │
├─────────────────────────────────────────────────────────────────────────────┤
│  /api/v1/products/*  → Catalog Service                                     │
│  /api/v1/cart/*      → Cart Service                                        │
│  /api/v1/users/*     → User Service                                        │
│  /api/v1/orders/*    → Order Service                                       │
│  /api/v1/payments/*  → Payment Service                                     │
│  /api/v1/inventory/* → Inventory Service                                   │
│  /*                  → Frontend (static files)                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 🛠️ Hands-On Exercise

### Step 1: Create Vue.js Project

```bash
# Navigate to frontend directory
mkdir -p ecommerce-app/frontend
cd ecommerce-app/frontend

# Create Vue.js project with Vite
npm create vite@latest . -- --template vue

# Install dependencies
npm install
npm install axios vue-router@4 pinia @vueuse/core
```

### Step 2: Create API Client

Create `ecommerce-app/frontend/src/api/client.js`:

```javascript
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
```

### Step 3: Create Pinia Stores

Create `ecommerce-app/frontend/src/stores/cart.js`:

```javascript
import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import { cartAPI } from '../api/client';

export const useCartStore = defineStore('cart', () => {
  const items = ref([]);
  const loading = ref(false);
  const error = ref(null);

  const totalItems = computed(() => 
    items.value.reduce((sum, item) => sum + item.quantity, 0)
  );

  const subtotal = computed(() =>
    items.value.reduce((sum, item) => sum + item.price * item.quantity, 0)
  );

  async function fetchCart() {
    loading.value = true;
    error.value = null;
    try {
      const response = await cartAPI.getCart();
      items.value = response.data.items || [];
    } catch (e) {
      error.value = e.response?.data?.detail || 'Failed to fetch cart';
      items.value = [];
    } finally {
      loading.value = false;
    }
  }

  async function addItem(product, quantity = 1) {
    loading.value = true;
    try {
      const response = await cartAPI.addItem({
        product_id: product.id,
        name: product.name,
        price: product.price,
        quantity,
        image_url: product.image_url,
      });
      items.value = response.data.items;
    } catch (e) {
      error.value = e.response?.data?.detail || 'Failed to add item';
      throw e;
    } finally {
      loading.value = false;
    }
  }

  async function updateQuantity(productId, quantity) {
    loading.value = true;
    try {
      if (quantity === 0) {
        await cartAPI.removeItem(productId);
        items.value = items.value.filter(i => i.product_id !== productId);
      } else {
        const response = await cartAPI.updateQuantity(productId, quantity);
        items.value = response.data.items;
      }
    } catch (e) {
      error.value = e.response?.data?.detail || 'Failed to update quantity';
      throw e;
    } finally {
      loading.value = false;
    }
  }

  async function removeItem(productId) {
    loading.value = true;
    try {
      await cartAPI.removeItem(productId);
      items.value = items.value.filter(i => i.product_id !== productId);
    } catch (e) {
      error.value = e.response?.data?.detail || 'Failed to remove item';
      throw e;
    } finally {
      loading.value = false;
    }
  }

  async function clearCart() {
    loading.value = true;
    try {
      await cartAPI.clearCart();
      items.value = [];
    } catch (e) {
      error.value = e.response?.data?.detail || 'Failed to clear cart';
    } finally {
      loading.value = false;
    }
  }

  return {
    items,
    loading,
    error,
    totalItems,
    subtotal,
    fetchCart,
    addItem,
    updateQuantity,
    removeItem,
    clearCart,
  };
});
```

### Step 4: Create Main App Component

Create `ecommerce-app/frontend/src/App.vue`:

```vue
<template>
  <div id="app">
    <nav class="navbar">
      <div class="navbar-brand">
        <router-link to="/" class="logo">
          🛍️ Perfume & Dessert Shop
        </router-link>
      </div>
      
      <div class="navbar-menu">
        <router-link to="/products?category=perfumes">Perfumes</router-link>
        <router-link to="/products?category=desserts">Desserts</router-link>
        <router-link to="/cart" class="cart-link">
          🛒 Cart ({{ cartStore.totalItems }})
        </router-link>
        
        <template v-if="authStore.isAuthenticated">
          <router-link to="/orders">My Orders</router-link>
          <button @click="logout" class="btn-logout">Logout</button>
        </template>
        <template v-else>
          <router-link to="/login">Login</router-link>
          <router-link to="/register">Register</router-link>
        </template>
      </div>
    </nav>
    
    <main class="main-content">
      <router-view />
    </main>
    
    <footer class="footer">
      <p>AIOps Training Demo - Perfume & Dessert E-Commerce</p>
    </footer>
  </div>
</template>

<script setup>
import { onMounted } from 'vue';
import { useRouter } from 'vue-router';
import { useCartStore } from './stores/cart';
import { useAuthStore } from './stores/auth';

const cartStore = useCartStore();
const authStore = useAuthStore();
const router = useRouter();

onMounted(() => {
  if (authStore.isAuthenticated) {
    cartStore.fetchCart();
  }
});

function logout() {
  authStore.logout();
  router.push('/');
}
</script>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  background-color: #f5f5f5;
}

.navbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem 2rem;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
}

.navbar-brand .logo {
  font-size: 1.5rem;
  font-weight: bold;
  color: white;
  text-decoration: none;
}

.navbar-menu {
  display: flex;
  gap: 1.5rem;
  align-items: center;
}

.navbar-menu a {
  color: white;
  text-decoration: none;
  transition: opacity 0.2s;
}

.navbar-menu a:hover {
  opacity: 0.8;
}

.cart-link {
  background: rgba(255,255,255,0.2);
  padding: 0.5rem 1rem;
  border-radius: 20px;
}

.btn-logout {
  background: transparent;
  border: 1px solid white;
  color: white;
  padding: 0.5rem 1rem;
  border-radius: 5px;
  cursor: pointer;
}

.main-content {
  min-height: calc(100vh - 140px);
  padding: 2rem;
}

.footer {
  text-align: center;
  padding: 1rem;
  background: #333;
  color: white;
}
</style>
```

### Step 5: Create Kubernetes Ingress

Create `ecommerce-app/infrastructure/k8s/ingress.yaml`:

```yaml
# Kubernetes Ingress for API Gateway
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: ecommerce-ingress
  namespace: ecommerce
  annotations:
    kubernetes.io/ingress.class: nginx
    nginx.ingress.kubernetes.io/proxy-body-size: "10m"
    nginx.ingress.kubernetes.io/proxy-read-timeout: "60"
    nginx.ingress.kubernetes.io/proxy-send-timeout: "60"
    nginx.ingress.kubernetes.io/cors-allow-origin: "*"
    nginx.ingress.kubernetes.io/enable-cors: "true"
spec:
  rules:
    - http:
        paths:
          # Catalog Service
          - path: /api/v1/products
            pathType: Prefix
            backend:
              service:
                name: catalog-service
                port:
                  number: 8001
          
          # Cart Service
          - path: /api/v1/cart
            pathType: Prefix
            backend:
              service:
                name: cart-service
                port:
                  number: 8004
          
          # User Service
          - path: /api/v1/users
            pathType: Prefix
            backend:
              service:
                name: user-service
                port:
                  number: 8003
          
          # Order Service
          - path: /api/v1/orders
            pathType: Prefix
            backend:
              service:
                name: order-service
                port:
                  number: 8006
          
          # Payment Service
          - path: /api/v1/payments
            pathType: Prefix
            backend:
              service:
                name: payment-service
                port:
                  number: 8005
          
          # Inventory Service
          - path: /api/v1/inventory
            pathType: Prefix
            backend:
              service:
                name: inventory-service
                port:
                  number: 8002
          
          # Frontend (catch-all)
          - path: /
            pathType: Prefix
            backend:
              service:
                name: frontend
                port:
                  number: 80
```

### Step 6: Create Kubernetes Services

Create `ecommerce-app/infrastructure/k8s/services.yaml`:

```yaml
# Kubernetes Services for all microservices
---
apiVersion: v1
kind: Namespace
metadata:
  name: ecommerce
  labels:
    app: ecommerce
    monitoring: enabled

---
# Catalog Service
apiVersion: v1
kind: Service
metadata:
  name: catalog-service
  namespace: ecommerce
spec:
  selector:
    app: catalog-service
  ports:
    - port: 8001
      targetPort: 8001
  type: ClusterIP

---
# Inventory Service
apiVersion: v1
kind: Service
metadata:
  name: inventory-service
  namespace: ecommerce
spec:
  selector:
    app: inventory-service
  ports:
    - port: 8002
      targetPort: 8002
  type: ClusterIP

---
# User Service
apiVersion: v1
kind: Service
metadata:
  name: user-service
  namespace: ecommerce
spec:
  selector:
    app: user-service
  ports:
    - port: 8003
      targetPort: 8003
  type: ClusterIP

---
# Cart Service
apiVersion: v1
kind: Service
metadata:
  name: cart-service
  namespace: ecommerce
spec:
  selector:
    app: cart-service
  ports:
    - port: 8004
      targetPort: 8004
  type: ClusterIP

---
# Payment Service
apiVersion: v1
kind: Service
metadata:
  name: payment-service
  namespace: ecommerce
spec:
  selector:
    app: payment-service
  ports:
    - port: 8005
      targetPort: 8005
  type: ClusterIP

---
# Order Service
apiVersion: v1
kind: Service
metadata:
  name: order-service
  namespace: ecommerce
spec:
  selector:
    app: order-service
  ports:
    - port: 8006
      targetPort: 8006
  type: ClusterIP

---
# Notification Service
apiVersion: v1
kind: Service
metadata:
  name: notification-service
  namespace: ecommerce
spec:
  selector:
    app: notification-service
  ports:
    - port: 8007
      targetPort: 8007
  type: ClusterIP

---
# Frontend Service
apiVersion: v1
kind: Service
metadata:
  name: frontend
  namespace: ecommerce
spec:
  selector:
    app: frontend
  ports:
    - port: 80
      targetPort: 80
  type: ClusterIP
```

### Step 7: Deploy to AKS

```bash
# Install NGINX Ingress Controller
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
helm repo update

helm install ingress-nginx ingress-nginx/ingress-nginx \
  --namespace ingress-nginx \
  --create-namespace \
  --set controller.replicaCount=1

# Wait for ingress controller
kubectl wait --namespace ingress-nginx \
  --for=condition=ready pod \
  --selector=app.kubernetes.io/component=controller \
  --timeout=120s

# Apply namespace and services
kubectl apply -f ecommerce-app/infrastructure/k8s/services.yaml

# Apply ingress
kubectl apply -f ecommerce-app/infrastructure/k8s/ingress.yaml

# Get ingress IP
kubectl get ingress -n ecommerce
```

---

## 🧪 Verification Checklist

Before moving to the next session, ensure you have:

- [ ] Vue.js project created with Vite
- [ ] API client with interceptors
- [ ] Pinia stores for state management
- [ ] Kubernetes services deployed
- [ ] Ingress controller installed
- [ ] Frontend accessible via ingress

---

## 📖 Key Takeaways

1. **API client interceptors** add auth tokens and correlation IDs automatically
2. **Pinia stores** provide reactive state management
3. **Kubernetes Ingress** acts as API gateway routing requests to services
4. **Correlation IDs** enable distributed tracing from frontend to backend

---

## 🔜 Next Session Preview

**Session 7: Application Insights Deep Dive**
- Instrument all services with Application Insights
- Custom metrics and dependency tracking
- Performance monitoring setup

---

## 📚 Additional Resources

- [Vue.js Documentation](https://vuejs.org/)
- [Pinia Documentation](https://pinia.vuejs.org/)
- [Kubernetes Ingress](https://kubernetes.io/docs/concepts/services-networking/ingress/)
- [NGINX Ingress Controller](https://kubernetes.github.io/ingress-nginx/)
