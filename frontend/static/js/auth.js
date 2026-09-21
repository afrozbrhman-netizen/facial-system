/**
 * Authentication and Role-Based UI Access Controller
 */
const Auth = {
  currentUser: null,

  init() {
    this.currentUser = API.getUser();
    this.bindEvents();

    if (this.currentUser && API.getToken()) {
      this.applyUserState(this.currentUser);
    } else {
      this.showLogin();
    }

    window.addEventListener("auth:expired", () => {
      this.showLogin("Session expired. Please log in again.");
    });
  },

  bindEvents() {
    // Login form submit
    const loginForm = document.getElementById("login-form");
    if (loginForm) {
      loginForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const usernameInput = document.getElementById("login-username").value.trim();
        const passwordInput = document.getElementById("login-password").value;
        const errorAlert = document.getElementById("login-error");
        errorAlert.style.display = "none";

        try {
          const res = await API.request("/api/auth/login", {
            method: "POST",
            body: JSON.stringify({ username: usernameInput, password: passwordInput })
          });

          if (res.success && res.token) {
            API.setToken(res.token);
            API.setUser(res.user);
            this.currentUser = res.user;
            this.applyUserState(res.user);
            this.hideLogin();
            API.showToast(`Welcome back, ${res.user.full_name}!`, "success");
            // Trigger initial data load
            window.dispatchEvent(new CustomEvent("app:ready"));
          } else {
            errorAlert.textContent = res.message || "Invalid credentials.";
            errorAlert.style.display = "block";
          }
        } catch (err) {
          errorAlert.textContent = err.message || "Failed to communicate with authentication server.";
          errorAlert.style.display = "block";
        }
      });
    }

    // Logout button
    const logoutBtn = document.getElementById("btn-logout");
    if (logoutBtn) {
      logoutBtn.addEventListener("click", async () => {
        try {
          await API.request("/api/auth/logout", { method: "POST" });
        } catch {}
        API.setToken(null);
        API.setUser(null);
        this.currentUser = null;
        this.showLogin();
      });
    }
  },

  applyUserState(user) {
    // Update user profile in sidebar
    const nameEl = document.getElementById("sidebar-user-name");
    const roleEl = document.getElementById("sidebar-user-role");
    const avatarEl = document.getElementById("sidebar-user-avatar");

    if (nameEl) nameEl.textContent = user.full_name || user.username;

    // Normalize role: handle teacher, faculty, hr, teacher_hr, staff
    const rawRole = (user.role || "").toLowerCase().trim();
    let normalizedRole = rawRole;
    if (["teacher", "faculty", "hr", "teacher_hr", "staff", "instructor", "professor"].includes(rawRole)) {
      normalizedRole = "teacher_hr";
    } else if (["student", "employee", "student_employee"].includes(rawRole)) {
      normalizedRole = "student_employee";
    } else if (rawRole === "admin" || rawRole === "administrator") {
      normalizedRole = "admin";
    }

    if (roleEl) {
      const roleTitles = {
        admin: "Administrator",
        teacher_hr: "Faculty / HR",
        student_employee: "Student / Employee"
      };
      roleEl.textContent = roleTitles[normalizedRole] || user.role;
    }
    if (avatarEl && user.profile_photo_path) {
      avatarEl.innerHTML = `<img src="/${user.profile_photo_path}" alt="${user.full_name}">`;
    }

    // Apply role permissions to nav elements
    document.querySelectorAll("[data-permission]").forEach(el => {
      const permitted = el.dataset.permission.split(",").map(p => p.trim().toLowerCase());
      if (
        permitted.includes(normalizedRole) || 
        permitted.includes(rawRole) ||
        (normalizedRole === "teacher_hr" && (permitted.includes("teacher_hr") || permitted.includes("faculty") || permitted.includes("hr") || permitted.includes("teacher")))
      ) {
        el.style.display = "";
      } else {
        el.style.display = "none";
      }
    });

    // Default tab depending on role
    if (normalizedRole === "student_employee") {
      App.switchTab("records");
    } else {
      App.switchTab("dashboard");
    }
  },

  showLogin(msg = null) {
    const overlay = document.getElementById("login-overlay");
    if (overlay) overlay.style.display = "flex";
    const uInput = document.getElementById("login-username");
    const pInput = document.getElementById("login-password");
    if (uInput) uInput.value = "";
    if (pInput) pInput.value = "";
    const err = document.getElementById("login-error");
    if (err) {
      if (msg) {
        err.textContent = msg;
        err.style.display = "block";
      } else {
        err.textContent = "";
        err.style.display = "none";
      }
    }
  },

  hideLogin() {
    const overlay = document.getElementById("login-overlay");
    if (overlay) overlay.style.display = "none";
  }
};
