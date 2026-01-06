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
