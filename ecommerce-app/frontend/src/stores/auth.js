import { defineStore } from 'pinia';
import { ref } from 'vue';

export const useAuthStore = defineStore('auth', () => {
    const isAuthenticated = ref(!!localStorage.getItem('auth_token'));
    
    function login(token) {
        localStorage.setItem('auth_token', token);
        isAuthenticated.value = true;
    }
    
    function logout() {
        localStorage.removeItem('auth_token');
        isAuthenticated.value = false;
    }
    
    return {
        isAuthenticated,
        login,
        logout
    };
});
