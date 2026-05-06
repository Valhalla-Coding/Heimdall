/* ── State ───────────────────────────────────────────────────────────── */
let devices = [];
let routes  = [];

/* ── API helpers ─────────────────────────────────────────────────────── */
const API = {
  async get(path) {
    const r = await fetch(path);
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },
  async post(path, body) {
    const r = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },
  async put(path, body) {
    const r = await fetch(path, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },
  async del(path) {
    const r = await fetch(path, { method: 'DELETE' });
    if (!r.ok && r.status !== 204) throw new Error(await r.text());
  },
};

/* ── Toast ───────────────────────────────────────────────────────────── */
const toast = document.getElementById('toast');
let toastTimer;
function showToast(msg, isError = false) {
  toast.textContent = msg;
  toast.className = 'toast show' + (isError ? ' error' : '');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { toast.className = 'toast'; }, 3000);
}

/* ── Navigation ──────────────────────────────────────────────────────── */
document.querySelectorAll('.nav-link').forEach(link => {
  link.addEventListener('click', e => {
    e.preventDefault();
    const view = link.dataset.view;
    document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
    link.classList.add('active');
    document.getElementById('view-' + view).classList.add('active');
    if (view === 'devices') renderDevices();
    if (view === 'routes') renderRoutes();
    if (view === 'dashboard') renderDashboard();
  });
});

/* ── Modal helpers ───────────────────────────────────────────────────── */
function openModal(id) { document.getElementById(id).style.display = 'flex'; }
function closeModal(id) { document.getElementById(id).style.display = 'none'; }

document.querySelectorAll('[data-modal]').forEach(btn => {
  btn.addEventListener('click', () => closeModal(btn.dataset.modal));
});
document.querySelectorAll('.modal-overlay').forEach(overlay => {
  overlay.addEventListener('click', e => {
    if (e.target === overlay) closeModal(overlay.id);
  });
});

/* ── Load data ───────────────────────────────────────────────────────── */
async function loadAll() {
  [devices, routes] = await Promise.all([
    API.get('/api/devices').catch(() => []),
    API.get('/api/routes').catch(() => []),
  ]);
}

/* ── Dashboard ───────────────────────────────────────────────────────── */
async function renderDashboard() {
  await loadAll();
  document.getElementById('stat-devices').textContent = devices.length;
  document.getElementById('stat-routes').textContent  = routes.filter(r => r.enabled).length;

  const body = document.getElementById('dash-route-body');
  if (!routes.length) {
    body.innerHTML = '<tr><td colspan="3" class="empty">No routes yet. <a href="#" data-view="routes">Add one →</a></td></tr>';
    body.querySelector('[data-view]')?.addEventListener('click', e => {
      e.preventDefault();
      document.querySelector('.nav-link[data-view="routes"]').click();
    });
    return;
  }
  body.innerHTML = routes.map(r => `
    <tr>
      <td><code>${esc(r.hostname)}</code></td>
      <td><code>${esc(r.target)}</code></td>
      <td><span class="pill ${r.enabled ? 'pill-green' : 'pill-dim'}">${r.enabled ? 'Active' : 'Disabled'}</span></td>
    </tr>
  `).join('');
}

/* ── Devices ─────────────────────────────────────────────────────────── */
function renderDevices() {
  const body = document.getElementById('device-body');
  if (!devices.length) {
    body.innerHTML = '<tr><td colspan="6" class="empty">No devices yet — add one above.</td></tr>';
    return;
  }
  body.innerHTML = devices.map(d => `
    <tr>
      <td><strong>${esc(d.hostname)}</strong></td>
      <td><code>${esc(d.ip)}</code></td>
      <td>${d.label ? esc(d.label) : '<span style="color:var(--text-dim)">—</span>'}</td>
      <td style="color:var(--text-dim); font-size:12px">${fmtDate(d.last_seen)}</td>
      <td>
        <label class="toggle">
          <input type="checkbox" ${d.active ? 'checked' : ''} onchange="toggleDevice(${d.id}, this.checked)" />
          <span class="toggle-slider"></span>
        </label>
      </td>
      <td>
        <div class="row-actions">
          <button class="btn btn-ghost btn-sm" onclick="editDevice(${d.id})">Edit</button>
          <button class="btn btn-danger btn-sm" onclick="deleteDevice(${d.id})">Delete</button>
        </div>
      </td>
    </tr>
  `).join('');
}

async function toggleDevice(id, active) {
  try {
    await API.put(`/api/devices/${id}`, { active });
    devices = devices.map(d => d.id === id ? { ...d, active } : d);
    showToast(active ? 'Device enabled' : 'Device disabled');
  } catch (e) {
    showToast('Failed to update device', true);
  }
}

function editDevice(id) {
  const d = devices.find(d => d.id === id);
  if (!d) return;
  document.getElementById('device-modal-title').textContent = 'Edit Device';
  document.getElementById('device-id').value       = d.id;
  document.getElementById('device-ip').value        = d.ip;
  document.getElementById('device-hostname').value  = d.hostname;
  document.getElementById('device-label').value     = d.label || '';
  openModal('device-modal');
}

async function deleteDevice(id) {
  if (!confirm('Delete this device?')) return;
  try {
    await API.del(`/api/devices/${id}`);
    devices = devices.filter(d => d.id !== id);
    renderDevices();
    showToast('Device deleted');
  } catch (e) {
    showToast('Delete failed', true);
  }
}

