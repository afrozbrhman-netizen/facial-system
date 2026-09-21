/**
 * Dashboard Analytics and Chart.js Visualizations
 */
const Dashboard = {
  trendChart: null,
  deptChart: null,

  async init() {
    await this.loadSummary();
  },

  async loadSummary() {
    try {
      const res = await API.request("/api/reports/summary");
      if (!res.success) return;

      const s = res.summary;

      // Update Metric Badges
      const totalEl = document.getElementById("stat-total-emp");
      const presentEl = document.getElementById("stat-present-today");
      const lateEl = document.getElementById("stat-late-today");
      const lowAttEl = document.getElementById("stat-low-att");
      const rateEl = document.getElementById("stat-att-rate");

      if (totalEl) totalEl.textContent = s.total_employees;
      if (presentEl) presentEl.textContent = s.present_today;
      if (lateEl) lateEl.textContent = s.late_today;
      if (lowAttEl) lowAttEl.textContent = s.low_attendance_count;
      if (rateEl) rateEl.textContent = `${s.attendance_percentage}%`;

      // Render Charts
      this.renderTrendChart(s.trend);
      this.renderDeptChart(s.department_breakdown);

      // Load Today's feed preview
      this.loadTodayPreview();

    } catch (err) {
      console.error("Failed to load dashboard summary:", err);
    }
  },

  renderTrendChart(trend) {
    const ctx = document.getElementById("chart-attendance-trend");
    if (!ctx) return;

    if (this.trendChart) {
      this.trendChart.destroy();
    }

    this.trendChart = new Chart(ctx, {
      type: "line",
      data: {
        labels: trend.labels,
        datasets: [
          {
            label: "Present",
            data: trend.present,
            borderColor: "#6366f1",
            backgroundColor: "rgba(99, 102, 241, 0.15)",
            borderWidth: 2.5,
            fill: true,
            tension: 0.35,
            pointBackgroundColor: "#6366f1"
          },
          {
            label: "Late Arrivals",
            data: trend.late,
            borderColor: "#f59e0b",
            backgroundColor: "rgba(245, 158, 11, 0.1)",
            borderWidth: 2,
            borderDash: [5, 5],
            fill: false,
            tension: 0.35,
            pointBackgroundColor: "#f59e0b"
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: "top",
            labels: { color: "#94a3b8", boxWidth: 12, font: { size: 12 } }
          }
        },
        scales: {
          x: {
            grid: { color: "rgba(255, 255, 255, 0.05)" },
            ticks: { color: "#64748b" }
          },
          y: {
            beginAtZero: true,
            grid: { color: "rgba(255, 255, 255, 0.05)" },
            ticks: { color: "#64748b", stepSize: 1 }
          }
        }
      }
    });
  },

  renderDeptChart(depts) {
    const ctx = document.getElementById("chart-dept-breakdown");
    if (!ctx) return;

    if (this.deptChart) {
      this.deptChart.destroy();
    }

    const labels = depts.map(d => d.dept_name);
    const counts = depts.map(d => d.att_count);
    const colors = ["#6366f1", "#06b6d4", "#10b981", "#f59e0b", "#ec4899", "#8b5cf6"];

    this.deptChart = new Chart(ctx, {
      type: "doughnut",
      data: {
        labels: labels.length > 0 ? labels : ["No Attendance"],
        datasets: [{
          data: counts.length > 0 ? counts : [1],
          backgroundColor: labels.length > 0 ? colors.slice(0, labels.length) : ["#334155"],
          borderWidth: 0
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: "bottom",
            labels: { color: "#94a3b8", boxWidth: 10, font: { size: 11 } }
          }
        },
        cutout: "70%"
      }
    });
  },

  async loadTodayPreview() {
    const tbody = document.getElementById("today-preview-tbody");
    if (!tbody) return;

    try {
      const res = await API.request("/api/attendance/today");
      if (!res.success || !res.records.length) {
        tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-dim); padding: 20px;">No attendance records captured today yet.</td></tr>`;
        return;
      }

      tbody.innerHTML = res.records.slice(0, 5).map(r => `
        <tr>
          <td><strong>${r.name}</strong></td>
          <td>${r.student_id}</td>
          <td>${r.check_in_time || r.time}</td>
          <td>${r.check_out_time || '—'}</td>
          <td>
            <span class="badge ${r.shift_status === 'Late' ? 'badge-warning' : 'badge-success'}">${r.shift_status || 'On-Time'}</span>
          </td>
        </tr>
      `).join("");
    } catch {}
  }
};
