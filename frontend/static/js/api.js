/**
 * API Wrapper for Enterprise Attendance Management System
 */
const API = {
  getToken() {
    return localStorage.getItem("att_auth_token");
  },

  setToken(token) {
    if (token) {
      localStorage.setItem("att_auth_token", token);
    } else {
      localStorage.removeItem("att_auth_token");
    }
  },

  getUser() {
    try {
      const u = localStorage.getItem("att_user");
      return u ? JSON.parse(u) : null;
    } catch {
      return null;
    }
  },

  setUser(user) {
    if (user) {
      localStorage.setItem("att_user", JSON.stringify(user));
    } else {
      localStorage.removeItem("att_user");
    }
  },

  async request(endpoint, options = {}) {
    const token = this.getToken();
    const headers = options.headers || {};

    if (!(options.body instanceof FormData) && !headers["Content-Type"]) {
      headers["Content-Type"] = "application/json";
    }

    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    try {
      const res = await fetch(endpoint, {
        ...options,
        headers
      });

      // Handle session expiration
      if (res.status === 401 && !endpoint.includes("/api/auth/login")) {
        this.setToken(null);
        this.setUser(null);
        window.dispatchEvent(new CustomEvent("auth:expired"));
        throw new Error("Session expired. Please log in again.");
      }

      // If returning binary (e.g. export download)
      const contentType = res.headers.get("content-type");
      if (contentType && (contentType.includes("spreadsheetml") || contentType.includes("csv") || contentType.includes("octet-stream"))) {
        const blob = await res.blob();
        return { success: true, blob, headers: res.headers };
      }

      const data = await res.json();
      return data;
    } catch (err) {
      console.error(`API Error [${endpoint}]:`, err);
      throw err;
    }
  },

  showToast(message, type = "info") {
    const existing = document.querySelector(".toast-notification");
    if (existing) existing.remove();

    const toast = document.createElement("div");
    toast.className = `toast-notification toast-${type}`;
    toast.style.cssText = `
      position: fixed;
      top: 24px;
      right: 24px;
      z-index: 9999;
      padding: 12px 20px;
      border-radius: 8px;
      font-size: 13.5px;
      font-weight: 500;
      color: #fff;
      display: flex;
      align-items: center;
      gap: 10px;
      box-shadow: 0 10px 25px rgba(0,0,0,0.5);
      animation: fadeIn 0.25s ease-out;
      background: ${type === 'success' ? '#10b981' : type === 'error' ? '#ef4444' : type === 'warning' ? '#f59e0b' : '#3b82f6'};
    `;
    toast.textContent = message;
    document.body.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transition = 'opacity 0.3s ease';
      setTimeout(() => toast.remove(), 300);
    }, 4000);
  }
};
