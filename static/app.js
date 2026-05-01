// NextFlex Project Portal — frontend logic
const API = ''; // same origin

// ───── Session ─────
async function loadSession() {
  try {
    const res = await fetch('/api/auth/whoami');
    if (!res.ok) {
      window.location.href = '/manager/login';
      return null;
    }
    const user = await res.json();
    const badge = document.getElementById('userBadge');
    if (badge) {
      const roleLabel = { admin: 'Admin', dod: 'DoD', member: 'Member' }[user.role] || user.role;
      badge.textContent = `${user.display_name} · ${roleLabel}`;
      badge.title = user.title;
    }
    window._currentUser = user;
    return user;
  } catch (e) {
    console.error('Session load failed', e);
    window.location.href = '/manager/login';
    return null;
  }
}

async function logout() {
  if (!confirm('Sign out?')) return;
  try {
    await fetch('/api/auth/logout', { method: 'POST' });
  } finally {
    window.location.href = '/manager/login';
  }
}

// ───── State ─────
let allPCs = [];
let allFocusAreas = [];

// ───── Utilities ─────
const $ = (s) => document.querySelector(s);
const $$ = (s) => document.querySelectorAll(s);

function fmtMoney(n) {
  if (n == null) return '—';
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `$${(n / 1_000).toFixed(0)}K`;
  return `$${n}`;
}
function fmtDate(s) {
  if (!s) return '—';
  return new Date(s).toLocaleDateString('en-US', { year: 'numeric', month: 'short' });
}
function escapeHtml(s) {
  return String(s ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;');
}

// ───── API client ─────
async function api(path, params = {}) {
  const url = new URL(API + path, location.origin);
  Object.entries(params).forEach(([k, v]) => v && url.searchParams.set(k, v));
  const res = await fetch(url);
  if (!res.ok) throw new Error(`API ${res.status}: ${path}`);
  return res.json();
}

// ───── View switching ─────
$$('.nav-btn').forEach((btn) => {
  btn.addEventListener('click', () => {
    $$('.nav-btn').forEach((b) => b.classList.remove('active'));
    $$('.view').forEach((v) => v.classList.remove('active'));
    btn.classList.add('active');
    $(`#view-${btn.dataset.view}`).classList.add('active');
    if (btn.dataset.view === 'projects' && !$('#filterPC').dataset.loaded) {
      populateFilters();
    }
    if (btn.dataset.view === 'institutions') {
      loadInstitutions();
    }
  });
});

// ───── Dashboard ─────
async function loadDashboard() {
  try {
    const stats = await api('/api/stats');
    $('#statTotal').textContent = stats.total_projects;
    $('#statFunding').textContent = fmtMoney(stats.total_funding_usd);
    $('#statPCs').textContent = stats.project_calls;
    $('#statInst').textContent = stats.institutions;
    $('#statFocus').textContent = stats.focus_areas;

    const pcs = await api('/api/project-calls');
    allPCs = pcs;
    const maxCount = Math.max(...pcs.map((p) => p.project_count));

    $('#pcList').innerHTML = pcs
      .map((pc) => {
        const w = (pc.project_count / maxCount) * 100;
        return `
          <div class="pc-row" onclick="filterByPC('${escapeHtml(pc.project_call)}')">
            <span class="pc-label">${escapeHtml(pc.project_call)}</span>
            <span class="pc-meta">${fmtMoney(pc.total_funding)}</span>
            <div class="pc-bar"><div class="pc-bar-fill" style="width:${w}%"></div></div>
            <span class="pc-count">${pc.project_count}</span>
          </div>
        `;
      })
      .join('');

    const fas = await api('/api/focus-areas');
    allFocusAreas = fas;
    const maxFa = Math.max(...fas.map((f) => f.count));
    $('#focusList').innerHTML = fas
      .slice(0, 10)
      .map((fa) => {
        const w = (fa.count / maxFa) * 100;
        return `
          <div class="focus-row" onclick="filterByFocus('${escapeHtml(fa.focus_area)}')">
            <span class="pc-label" style="min-width:auto; flex:1">${escapeHtml(fa.focus_area)}</span>
            <div class="pc-bar"><div class="pc-bar-fill" style="width:${w}%"></div></div>
            <span class="pc-count">${fa.count}</span>
          </div>
        `;
      })
      .join('');
  } catch (e) {
    console.error('Dashboard load failed', e);
  }
}

function filterByPC(pc) {
  $('#filterPC').value = pc;
  $('.nav-btn[data-view="projects"]').click();
  loadProjects();
}
function filterByFocus(focus) {
  $('#filterFocus').value = focus;
  $('.nav-btn[data-view="projects"]').click();
  loadProjects();
}

// ───── Projects view ─────
async function populateFilters() {
  if (!allPCs.length) {
    allPCs = await api('/api/project-calls');
    allFocusAreas = await api('/api/focus-areas');
  }
  $('#filterPC').innerHTML =
    '<option value="">All Project Calls</option>' +
    allPCs.map((p) => `<option value="${escapeHtml(p.project_call)}">${escapeHtml(p.project_call)} (${p.project_count})</option>`).join('');
  $('#filterFocus').innerHTML =
    '<option value="">All Focus Areas</option>' +
    allFocusAreas.map((f) => `<option value="${escapeHtml(f.focus_area)}">${escapeHtml(f.focus_area)} (${f.count})</option>`).join('');
  $('#filterPC').dataset.loaded = 'true';
  loadProjects();
}

async function loadProjects() {
  const params = {
    pc: $('#filterPC').value,
    focus: $('#filterFocus').value,
    status: $('#filterStatus').value,
    limit: 100,
  };
  $('#projectsList').innerHTML = '<div class="loading">Loading...</div>';
  try {
    const data = await api('/api/projects', params);
    renderProjectList('#projectsList', data.results);
  } catch (e) {
    $('#projectsList').innerHTML = `<div class="empty-state">Error: ${e.message}</div>`;
  }
}

function renderProjectList(target, projects) {
  if (!projects.length) {
    $(target).innerHTML = '<div class="empty-state">No projects matched your filters.</div>';
    return;
  }
  $(target).innerHTML = projects
    .map((p) => `
      <div class="project-card" onclick="showProject('${escapeHtml(p.id)}')">
        <div class="project-card-header">
          <span class="project-pc">${escapeHtml(p.project_call)}</span>
          <div class="project-title">${escapeHtml(p.title)}</div>
        </div>
        <div class="project-meta">
          <span class="item">📍 ${escapeHtml(p.lead_institution || 'Unknown')}</span>
          <span class="item">🗓️ ${fmtDate(p.start_date)} → ${fmtDate(p.end_date)}</span>
          <span class="item">💵 ${fmtMoney(p.funding_amount)}</span>
        </div>
        <div class="project-tags">
          <span class="tag focus">${escapeHtml(p.focus_area || '')}</span>
          <span class="tag status-${escapeHtml(p.status)}">${escapeHtml(p.status)}</span>
          ${(p.keywords || []).slice(0, 4).map((k) => `<span class="tag">${escapeHtml(k)}</span>`).join('')}
        </div>
      </div>
    `)
    .join('');
}

// ───── Project detail modal ─────
async function showProject(id) {
  try {
    const p = await api(`/api/projects/${encodeURIComponent(id)}`);
    const renderList = (arr) =>
      arr && arr.length
        ? `<div class="list-block"><ul>${arr.map((x) => `<li>• ${escapeHtml(x)}</li>`).join('')}</ul></div>`
        : '<div class="list-block" style="color:var(--muted)">—</div>';

    $('#modalBody').innerHTML = `
      <div class="modal-pc">${escapeHtml(p.project_call)} · ${escapeHtml(p.id)}</div>
      <h2 class="modal-title">${escapeHtml(p.title)}</h2>

      <div class="modal-grid">
        <div>
          <div class="kv"><span class="key">Lead institution</span><span class="val">${escapeHtml(p.lead_institution || '—')}</span></div>
          <div class="kv"><span class="key">Focus area</span><span class="val">${escapeHtml(p.focus_area || '—')}</span></div>
          <div class="kv"><span class="key">Period</span><span class="val">${fmtDate(p.start_date)} → ${fmtDate(p.end_date)}</span></div>
          <div class="kv"><span class="key">Funding</span><span class="val">${fmtMoney(p.funding_amount)}</span></div>
          <div class="kv"><span class="key">Status</span><span class="val"><span class="tag status-${escapeHtml(p.status)}">${escapeHtml(p.status)}</span></span></div>
          <div class="kv"><span class="key">District</span><span class="val">${escapeHtml(p.congressional_district || '—')}</span></div>
        </div>
        <div>
          <div class="kv" style="border:none"><span class="key">Principal Investigators</span></div>
          ${renderList(p.principal_investigators)}
          ${p.co_investigators && p.co_investigators.length ? `
            <div class="kv" style="border:none; margin-top:12px"><span class="key">Co-Investigators</span></div>
            ${renderList(p.co_investigators)}` : ''}
          ${p.industry_partners && p.industry_partners.length ? `
            <div class="kv" style="border:none; margin-top:12px"><span class="key">Industry Partners</span></div>
            ${renderList(p.industry_partners)}` : ''}
        </div>
      </div>

      <div class="modal-section">
        <h3>Abstract</h3>
        <p>${escapeHtml(p.abstract || '')}</p>
      </div>

      <div class="modal-grid">
        <div class="modal-section">
          <h3>Materials used</h3>
          ${renderList(p.materials_used)}
        </div>
        <div class="modal-section">
          <h3>Processes used</h3>
          ${renderList(p.processes_used)}
        </div>
      </div>

      <div class="modal-section">
        <h3>Outcomes</h3>
        <p>${escapeHtml(p.outcomes || '')}</p>
      </div>

      ${p.publications && p.publications.length ? `
        <div class="modal-section">
          <h3>Publications</h3>
          ${renderList(p.publications)}
        </div>` : ''}

      ${p.patents && p.patents.length ? `
        <div class="modal-section">
          <h3>Patents</h3>
          ${renderList(p.patents)}
        </div>` : ''}

      <div class="modal-section">
        <h3>Keywords</h3>
        <div class="project-tags">
          ${(p.keywords || []).map((k) => `<span class="tag">${escapeHtml(k)}</span>`).join('')}
        </div>
      </div>
    `;
    $('#modal').classList.remove('hidden');
  } catch (e) {
    alert('Could not load project: ' + e.message);
  }
}

function closeModal() {
  $('#modal').classList.add('hidden');
}
$('#modal').addEventListener('click', closeModal);
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') closeModal();
});

