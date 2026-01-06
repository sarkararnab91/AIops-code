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
