/**
 * System Settings, Attendance Rules, Departments, and Audit Logs Manager
 */
const Settings = {
  async init() {
    this.bindEvents();
    await this.loadRules();
    await this.loadDepartments();
    await this.loadAuditLogs();
  },

  bindEvents() {
    // Save rules form
    const rulesForm = document.getElementById("settings-rules-form");
    if (rulesForm) {
      rulesForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        await this.saveRules();
      });
    }

    // Add department form
    const deptForm = document.getElementById("settings-dept-form");
    if (deptForm) {
      deptForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        await this.saveDepartment();
      });
    }

    // Add user form
    const userForm = document.getElementById("settings-user-form");
    if (userForm) {
      userForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        await this.createUser();
      });
    }
  },

  async loadRules() {
    try {
      const res = await API.request("/api/settings/rules");
      if (res.success && res.rule) {
        const r = res.rule;
        const startEl = document.getElementById("rule-start-time");
        const lateEl = document.getElementById("rule-late-time");
        const endEl = document.getElementById("rule-end-time");
        const pctEl = document.getElementById("rule-min-pct");

        if (startEl) startEl.value = r.work_start_time || "09:00 AM";
        if (lateEl) lateEl.value = r.late_threshold_time || "09:15 AM";
        if (endEl) endEl.value = r.work_end_time || "05:00 PM";
        if (pctEl) pctEl.value = r.min_attendance_percent || 75;
      }
    } catch (err) {
      console.error("Error loading rules:", err);
    }
  },

  async saveRules() {
    const start = document.getElementById("rule-start-time").value.trim();
    const late = document.getElementById("rule-late-time").value.trim();
    const end = document.getElementById("rule-end-time").value.trim();
    const pct = parseFloat(document.getElementById("rule-min-pct").value);

    try {
      const res = await API.request("/api/settings/rules", {
        method: "PUT",
        body: JSON.stringify({
          work_start_time: start,
          late_threshold_time: late,
          work_end_time: end,
          min_attendance_percent: pct
        })
      });

      if (res.success) {
        API.showToast("Attendance policy rules updated successfully!", "success");
      } else {
        API.showToast(res.message, "error");
      }
    } catch {
      API.showToast("Failed to save rules.", "error");
    }
  },

  async loadDepartments() {
    const listEl = document.getElementById("settings-depts-list");
    if (!listEl) return;

    try {
      const res = await API.request("/api/settings/departments");
      if (!res.success || !res.departments.length) {
        listEl.innerHTML = `<div style="color: var(--text-dim); padding: 14px;">No departments added yet.</div>`;
        return;
      }

      listEl.innerHTML = res.departments.map(d => `
        <div style="display: flex; align-items: center; justify-content: space-between; padding: 10px 14px; background: rgba(255,255,255,0.03); border: 1px solid var(--border); border-radius: 6px; margin-bottom: 8px;">
          <div>
            <strong>${d.name}</strong>
            <span style="font-size: 11px; color: var(--accent); margin-left: 8px;">${d.code || ''}</span>
            <span style="font-size: 12px; color: var(--text-dim); margin-left: 12px;">(${d.employee_count} members)</span>
          </div>
          <button class="btn btn-secondary btn-sm" onclick="Settings.deleteDepartment(${d.id})" style="color: var(--danger); padding: 4px 8px;">Delete</button>
        </div>
      `).join("");
    } catch {}
  },

  async saveDepartment() {
    const name = document.getElementById("dept-name-input").value.trim();
    const code = document.getElementById("dept-code-input").value.trim();

    try {
      const res = await API.request("/api/settings/departments", {
        method: "POST",
        body: JSON.stringify({ name, code })
      });

      if (res.success) {
        API.showToast(res.message, "success");
        document.getElementById("settings-dept-form").reset();
        await this.loadDepartments();
        // Also refresh department selectors
        if (typeof Employees !== "undefined") Employees.loadDepartments();
      } else {
        API.showToast(res.message, "error");
      }
    } catch {
      API.showToast("Failed to add department.", "error");
    }
  },

  async deleteDepartment(deptId) {
    if (!confirm("Are you sure you want to remove this department?")) return;
    try {
      const res = await API.request(`/api/settings/departments/${deptId}`, { method: "DELETE" });
      if (res.success) {
        API.showToast(res.message, "success");
        await this.loadDepartments();
      }
    } catch {}
  },

  async createUser() {
    const username = document.getElementById("new-user-username").value.trim();
    const email = document.getElementById("new-user-email").value.trim();
    const password = document.getElementById("new-user-password").value;
    const role = document.getElementById("new-user-role").value;

    try {
      const res = await API.request("/api/auth/users", {
        method: "POST",
        body: JSON.stringify({ username, email, password, role })
      });

      if (res.success) {
        API.showToast(res.message, "success");
        document.getElementById("settings-user-form").reset();
      } else {
        API.showToast(res.message, "error");
      }
    } catch {
      API.showToast("Failed to create user account.", "error");
    }
  },

  async loadAuditLogs() {
    const tbody = document.getElementById("audit-logs-tbody");
    if (!tbody) return;

    try {
      const res = await API.request("/api/settings/audit-logs?limit=50");
      if (!res.success || !res.logs.length) {
        tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-dim); padding: 25px;">No audit events recorded yet.</td></tr>`;
        return;
      }

      tbody.innerHTML = res.logs.map(log => `
        <tr>
          <td><span style="font-size: 12px; color: var(--text-muted);">${log.timestamp}</span></td>
          <td><strong>${log.username || 'System'}</strong></td>
          <td><span class="badge badge-purple">${log.action}</span></td>
          <td style="font-size: 13px; color: var(--text-muted);">${log.details || '—'}</td>
          <td><code style="font-size: 11px; color: var(--text-dim);">${log.ip_address || 'local'}</code></td>
        </tr>
      `).join("");
    } catch {}
  }
};
