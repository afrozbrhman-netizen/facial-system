/**
 * Main Application Orchestrator and Navigation Router
 */
const App = {
  currentTab: "dashboard",

  init() {
    this.initMobileLayout();
    this.bindNavigation();
    Auth.init();
    Scanner.init();

    window.addEventListener("app:ready", () => {
      this.initTabModules();
    });

    if (Auth.currentUser && API.getToken()) {
      this.initTabModules();
    }
  },

  initMobileLayout() {
    const isAndroid = /Android/i.test(navigator.userAgent);
    const isMobile = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent) || window.innerWidth <= 768;

    if (isAndroid) {
      document.body.classList.add("is-android");
    }
    if (isMobile) {
      document.body.classList.add("is-mobile");
    }

    // Toggle Mobile Sidebar Drawer
    const btnMobileMenu = document.getElementById("btn-mobile-menu");
    const btnSidebarClose = document.getElementById("btn-sidebar-close");
    const sidebarBackdrop = document.getElementById("sidebar-backdrop");
    const sidebar = document.getElementById("app-sidebar") || document.querySelector(".sidebar");

    const openSidebar = () => {
      if (sidebar) sidebar.classList.add("mobile-open");
      if (sidebarBackdrop) sidebarBackdrop.classList.add("active");
    };

    const closeSidebar = () => {
      if (sidebar) sidebar.classList.remove("mobile-open");
      if (sidebarBackdrop) sidebarBackdrop.classList.remove("active");
    };

    if (btnMobileMenu) {
      btnMobileMenu.addEventListener("click", () => {
        if (sidebar && sidebar.classList.contains("mobile-open")) {
          closeSidebar();
        } else {
          openSidebar();
        }
      });
    }

    if (btnSidebarClose) {
      btnSidebarClose.addEventListener("click", closeSidebar);
    }

    if (sidebarBackdrop) {
      sidebarBackdrop.addEventListener("click", closeSidebar);
    }

    // Password visibility toggle
    const btnTogglePassword = document.getElementById("btn-toggle-password");
    const passwordInput = document.getElementById("login-password");
    const eyeIcon = document.getElementById("pw-eye-icon");

    if (btnTogglePassword && passwordInput) {
      btnTogglePassword.addEventListener("click", () => {
        const isPassword = passwordInput.type === "password";
        passwordInput.type = isPassword ? "text" : "password";
        if (eyeIcon) {
          eyeIcon.innerHTML = isPassword
            ? `<path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"></path><line x1="1" y1="1" x2="23" y2="23"></line>`
            : `<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle>`;
        }
      });
    }

    // Auto-close sidebar on window resize if resized to desktop
    window.addEventListener("resize", () => {
      if (window.innerWidth > 768) {
        closeSidebar();
      }
    });
  },

  bindNavigation() {
    document.querySelectorAll(".nav-item[data-tab]").forEach(link => {
      link.addEventListener("click", (e) => {
        e.preventDefault();
        const tab = link.dataset.tab;
        this.switchTab(tab);
      });
    });
  },

  switchTab(tabName) {
    this.currentTab = tabName;

    // Automatically manage mobile interface: close sidebar on tab switch
    if (window.innerWidth <= 768) {
      const sidebar = document.getElementById("app-sidebar") || document.querySelector(".sidebar");
      const sidebarBackdrop = document.getElementById("sidebar-backdrop");
      if (sidebar) sidebar.classList.remove("mobile-open");
      if (sidebarBackdrop) sidebarBackdrop.classList.remove("active");
    }

    // Update active state in nav
    document.querySelectorAll(".nav-item").forEach(el => {
      if (el.dataset.tab === tabName) {
        el.classList.add("active");
      } else {
        el.classList.remove("active");
      }
    });

    // Update active tab pane
    document.querySelectorAll(".tab-pane").forEach(pane => {
      if (pane.id === `tab-${tabName}`) {
        pane.classList.add("active");
      } else {
        pane.classList.remove("active");
      }
    });

    // Update top header title
    const titles = {
      dashboard: "Executive Attendance Overview",
      scanner: "Biometric Camera Attendance Terminal",
      employees: "Student & Employee Directory",
      records: "Attendance Activity & History",
      reports: "Export Center & Compliance Reports",
      settings: "System Configuration & Shift Rules",
      audit: "Security Audit Trail & Activity Logs"
    };
    const titleEl = document.getElementById("header-title-text");
    if (titleEl) titleEl.textContent = titles[tabName] || "Attendance Studio";

    // Manage camera automatically: stop if leaving scanner tab
    if (tabName !== "scanner" && Scanner.isScanning) {
      Scanner.stopCamera();
    }

    // Refresh data when switching to specific tabs
    if (tabName === "dashboard" && typeof Dashboard !== "undefined") {
      Dashboard.loadSummary();
    } else if (tabName === "employees" && typeof Employees !== "undefined") {
      Employees.loadEmployees();
    } else if (tabName === "records" && typeof Records !== "undefined") {
      Records.loadRecords();
    } else if (tabName === "reports" && typeof Reports !== "undefined") {
      Reports.loadLowAttendance();
    } else if (tabName === "settings" && typeof Settings !== "undefined") {
      Settings.loadRules();
      Settings.loadDepartments();
    } else if (tabName === "audit" && typeof Settings !== "undefined") {
      Settings.loadAuditLogs();
    }
  },

  initTabModules() {
    Dashboard.init();
    Employees.init();
    Records.init();
    Settings.init();
    if (typeof Reports !== "undefined") Reports.init();
  }
};

