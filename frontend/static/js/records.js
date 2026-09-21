/**
 * Attendance Records, Filtering, Manual Correction, and File Exporter
 */
const Records = {
  currentOffset: 0,
  limit: 25,
  totalRecords: 0,

  async init() {
    this.bindEvents();
    await this.loadRecords();
  },

  bindEvents() {
    // Filter changes
    ["rec-search", "rec-status-filter", "rec-dept-filter", "rec-date-from", "rec-date-to"].forEach(id => {
      const el = document.getElementById(id);
      if (el) {
        el.addEventListener("change", () => {
          this.currentOffset = 0;
          this.loadRecords();
        });
        if (el.tagName === "INPUT" && el.type === "text") {
          el.addEventListener("input", () => {
            clearTimeout(this.filterTimer);
            this.filterTimer = setTimeout(() => {
              this.currentOffset = 0;
              this.loadRecords();
            }, 350);
          });
        }
      }
    });

    // Manual attendance modal
    const manualForm = document.getElementById("manual-attendance-form");
    if (manualForm) {
      manualForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        await this.submitManualMark();
      });
    }

    // Export Buttons
    const btnExpExcel = document.getElementById("btn-export-excel");
    const btnExpCsv = document.getElementById("btn-export-csv");
    const btnExpPrint = document.getElementById("btn-export-print");

    if (btnExpExcel) btnExpExcel.addEventListener("click", () => this.downloadExport("excel"));
    if (btnExpCsv) btnExpCsv.addEventListener("click", () => this.downloadExport("csv"));
    if (btnExpPrint) btnExpPrint.addEventListener("click", () => this.openPrintView());
  },

  async loadRecords() {
    const tbody = document.getElementById("records-tbody");
    if (!tbody) return;

    const search = document.getElementById("rec-search")?.value.trim() || "";
    const status = document.getElementById("rec-status-filter")?.value || "";
    const deptId = document.getElementById("rec-dept-filter")?.value || "";
    const dateFrom = document.getElementById("rec-date-from")?.value || "";
    const dateTo = document.getElementById("rec-date-to")?.value || "";

    const queryParams = new URLSearchParams({
      limit: this.limit,
      offset: this.currentOffset
    });
    if (search) queryParams.append("search", search);
    if (status) queryParams.append("status", status);
    if (deptId) queryParams.append("department_id", deptId);
    if (dateFrom) queryParams.append("date_from", dateFrom);
    if (dateTo) queryParams.append("date_to", dateTo);

    try {
      tbody.innerHTML = `<tr><td colspan="9" style="text-align: center; color: var(--text-dim); padding: 30px;">Loading attendance logs...</td></tr>`;

      const res = await API.request(`/api/attendance/history?${queryParams.toString()}`);
      if (!res.success || !res.records.length) {
        tbody.innerHTML = `<tr><td colspan="9" style="text-align: center; color: var(--text-dim); padding: 30px;">No attendance logs found matching filter criteria.</td></tr>`;
        this.updatePagination(0);
        return;
      }

      this.totalRecords = res.total;
      this.updatePagination(res.total);

      tbody.innerHTML = res.records.map(r => {
        const isLate = r.shift_status === "Late";
        const durationFormatted = r.duration_minutes > 0
          ? `${Math.floor(r.duration_minutes / 60)}h ${r.duration_minutes % 60}m`
          : '—';

        return `
          <tr>
            <td><strong>${r.date}</strong></td>
            <td><code style="color: var(--accent);">${r.student_id}</code></td>
            <td><strong>${r.name}</strong></td>
            <td>${r.department_name || 'General'}</td>
            <td>${r.check_in_time || r.time || '—'}</td>
            <td>${r.check_out_time || '—'}</td>
            <td>${durationFormatted}</td>
            <td>
              <span class="badge ${r.status === 'Present' ? 'badge-success' : 'badge-danger'}">${r.status}</span>
            </td>
            <td>
              <span class="badge ${isLate ? 'badge-warning' : 'badge-success'}">${r.shift_status || 'On-Time'}</span>
            </td>
          </tr>
        `;
      }).join("");

    } catch (err) {
      console.error("Error loading records:", err);
    }
  },

  updatePagination(total) {
    const pageInfo = document.getElementById("rec-page-info");
    const prevBtn = document.getElementById("rec-prev-page");
    const nextBtn = document.getElementById("rec-next-page");

    if (pageInfo) {
      const from = total === 0 ? 0 : this.currentOffset + 1;
      const to = Math.min(this.currentOffset + this.limit, total);
      pageInfo.textContent = `Showing ${from}–${to} of ${total} records`;
    }

    if (prevBtn) prevBtn.disabled = this.currentOffset === 0;
    if (nextBtn) nextBtn.disabled = this.currentOffset + this.limit >= total;
  },

  prevPage() {
    if (this.currentOffset >= this.limit) {
      this.currentOffset -= this.limit;
      this.loadRecords();
    }
  },

  nextPage() {
    if (this.currentOffset + this.limit < this.totalRecords) {
      this.currentOffset += this.limit;
      this.loadRecords();
    }
  },

  openManualModal() {
    const modal = document.getElementById("modal-manual-mark");
    if (modal) modal.classList.add("active");
  },

  closeManualModal() {
    const modal = document.getElementById("modal-manual-mark");
    if (modal) modal.classList.remove("active");
  },

  async submitManualMark() {
    const sid = document.getElementById("manual-student-id").value.trim();
    const status = document.getElementById("manual-status").value;
    const date = document.getElementById("manual-date").value;
    const time = document.getElementById("manual-time").value;
    const shift = document.getElementById("manual-shift-status").value;
    const subject = document.getElementById("manual-subject").value.trim();

    try {
      const res = await API.request("/api/attendance/manual-mark", {
        method: "POST",
        body: JSON.stringify({
          student_id: sid,
          status: status,
          date: date,
          time: time,
          shift_status: shift,
          subject: subject || "General"
        })
      });

      if (res.success) {
        API.showToast(res.message, "success");
        this.closeManualModal();
        document.getElementById("manual-attendance-form").reset();
        await this.loadRecords();
      } else {
        API.showToast(res.message, "error");
      }
    } catch {
      API.showToast("Failed to record manual attendance.", "error");
    }
  },

  async downloadExport(format = "excel") {
    API.showToast(`Preparing ${format.toUpperCase()} export download...`, "info");
    const dateFrom = document.getElementById("rec-date-from")?.value || "";
    const dateTo = document.getElementById("rec-date-to")?.value || "";
    const deptId = document.getElementById("rec-dept-filter")?.value || "";

    const queryParams = new URLSearchParams({
      format: format,
      type: "daily"
    });
    if (dateFrom) queryParams.append("date_from", dateFrom);
    if (dateTo) queryParams.append("date_to", dateTo);
    if (deptId) queryParams.append("department_id", deptId);

    const token = API.getToken();
    const downloadUrl = `/api/reports/export?${queryParams.toString()}`;

    // Trigger download via link with auth token
    fetch(downloadUrl, {
      headers: { "Authorization": `Bearer ${token}` }
    })
    .then(resp => resp.blob())
    .then(blob => {
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `attendance_export_${new Date().toISOString().slice(0,10)}.${format === 'excel' ? 'xlsx' : 'csv'}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      API.showToast("Download started successfully!", "success");
    })
    .catch(() => API.showToast("Export failed.", "error"));
  },

  openPrintView() {
    const dateFrom = document.getElementById("rec-date-from")?.value || "";
    const dateTo = document.getElementById("rec-date-to")?.value || "";
    const deptId = document.getElementById("rec-dept-filter")?.value || "";

    const queryParams = new URLSearchParams({
      format: "html",
      type: "daily"
    });
    if (dateFrom) queryParams.append("date_from", dateFrom);
    if (dateTo) queryParams.append("date_to", dateTo);
    if (deptId) queryParams.append("department_id", deptId);

    const token = API.getToken();
    fetch(`/api/reports/export?${queryParams.toString()}`, {
      headers: { "Authorization": `Bearer ${token}` }
    })
    .then(r => r.text())
    .then(html => {
      const printWindow = window.open("", "_blank");
      printWindow.document.write(html);
      printWindow.document.close();
    })
    .catch(() => API.showToast("Could not open print view.", "error"));
  }
};
