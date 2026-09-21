/**
 * Employee & Student Directory with Biometric Face Enrollment
 */
const Employees = {
  currentEnrollEmployeeId: null,
  enrollStream: null,
  enrollFacingMode: "user",

  async init() {
    this.bindEvents();
    await this.loadDepartments();
    await this.loadEmployees();
  },

  bindEvents() {
    // Search input debounce
    const searchInput = document.getElementById("emp-search");
    if (searchInput) {
      searchInput.addEventListener("input", () => {
        clearTimeout(this.searchTimer);
        this.searchTimer = setTimeout(() => this.loadEmployees(), 350);
      });
    }

    // Department filter change
    const deptFilter = document.getElementById("emp-dept-filter");
    if (deptFilter) {
      deptFilter.addEventListener("change", () => this.loadEmployees());
    }

    // Add employee form submit
    const addForm = document.getElementById("add-employee-form");
    if (addForm) {
      addForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        await this.submitAddEmployee();
      });
    }

    // Face enrollment modal trigger
    const btnCaptureFace = document.getElementById("btn-capture-enroll-face");
    if (btnCaptureFace) {
      btnCaptureFace.addEventListener("click", () => this.captureAndEnrollFace());
    }

    // Face enrollment flip camera trigger
    const btnFlipFace = document.getElementById("btn-flip-enroll-camera");
    if (btnFlipFace) {
      btnFlipFace.addEventListener("click", () => this.flipEnrollCamera());
    }

    // File upload fallback for face enrollment
    const faceFileInput = document.getElementById("enroll-file-input");
    if (faceFileInput) {
      faceFileInput.addEventListener("change", (e) => this.handleFaceFileUpload(e));
    }

    // Reset password form submit
    const resetPwdForm = document.getElementById("reset-password-form");
    if (resetPwdForm) {
      resetPwdForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        await this.submitResetPassword();
      });
    }
  },

  async loadDepartments() {
    try {
      const res = await API.request("/api/settings/departments");
      if (!res.success) return;

      const selectOpts = `<option value="">All Departments</option>` +
        res.departments.map(d => `<option value="${d.id}">${d.name}</option>`).join("");

      const filterEl = document.getElementById("emp-dept-filter");
      const formEl = document.getElementById("add-emp-dept");

      if (filterEl) filterEl.innerHTML = selectOpts;
      if (formEl) formEl.innerHTML = `<option value="">Select Department</option>` +
        res.departments.map(d => `<option value="${d.id}">${d.name}</option>`).join("");
    } catch {}
  },

  async loadEmployees() {
    const tbody = document.getElementById("employees-tbody");
    if (!tbody) return;

    const search = document.getElementById("emp-search")?.value.trim() || "";
    const deptId = document.getElementById("emp-dept-filter")?.value || "";

    try {
      tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--text-dim); padding: 30px;">Loading directory...</td></tr>`;

      const queryParams = new URLSearchParams();
      if (search) queryParams.append("search", search);
      if (deptId) queryParams.append("department_id", deptId);

      const res = await API.request(`/api/employees?${queryParams.toString()}`);
      if (!res.success || !res.employees.length) {
        tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--text-dim); padding: 30px;">No matching employees or students found.</td></tr>`;
        return;
      }

      tbody.innerHTML = res.employees.map(emp => {
        const photoUrl = emp.profile_photo_path ? `/${emp.profile_photo_path}` : '';
        const avatarHtml = photoUrl
          ? `<img src="${photoUrl}" style="width: 34px; height: 34px; border-radius: 50%; object-fit: cover;">`
          : `<div style="width: 34px; height: 34px; border-radius: 50%; background: #334155; display: flex; align-items: center; justify-content: center; font-weight: 600; font-size: 12px; color: #fff;">${emp.full_name.charAt(0)}</div>`;

        const hasFace = emp.face_samples_count > 0;

        return `
          <tr>
            <td>
              <div style="display: flex; align-items: center; gap: 10px;">
                ${avatarHtml}
                <div>
                  <div style="font-weight: 600; color: #fff;">${emp.full_name}</div>
                  <div style="font-size: 11.5px; color: var(--text-dim);">${emp.email || 'No email registered'}</div>
                </div>
              </div>
            </td>
            <td><code style="color: var(--accent);">${emp.employee_code}</code></td>
            <td>${emp.department_name || 'General'}</td>
            <td>${emp.designation_class || 'Student'}</td>
            <td>
              <span class="badge ${hasFace ? 'badge-success' : 'badge-warning'}">
                ${hasFace ? `Enrolled (${emp.face_samples_count})` : 'No Face Data'}
              </span>
            </td>
            <td>
              <span class="badge ${emp.status === 'active' ? 'badge-success' : 'badge-danger'}">${emp.status}</span>
            </td>
            <td>
              <div style="display: flex; gap: 6px;">
                <button class="btn btn-secondary btn-sm" title="Enroll Facial Biometrics" onclick="Employees.openFaceModal(${emp.id}, '${encodeURIComponent(emp.full_name)}')">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M8 14s1.5 2 4 2 4-2 4-2"/><line x1="9" y1="9" x2="9.01" y2="9"/><line x1="15" y1="9" x2="15.01" y2="9"/></svg>
                  Face
                </button>
                <button class="btn btn-secondary btn-sm" title="Set/Reset Individual Password" onclick="Employees.openResetPwdModal(${emp.id}, '${encodeURIComponent(emp.full_name)}', '${encodeURIComponent(emp.employee_code)}')">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0110 0v4"/></svg>
                  Password
                </button>
                <button class="btn btn-secondary btn-sm" title="Delete Person" onclick="Employees.deleteEmp(${emp.id}, '${encodeURIComponent(emp.full_name)}')">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/></svg>
                </button>
              </div>
            </td>
          </tr>
        `;
      }).join("");

    } catch (err) {
      console.error("Error loading employees:", err);
    }
  },

  openAddModal() {
    const modal = document.getElementById("modal-add-employee");
    if (modal) modal.classList.add("active");
  },

  closeAddModal() {
    const modal = document.getElementById("modal-add-employee");
    if (modal) modal.classList.remove("active");
  },

  async submitAddEmployee() {
    const code = document.getElementById("add-emp-code").value.trim();
    const name = document.getElementById("add-emp-name").value.trim();
    const email = document.getElementById("add-emp-email").value.trim();
    const phone = document.getElementById("add-emp-phone").value.trim();
    const deptId = document.getElementById("add-emp-dept").value;
    const designation = document.getElementById("add-emp-designation").value.trim();
    const role = document.getElementById("add-emp-role")?.value || "student_employee";
    const password = document.getElementById("add-emp-password")?.value.trim();

    try {
      const res = await API.request("/api/employees", {
        method: "POST",
        body: JSON.stringify({
          employee_code: code,
          full_name: name,
          email: email,
          phone: phone,
          department_id: deptId ? parseInt(deptId) : null,
          designation_class: designation || "Student",
          role: role,
          password: password || undefined
        })
      });

      if (res.success) {
        API.showToast(res.message, "success");
        this.closeAddModal();
        document.getElementById("add-employee-form").reset();
        await this.loadEmployees();

        // Prompt to enroll face
        if (confirm(`Student ${name} registered with unique password: "${res.default_password || password || code + '@123'}"!\n\nWould you like to enroll their facial biometrics now?`)) {
          this.openFaceModal(res.employee_id, encodeURIComponent(name));
        }
      } else {
        API.showToast(res.message, "error");
      }
    } catch (err) {
      API.showToast("Failed to create employee.", "error");
    }
  },

  openResetPwdModal(empId, encodedName, encodedCode) {
    this.currentResetEmpId = empId;
    const name = decodeURIComponent(encodedName);
    const code = decodeURIComponent(encodedCode);
    const title = document.getElementById("reset-pwd-modal-title");
    const sub = document.getElementById("reset-pwd-subtitle");
    if (title) title.textContent = `Set Password for ${name}`;
    if (sub) sub.textContent = `Login Username: ${code}`;
    const input = document.getElementById("reset-pwd-input");
    if (input) input.value = `${code}@123`;
    const modal = document.getElementById("modal-reset-password");
    if (modal) modal.classList.add("active");
  },

  closeResetPwdModal() {
    this.currentResetEmpId = null;
    const modal = document.getElementById("modal-reset-password");
    if (modal) modal.classList.remove("active");
  },

  async submitResetPassword() {
    if (!this.currentResetEmpId) return;
    const pwd = document.getElementById("reset-pwd-input").value.trim();
    try {
      const res = await API.request(`/api/employees/${this.currentResetEmpId}/password`, {
        method: "POST",
        body: JSON.stringify({ password: pwd })
      });
      if (res.success) {
        API.showToast(res.message, "success");
        this.closeResetPwdModal();
      } else {
        API.showToast(res.message, "error");
      }
    } catch {
      API.showToast("Failed to update password.", "error");
    }
  },

  async openFaceModal(empId, encodedName) {
    this.currentEnrollEmployeeId = empId;
    const name = decodeURIComponent(encodedName);
    const titleEl = document.getElementById("enroll-modal-title");
    if (titleEl) titleEl.textContent = `Enroll Biometrics for ${name}`;

    const modal = document.getElementById("modal-enroll-face");
    if (modal) modal.classList.add("active");

    const statusEl = document.getElementById("enroll-status-msg");
    if (statusEl) statusEl.textContent = "Click 'Start Webcam' or upload a photo.";

    // Auto start webcam for convenience
    this.startEnrollWebcam();
  },

  closeFaceModal() {
    this.stopEnrollWebcam();
    this.currentEnrollEmployeeId = null;
    const modal = document.getElementById("modal-enroll-face");
    if (modal) modal.classList.remove("active");
  },

  async flipEnrollCamera() {
    this.enrollFacingMode = this.enrollFacingMode === "user" ? "environment" : "user";
    API.showToast(`Enrollment camera switched to ${this.enrollFacingMode === "environment" ? "Rear (Back)" : "Front (Selfie)"}`, "info");
    this.stopEnrollWebcam();
    await this.startEnrollWebcam();
  },

  async startEnrollWebcam() {
    const video = document.getElementById("enroll-webcam-video");
    const statusEl = document.getElementById("enroll-status-msg");

    if (this.enrollFacingMode === "environment") {
      if (video) video.classList.add("camera-rear");
    } else {
      if (video) video.classList.remove("camera-rear");
    }

    try {
      this.enrollStream = await navigator.mediaDevices.getUserMedia({
        video: { width: 480, height: 480, facingMode: this.enrollFacingMode }
      });
      video.srcObject = this.enrollStream;
      await video.play();
      if (statusEl) statusEl.textContent = "Position face straight towards camera and click Capture.";
    } catch (err) {
      if (statusEl) statusEl.textContent = "Camera unavailable. You can upload an image file instead.";
    }
  },

  stopEnrollWebcam() {
    if (this.enrollStream) {
      this.enrollStream.getTracks().forEach(t => t.stop());
      this.enrollStream = null;
    }
    const video = document.getElementById("enroll-webcam-video");
    if (video) video.srcObject = null;
  },

  async captureAndEnrollFace() {
    const video = document.getElementById("enroll-webcam-video");
    if (!video || !video.videoWidth) {
      API.showToast("Please start the webcam or upload a photo.", "warning");
      return;
    }

    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext("2d");
    ctx.drawImage(video, 0, 0);
    const imageB64 = canvas.toDataURL("image/jpeg", 0.9);

    await this.sendFaceData(imageB64);
  },

  handleFaceFileUpload(e) {
    const file = e.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = async (event) => {
      await this.sendFaceData(event.target.result);
    };
    reader.readAsDataURL(file);
  },

  async sendFaceData(imageB64) {
    const statusEl = document.getElementById("enroll-status-msg");
    if (statusEl) statusEl.textContent = "Computing 128-d face embedding and verifying anti-spoofing...";

    try {
      const res = await API.request(`/api/employees/${this.currentEnrollEmployeeId}/register-face`, {
        method: "POST",
        body: JSON.stringify({ image: imageB64 })
      });

      if (res.success) {
        API.showToast("Facial biometrics enrolled successfully!", "success");
        if (statusEl) statusEl.textContent = "Biometrics successfully enrolled!";
        setTimeout(() => {
          this.closeFaceModal();
          this.loadEmployees();
        }, 1200);
      } else {
        if (statusEl) statusEl.textContent = res.message;
        API.showToast(res.message, "error");
      }
    } catch (err) {
      if (statusEl) statusEl.textContent = "Server error during biometric enrollment.";
      API.showToast("Failed to enroll face.", "error");
    }
  },

  async deleteEmp(empId, encodedName) {
    const name = decodeURIComponent(encodedName);
    if (!confirm(`Are you sure you want to delete ${name} and remove all their enrolled facial biometrics?`)) return;

    try {
      const res = await API.request(`/api/employees/${empId}`, { method: "DELETE" });
      if (res.success) {
        API.showToast(res.message, "success");
        await this.loadEmployees();
      } else {
        API.showToast(res.message, "error");
      }
    } catch {
      API.showToast("Failed to delete employee.", "error");
    }
  }
};