/**
 * Reports & Compliance Module
 */
const Reports = {
  async init() {
    this.bindEvents();
    await this.loadLowAttendance();
  },

  bindEvents() {
    const btnLowExcel = document.getElementById("btn-export-low-excel");
    const btnLowCsv = document.getElementById("btn-export-low-csv");

    if (btnLowExcel) btnLowExcel.addEventListener("click", () => this.exportLow("excel"));
    if (btnLowCsv) btnLowCsv.addEventListener("click", () => this.exportLow("csv"));
  },

  async loadLowAttendance() {
    const tbody = document.getElementById("low-att-tbody");
    if (!tbody) return;

    try {
      const res = await API.request("/api/reports/low-attendance?threshold=75");
      if (!res.success || !res.low_attendance.length) {
        tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--text-dim); padding: 25px;">Excellent! No students or employees currently have low attendance (&lt; 75%).</td></tr>`;
        return;
      }

      tbody.innerHTML = res.low_attendance.map(item => `
        <tr>
          <td><code style="color: var(--accent);">${item.employee_code}</code></td>
          <td><strong>${item.full_name}</strong></td>
          <td>${item.department}</td>
          <td>${item.attended_sessions} / ${item.total_sessions}</td>
          <td>
            <div style="display: flex; align-items: center; gap: 10px;">
              <div style="flex: 1; height: 6px; background: rgba(255,255,255,0.06); border-radius: 3px; overflow: hidden;">
                <div style="width: ${item.percentage}%; height: 100%; background: ${item.percentage < 50 ? '#ef4444' : '#f59e0b'};"></div>
              </div>
              <span style="font-weight: 700; color: ${item.percentage < 50 ? '#f87171' : '#fbbf24'};">${item.percentage}%</span>
            </div>
          </td>
          <td>
            <span class="badge badge-danger">At Risk (&lt;75%)</span>
          </td>
        </tr>
      `).join("");
    } catch {}
  },

  exportLow(format = "excel") {
    const token = API.getToken();
    const downloadUrl = `/api/reports/export?format=${format}&type=low_attendance`;

    fetch(downloadUrl, {
      headers: { "Authorization": `Bearer ${token}` }
    })
    .then(r => r.blob())
    .then(blob => {
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `low_attendance_report_${new Date().toISOString().slice(0,10)}.${format === 'excel' ? 'xlsx' : 'csv'}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      API.showToast("Low attendance report downloaded!", "success");
    })
    .catch(() => API.showToast("Export failed.", "error"));
  }
};

// Bootstrap application on DOM ready
document.addEventListener("DOMContentLoaded", () => {
  App.init();
});