// ───── Institutions ─────
async function loadInstitutions() {
  try {
    const insts = await api('/api/institutions', { top: 30 });
    $('#institutionsTable tbody').innerHTML = insts
      .map((i) => `
        <tr onclick="filterByInst('${escapeHtml(i.lead_institution)}')" style="cursor:pointer">
          <td>${escapeHtml(i.lead_institution)}</td>
          <td class="num">${i.count}</td>
          <td class="num">${fmtMoney(i.total_funding)}</td>
        </tr>
      `)
      .join('');
  } catch (e) {
    console.error(e);
  }
}
function filterByInst(name) {
  // Switch to projects view filtered by institution
  $('.nav-btn[data-view="projects"]').click();
  populateFilters().then(() => {
    // Add institution filter via search params on next API call
    fetch(`/api/projects?institution=${encodeURIComponent(name)}&limit=100`)
      .then((r) => r.json())
      .then((d) => renderProjectList('#projectsList', d.results));
  });
}

// ───── Search ─────
async function runSearch() {
  const q = $('#searchInput').value.trim();
  if (!q) return;
  $('#searchResults').innerHTML = '<div class="loading">Searching...</div>';
  try {
    const data = await api('/api/projects', { q, limit: 50 });
    if (data.results.length) {
      $('#searchResults').innerHTML = `<div class="empty-state" style="padding:14px; text-align:left">Found ${data.count} project${data.count === 1 ? '' : 's'} matching <strong>"${escapeHtml(q)}"</strong></div>`;
      renderProjectList('#searchResults', data.results);
      // Re-prepend the result count
      $('#searchResults').insertAdjacentHTML('afterbegin',
        `<div style="padding:10px 14px; font-size:12px; color:var(--muted); margin-bottom:8px">Found <strong>${data.count}</strong> result${data.count === 1 ? '' : 's'} for <em>"${escapeHtml(q)}"</em></div>`
      );
    } else {
      $('#searchResults').innerHTML = `<div class="empty-state">No projects matched "<strong>${escapeHtml(q)}</strong>"</div>`;
    }
  } catch (e) {
    $('#searchResults').innerHTML = `<div class="empty-state">Search error: ${e.message}</div>`;
  }
}
$('#searchInput').addEventListener('keydown', (e) => {
  if (e.key === 'Enter') runSearch();
});

// ───── Boot ─────
loadSession().then(() => loadDashboard());
