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
    // Populate status banner (non-critical, fire-and-forget)
    fetch('/api/health').then(r => r.json()).then(h => {
      const build = document.getElementById('statusBuild');
      const lat = document.getElementById('statusLatency');
      if (build) build.textContent = `v${h.version} · build ${h.build}`;
      if (lat) lat.textContent = `Avg latency: ${h.latency_ms}ms`;
    }).catch(() => {});
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
    const v = btn.dataset.view;
    if (!v) return;
    const target = $(`#view-${v}`);
    if (target) target.classList.add('active');
    if (v === 'projects' && !$('#filterPC').dataset.loaded) {
      populateFilters();
    }
    if (v === 'institutions') {
      loadInstitutions();
    }
    if (v === 'public') {
      initPublicDataset();
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
        <h3>Project documents</h3>
        <div class="files-strip">
          <a href="/api/projects/${encodeURIComponent(p.id)}/files/pdf" target="_blank" class="file-card">
            <div class="file-icon pdf">PDF</div>
            <div class="file-meta">
              <div class="file-name">Final Report</div>
              <div class="file-desc">Ontology-classified · 5–7 pages</div>
            </div>
            <div class="file-action">Download ↓</div>
          </a>
          <a href="/api/projects/${encodeURIComponent(p.id)}/files/pptx" target="_blank" class="file-card">
            <div class="file-icon pptx">PPT</div>
            <div class="file-meta">
              <div class="file-name">Project Briefing</div>
              <div class="file-desc">8 slides · executive → transition</div>
            </div>
            <div class="file-action">Download ↓</div>
          </a>
        </div>
      </div>

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

// ───── Drill-down navigation helpers ─────
function goView(view) {
  const btn = document.querySelector(`.nav-btn[data-view="${view}"]`);
  if (btn) btn.click();
}
function goProjects() { goView('projects'); loadProjects(); }

function filterByPC(pc) {
  goView('projects');
  const sel = $('#filterPC');
  if (pc) sel.value = pc;
  loadProjects();
}
function filterByFocus(focus) {
  goView('projects');
  const sel = $('#filterFocus');
  if (focus) sel.value = focus;
  loadProjects();
}
function filterByDistrict(code) {
  goView('projects');
  // Use the search box to filter by district (since we don't have a dedicated control)
  goView('search');
  $('#searchInput').value = code;
  // But districts are an exact-match filter, not FTS — use the API directly
  fetch(`/api/projects?district=${encodeURIComponent(code)}&limit=200`, {credentials: 'same-origin'})
    .then(r => r.json())
    .then(d => {
      $('#searchResults').innerHTML = '';
      const head = document.createElement('div');
      head.style.cssText = 'padding:14px 16px;background:var(--card);border:1px solid var(--border);border-radius:8px;margin-bottom:12px';
      head.innerHTML = `<div style="font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;margin-bottom:4px">Drilled in from district</div>
        <div style="font-size:15px;font-weight:700">${escapeHtml(code)} — ${d.count} project${d.count === 1 ? '' : 's'}</div>`;
      $('#searchResults').appendChild(head);
      const list = document.createElement('div');
      list.id = '_drilldown_list';
      $('#searchResults').appendChild(list);
      renderProjectList('#_drilldown_list', d.results);
    });
}
function filterByPEO(peo) {
  goView('search');
  fetch(`/api/projects?peo=${encodeURIComponent(peo)}&limit=200`, {credentials: 'same-origin'})
    .then(r => r.json())
    .then(d => {
      $('#searchResults').innerHTML = '';
      const head = document.createElement('div');
      head.style.cssText = 'padding:14px 16px;background:var(--card);border:1px solid var(--border);border-radius:8px;margin-bottom:12px';
      head.innerHTML = `<div style="font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;margin-bottom:4px">DoD PEO acquisition pathway</div>
        <div style="font-size:15px;font-weight:700">${escapeHtml(peo)} — ${d.count} aligned project${d.count === 1 ? '' : 's'}</div>`;
      $('#searchResults').appendChild(head);
      const list = document.createElement('div');
      list.id = '_drilldown_list';
      $('#searchResults').appendChild(list);
      renderProjectList('#_drilldown_list', d.results);
    });
}
// ═══ PUBLIC NEXTFLEX DATASET ═══

let _pubInitDone = false;
async function initPublicDataset() {
  if (_pubInitDone) return;
  _pubInitDone = true;
  try {
    const stats = await fetch('/api/public-dataset/stats', {credentials: 'same-origin'}).then(r => r.json());
    const pubByCat = {};
    (stats.by_category || []).forEach(c => { pubByCat[c.category] = c.n; });
    $('#pubTotal').textContent = stats.total_assets;
    $('#pubFiles').textContent = stats.with_local_files + ' / ' + stats.total_assets;
    $('#pubPapers').textContent = pubByCat.paper || 0;
    $('#pubPatents').textContent = pubByCat.patent || 0;
    $('#pubWebinars').textContent = pubByCat.webinar || 0;

    // Populate years dropdown
    const yearSel = $('#pubFilterYear');
    yearSel.innerHTML = '<option value="">All years</option>';
    (stats.by_year || []).slice().reverse().forEach(y => {
      const opt = document.createElement('option');
      opt.value = y.year; opt.textContent = `${y.year} (${y.n})`;
      yearSel.appendChild(opt);
    });
  } catch (e) {
    console.error('Public dataset stats failed', e);
  }
  loadPublicAssets();
}

function filterPubBy(category) {
  // Switch to public view if not already
  $('.nav-btn[data-view="public"]').click();
  setTimeout(() => {
    $('#pubFilterCat').value = category || '';
    $('#pubFilterYear').value = '';
    $('#pubSearchInput').value = '';
    loadPublicAssets();
  }, 50);
}

async function loadPublicAssets() {
  const cat = $('#pubFilterCat').value;
  const year = $('#pubFilterYear').value;
  const q = $('#pubSearchInput').value.trim();
  const params = new URLSearchParams();
  if (cat) params.append('category', cat);
  if (year) params.append('year', year);
  if (q) params.append('q', q);
  params.append('limit', '200');

  const list = $('#pubAssetsList');
  list.innerHTML = '<div class="loading">Loading…</div>';
  try {
    const data = await fetch(`/api/public-dataset/list?${params}`, {credentials: 'same-origin'}).then(r => r.json());
    if (!data.results || !data.results.length) {
      list.innerHTML = '<div class="empty-state">No assets match these filters.</div>';
      return;
    }
    list.innerHTML = data.results.map(renderAssetCard).join('');
  } catch (e) {
    list.innerHTML = `<div class="empty-state">Error: ${e.message}</div>`;
  }
}

function renderAssetCard(a) {
  const iconLetter = {paper:'PAP', patent:'PAT', webinar:'WBN', project_report:'RPT', pptx:'PPT'}[a.category] || 'DOC';
  const sizeStr = a.file_size_bytes ? ` · ${(a.file_size_bytes/1024/1024).toFixed(1)} MB` : '';
  const pagesStr = a.pages ? ` · ${a.pages} pages` : '';
  const yearStr = a.year ? `${a.year}` : '—';
  const pcStr = a.project_call ? ` · ${escapeHtml(a.project_call)}` : '';
  return `
    <div class="asset-card" onclick="openAssetModal('${a.id}')">
      <div class="asset-icon ${a.category}">${iconLetter}</div>
      <div class="asset-meta">
        <div style="display:flex; gap:6px; margin-bottom:4px; align-items:center; flex-wrap:wrap">
          <span class="asset-tag cat-${a.category}">${a.category.toUpperCase()}</span>
          <span style="font-size:10px; color:var(--muted); font-family:'JetBrains Mono', monospace">${yearStr}${pcStr}</span>
        </div>
        <div class="asset-title">${escapeHtml(a.title)}</div>
        <div class="asset-detail">
          ${a.agreement_numbers ? `<span>📋 ${escapeHtml(a.agreement_numbers)}</span>` : ''}
          <span>${pagesStr}${sizeStr}</span>
        </div>
      </div>
      <div class="asset-action ${a.has_local_file ? '' : 'disabled'}">${a.has_local_file ? 'View →' : 'External →'}</div>
    </div>
  `;
}

async function openAssetModal(id) {
  try {
    const a = await fetch(`/api/public-dataset/${encodeURIComponent(id)}`, {credentials: 'same-origin'}).then(r => r.json());
    const body = $('#modalBody');
    const downloadCard = a.has_local_file && a.download_url ? `
      <div class="modal-section">
        <h3>Download</h3>
        <div class="files-strip">
          <a href="${a.download_url}" target="_blank" class="file-card">
            <div class="file-icon ${a.file_path && a.file_path.endsWith('.pptx') ? 'pptx' : 'pdf'}">
              ${a.file_path && a.file_path.endsWith('.pptx') ? 'PPT' : 'PDF'}
            </div>
            <div class="file-meta">
              <div class="file-name">${escapeHtml(a.file_path.split('/').pop())}</div>
              <div class="file-desc">${(a.file_size_bytes/1024/1024).toFixed(1)} MB · ${a.pages || '?'} pages · ${a.full_text_chars.toLocaleString()} chars indexed</div>
            </div>
            <div class="file-action">Open ↗</div>
          </a>
        </div>
      </div>
    ` : `
      <div class="modal-section">
        <h3>Source</h3>
        <p style="color:var(--muted); font-size:13px">${a.source_url ? `External: <a href="${escapeHtml(a.source_url)}" target="_blank" style="color:var(--teal)">${escapeHtml(a.source_url.slice(0,80))}</a>` : 'Manifest-only entry, no local file.'}</p>
      </div>
    `;
    body.innerHTML = `
      <div class="modal-pc-tag" style="background:rgba(10,143,143,.12); color:var(--teal); display:inline-block; padding:3px 10px; border-radius:6px; font-size:10px; font-weight:700; font-family:'JetBrains Mono', monospace; margin-bottom:10px">
        ${a.category.toUpperCase()} · ${a.year || 'n.d.'}${a.project_call ? ' · ' + escapeHtml(a.project_call) : ''}
      </div>
      <h2 style="margin:0 0 12px 0; font-size:20px; line-height:1.3">${escapeHtml(a.title)}</h2>

      <div class="modal-section">
        <h3>Metadata</h3>
        <div class="modal-meta-grid">
          ${a.agreement_numbers ? `<div><div class="meta-label">Agreement</div><div class="meta-val">${escapeHtml(a.agreement_numbers)}</div></div>` : ''}
          <div><div class="meta-label">Pages</div><div class="meta-val">${a.pages || '—'}</div></div>
          <div><div class="meta-label">Indexed chunks</div><div class="meta-val">${a.indexed_chunks}</div></div>
          ${a.public_access ? `<div><div class="meta-label">Access</div><div class="meta-val">${escapeHtml(a.public_access)}</div></div>` : ''}
        </div>
      </div>

      ${a.funding_acknowledgment ? `<div class="modal-section">
        <h3>Funding acknowledgment / evidence</h3>
        <div style="font-size:12px; color:var(--text); line-height:1.6; padding:12px 14px; background:var(--bg); border-radius:8px; border:1px solid var(--border); font-style:italic">"${escapeHtml(a.funding_acknowledgment.slice(0, 600))}${a.funding_acknowledgment.length > 600 ? '...' : ''}"</div>
      </div>` : ''}

      ${a.abstract ? `<div class="modal-section">
        <h3>Abstract / opening text</h3>
        <div style="font-size:13px; line-height:1.6; padding:12px 14px; background:var(--bg); border-radius:8px; border:1px solid var(--border)">${escapeHtml(a.abstract.slice(0, 600))}${a.abstract.length > 600 ? '…' : ''}</div>
      </div>` : ''}

      ${downloadCard}

      <div class="modal-section">
        <p style="font-size:11px; color:var(--muted); margin-top:14px">
          ✓ This document's full text is indexed in the GraphRAG corpus. Try queries like
          <em>"${escapeHtml(a.title.split(' ').slice(0, 4).join(' ') + '"')}</em> in the manager dashboard query bar.
        </p>
      </div>
    `;
    $('#modal').classList.remove('hidden');
  } catch (e) {
    alert('Could not load asset: ' + e.message);
  }
}

window.filterPubBy = filterPubBy;
window.loadPublicAssets = loadPublicAssets;
window.openAssetModal = openAssetModal;

// Expose to global so manager dashboard inline handlers can navigate via parent window when needed
window.filterByDistrict = filterByDistrict;
window.filterByPEO = filterByPEO;
window.filterByPC = filterByPC;
window.filterByFocus = filterByFocus;

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
