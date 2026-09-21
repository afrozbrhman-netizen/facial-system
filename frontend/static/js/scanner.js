/**
 * Real-Time Camera Attendance Scanner with Anti-Spoofing & Liveness Display
 */
const Scanner = {
  videoStream: null,
  isScanning: false,
  scanInterval: null,
  scanCooldown: false,

  init() {
    this.bindEvents();
  },

  bindEvents() {
    const btnToggle = document.getElementById("btn-toggle-camera");
    if (btnToggle) {
      btnToggle.addEventListener("click", () => {
        if (this.isScanning) {
          this.stopCamera();
        } else {
          this.startCamera();
        }
      });
    }

    const btnSnap = document.getElementById("btn-manual-scan");
    if (btnSnap) {
      btnSnap.addEventListener("click", () => {
        this.performScan();
      });
    }
  },

  async startCamera() {
    const video = document.getElementById("camera-video");
    const btnToggle = document.getElementById("btn-toggle-camera");
    const statusText = document.getElementById("scanner-status-text");

    try {
      this.videoStream = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: "user" },
        audio: false
      });
      video.srcObject = this.videoStream;
      await video.play();

      this.isScanning = true;
      if (btnToggle) {
        btnToggle.textContent = "Stop Camera";
        btnToggle.className = "btn btn-danger";
      }
      if (statusText) statusText.textContent = "Scanner Active - Looking for Faces";

      // Start automatic scan loop every 2.5 seconds
      this.scanInterval = setInterval(() => {
        if (!this.scanCooldown) {
          this.performScan();
        }
      }, 2500);

    } catch (err) {
      console.error("Camera access error:", err);
      API.showToast("Could not access camera. Please allow camera permissions.", "error");
      if (statusText) statusText.textContent = "Camera Permission Denied";
    }
  },

  stopCamera() {
    if (this.scanInterval) {
      clearInterval(this.scanInterval);
      this.scanInterval = null;
    }

    if (this.videoStream) {
      this.videoStream.getTracks().forEach(track => track.stop());
      this.videoStream = null;
    }

    const video = document.getElementById("camera-video");
    if (video) video.srcObject = null;

    this.isScanning = false;
    const btnToggle = document.getElementById("btn-toggle-camera");
    if (btnToggle) {
      btnToggle.textContent = "Start Camera";
      btnToggle.className = "btn btn-primary";
    }

    const statusText = document.getElementById("scanner-status-text");
    if (statusText) statusText.textContent = "Camera Off";
  },

  captureFrame() {
    const video = document.getElementById("camera-video");
    if (!video || !video.videoWidth) return null;

    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext("2d");
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    return canvas.toDataURL("image/jpeg", 0.85);
  },

  async performScan() {
    const frameB64 = this.captureFrame();
    if (!frameB64) return;

    const mode = document.getElementById("scanner-mode")?.value || "auto";
    const subject = document.getElementById("scanner-subject")?.value || "General";
    const category = document.getElementById("scanner-category")?.value || "Classroom Lecture";

    const feedbackBox = document.getElementById("scanner-feedback");
    const statusText = document.getElementById("scanner-status-text");

    try {
      if (statusText) statusText.textContent = "Analyzing Biometrics & Liveness...";

      const res = await API.request("/api/attendance/scan", {
        method: "POST",
        body: JSON.stringify({
          image: frameB64,
          mode: mode,
          subject: subject,
          category: category
        })
      });

      this.handleScanResult(res);

    } catch (err) {
      console.error("Scan error:", err);
    }
  },

  handleScanResult(res) {
    const feedbackBox = document.getElementById("scanner-feedback");
    const statusText = document.getElementById("scanner-status-text");
    if (!feedbackBox) return;

    // Reset feedback box state
    feedbackBox.className = "feedback-box";

    if (!res.success) {
      if (res.status === "no_face") {
        if (statusText) statusText.textContent = "Scanning... Position face inside reticle";
        return;
      }

      if (res.status === "spoof_warning") {
        feedbackBox.classList.add("state-danger");
        feedbackBox.innerHTML = `
          <div class="feedback-icon" style="background: var(--danger-light); color: var(--danger);">
            <svg viewBox="0 0 24 24"><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
          </div>
          <h3 style="color: var(--danger); margin-bottom: 6px;">Liveness Check Failed</h3>
          <p style="font-size: 13.5px; color: var(--text-muted);">${res.message}</p>
        `;
        this.playTone(300, "sawtooth");
        this.cooldown(3000);
        return;
      }

      if (res.status === "unknown_person") {
        feedbackBox.classList.add("state-danger");
        feedbackBox.innerHTML = `
          <div class="feedback-icon" style="background: var(--danger-light); color: var(--danger);">
            <svg viewBox="0 0 24 24"><circle cx="12" cy="8" r="5"/><path d="M20 21a8 8 0 00-16 0"/><line x1="18" y1="8" x2="23" y2="13"/><line x1="23" y1="8" x2="18" y2="13"/></svg>
          </div>
          <h3 style="color: var(--danger); margin-bottom: 6px;">Unknown Person</h3>
          <p style="font-size: 13.5px; color: var(--text-muted);">${res.message}</p>
        `;
        this.playTone(350, "sine");
        this.cooldown(3000);
        return;
      }
    }

    // Success response handling
    const emp = res.employee || {};
    const photoUrl = emp.profile_photo_path ? `/${emp.profile_photo_path}` : 'data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="%236366f1"><circle cx="12" cy="8" r="5"/><path d="M20 21a8 8 0 00-16 0"/></svg>';

    if (res.status === "check_in_success") {
      feedbackBox.classList.add("state-success");
      const isLate = res.shift_status === "Late";
      feedbackBox.innerHTML = `
        <div class="feedback-icon" style="background: var(--success-light); color: var(--success);">
          <svg viewBox="0 0 24 24"><path d="M22 11.08V12a10 10 0 11-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
        </div>
        <h3 style="color: var(--success); margin-bottom: 4px;">Attendance Marked!</h3>
        <p style="font-size: 13px; color: var(--text-muted);">${res.message}</p>
        <div class="matched-user-badge">
          <div class="matched-avatar"><img src="${photoUrl}" alt="${emp.full_name}"></div>
          <div style="text-align: left; flex: 1;">
            <div style="font-weight: 700; font-size: 15px; color: #fff;">${emp.full_name}</div>
            <div style="font-size: 12px; color: var(--text-muted);">${emp.employee_code} • ${emp.department_name || 'Staff'}</div>
            <div style="margin-top: 4px;">
              <span class="badge ${isLate ? 'badge-warning' : 'badge-success'}">${res.shift_status} Check-In (${res.check_in_time})</span>
            </div>
          </div>
        </div>
      `;
      this.playTone(880, "sine");
      API.showToast(`Checked in: ${emp.full_name}`, "success");
      this.cooldown(4500);

    } else if (res.status === "check_out_success") {
      feedbackBox.classList.add("state-success");
      feedbackBox.innerHTML = `
        <div class="feedback-icon" style="background: var(--accent-light); color: var(--accent);">
          <svg viewBox="0 0 24 24"><path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
        </div>
        <h3 style="color: var(--accent); margin-bottom: 4px;">Check-Out Recorded!</h3>
        <p style="font-size: 13px; color: var(--text-muted);">${res.message}</p>
        <div class="matched-user-badge">
          <div class="matched-avatar"><img src="${photoUrl}" alt="${emp.full_name}"></div>
          <div style="text-align: left; flex: 1;">
            <div style="font-weight: 700; font-size: 15px; color: #fff;">${emp.full_name}</div>
            <div style="font-size: 12px; color: var(--text-muted);">${emp.employee_code} • Out at ${res.check_out_time}</div>
            <div style="margin-top: 4px;">
              <span class="badge badge-purple">Duration: ${res.duration_formatted}</span>
            </div>
          </div>
        </div>
      `;
      this.playTone(700, "sine");
      API.showToast(`Checked out: ${emp.full_name}`, "success");
      this.cooldown(4500);

    } else if (res.status === "already_marked" || res.status === "completed_today") {
      feedbackBox.classList.add("state-warning");
      feedbackBox.innerHTML = `
        <div class="feedback-icon" style="background: var(--warning-light); color: var(--warning);">
          <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
        </div>
        <h3 style="color: var(--warning); margin-bottom: 4px;">Already Recorded</h3>
        <p style="font-size: 13px; color: var(--text-muted);">${res.message}</p>
        <div class="matched-user-badge">
          <div class="matched-avatar"><img src="${photoUrl}" alt="${emp.full_name}"></div>
          <div style="text-align: left; flex: 1;">
            <div style="font-weight: 700; font-size: 15px; color: #fff;">${emp.full_name}</div>
            <div style="font-size: 12px; color: var(--text-muted);">${emp.employee_code} • Status: ${res.shift_status || 'Marked'}</div>
          </div>
        </div>
      `;
      this.cooldown(3000);
    }
  },

  cooldown(ms = 3000) {
    this.scanCooldown = true;
    setTimeout(() => {
      this.scanCooldown = false;
    }, ms);
  },

  playTone(freq = 600, type = "sine") {
    try {
      const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      const osc = audioCtx.createOscillator();
      const gain = audioCtx.createGain();
      osc.type = type;
      osc.frequency.value = freq;
      gain.gain.setValueAtTime(0.08, audioCtx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.0001, audioCtx.currentTime + 0.35);
      osc.connect(gain);
      gain.connect(audioCtx.destination);
      osc.start();
      osc.stop(audioCtx.currentTime + 0.35);
    } catch {}
  }
};