document.getElementById('btn-add-device').addEventListener('click', () => {
  document.getElementById('device-modal-title').textContent = 'Add Device';
  document.getElementById('device-form').reset();
  document.getElementById('device-id').value = '';
  openModal('device-modal');
});

document.getElementById('device-form').addEventListener('submit', async e => {
  e.preventDefault();
  const id       = document.getElementById('device-id').value;
  const payload  = {
    ip:       document.getElementById('device-ip').value.trim(),
    hostname: document.getElementById('device-hostname').value.trim(),
    label:    document.getElementById('device-label').value.trim() || null,
  };
  try {
    if (id) {
      const updated = await API.put(`/api/devices/${id}`, payload);
      devices = devices.map(d => d.id === updated.id ? updated : d);
      showToast('Device updated');
    } else {
      const created = await API.post('/api/devices', payload);
      devices.push(created);
      showToast('Device added');
    }
    closeModal('device-modal');
    renderDevices();
  } catch (e) {
    showToast('Error: ' + extractError(e), true);
  }
});

/* ── Routes ──────────────────────────────────────────────────────────── */
function renderRoutes() {
  populateDeviceSelect();
  const body = document.getElementById('route-body');
  if (!routes.length) {
    body.innerHTML = '<tr><td colspan="6" class="empty">No routes yet — add one above.</td></tr>';
    return;
  }
  body.innerHTML = routes.map(r => {
    const device = devices.find(d => d.id === r.device_id);
    return `
      <tr>
        <td><code>${esc(r.hostname)}</code></td>
        <td><code>${esc(r.target)}</code></td>
        <td>${r.label ? esc(r.label) : '<span style="color:var(--text-dim)">—</span>'}</td>
        <td>${device ? `<span class="pill pill-dim">${esc(device.hostname)}</span>` : '<span style="color:var(--text-dim)">—</span>'}</td>
        <td>
          <label class="toggle">
            <input type="checkbox" ${r.enabled ? 'checked' : ''} onchange="toggleRoute(${r.id}, this.checked)" />
            <span class="toggle-slider"></span>
          </label>
        </td>
        <td>
          <div class="row-actions">
            <button class="btn btn-ghost btn-sm" onclick="editRoute(${r.id})">Edit</button>
            <button class="btn btn-danger btn-sm" onclick="deleteRoute(${r.id})">Delete</button>
          </div>
        </td>
      </tr>
    `;
  }).join('');
}

function populateDeviceSelect() {
  const sel = document.getElementById('route-device');
  const current = sel.value;
  sel.innerHTML = '<option value="">— none —</option>' +
    devices.map(d => `<option value="${d.id}">${esc(d.hostname)} (${esc(d.ip)})</option>`).join('');
  sel.value = current;
}

async function toggleRoute(id, enabled) {
  try {
    await API.put(`/api/routes/${id}`, { enabled });
    routes = routes.map(r => r.id === id ? { ...r, enabled } : r);
    showToast(enabled ? 'Route enabled' : 'Route disabled');
  } catch (e) {
    showToast('Failed to update route', true);
  }
}

function editRoute(id) {
  const r = routes.find(r => r.id === id);
  if (!r) return;
  document.getElementById('route-modal-title').textContent = 'Edit Route';
  document.getElementById('route-id').value       = r.id;
  document.getElementById('route-hostname').value  = r.hostname;
  document.getElementById('route-target').value    = r.target;
  document.getElementById('route-label').value     = r.label || '';
  document.getElementById('route-device').value    = r.device_id || '';
  document.getElementById('route-enabled').checked = r.enabled;
  openModal('route-modal');
}

async function deleteRoute(id) {
  if (!confirm('Delete this route?')) return;
  try {
    await API.del(`/api/routes/${id}`);
    routes = routes.filter(r => r.id !== id);
    renderRoutes();
    showToast('Route deleted');
  } catch (e) {
    showToast('Delete failed', true);
  }
}

document.getElementById('btn-add-route').addEventListener('click', async () => {
  await loadAll();
  document.getElementById('route-modal-title').textContent = 'Add Route';
  document.getElementById('route-form').reset();
  document.getElementById('route-id').value = '';
  document.getElementById('route-enabled').checked = true;
  populateDeviceSelect();
  openModal('route-modal');
});

document.getElementById('route-form').addEventListener('submit', async e => {
  e.preventDefault();
  const id      = document.getElementById('route-id').value;
  const payload = {
    hostname:  document.getElementById('route-hostname').value.trim(),
    target:    document.getElementById('route-target').value.trim(),
    label:     document.getElementById('route-label').value.trim() || null,
    device_id: document.getElementById('route-device').value || null,
    enabled:   document.getElementById('route-enabled').checked,
  };
  try {
    if (id) {
      const updated = await API.put(`/api/routes/${id}`, payload);
      routes = routes.map(r => r.id === updated.id ? updated : r);
      showToast('Route updated');
    } else {
      const created = await API.post('/api/routes', payload);
      routes.push(created);
      showToast('Route added');
    }
    closeModal('route-modal');
    renderRoutes();
  } catch (e) {
    showToast('Error: ' + extractError(e), true);
  }
});

/* ── Utilities ───────────────────────────────────────────────────────── */
function esc(str) {
  if (!str) return '';
  return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function fmtDate(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function extractError(err) {
  try {
    const obj = JSON.parse(err.message);
    return obj.detail || err.message;
  } catch {
    return err.message;
  }
}

/* ── Add My Device (self-registration) ───────────────────────────────── */
async function openSelfModal() {
  // Try to detect the hostname from the server
  try {
    const info = await API.get