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
      const roleLabel = { admin: 'Admin', dow: 'DoW', member: 'Member' }[user.role] || user.role;
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
    if (v === 'knowledge') {
      initKnowledgeBase();
    }
    if (v === 'insights') {
      initInsights();
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
      head.innerHTML = `<div style="font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;margin-bottom:4px">DoW PEO acquisition pathway</div>
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

// ═══ LLM KNOWLEDGE BASE ═══

let _kbInitDone = false;
let _kbConcepts = [];
let _kbFilter = 'all';

async function initKnowledgeBase() {
  if (_kbInitDone) return;
  _kbInitDone = true;
  try {
    const data = await fetch('/api/knowledge-base/concepts', {credentials: 'same-origin'}).then(r => r.json());
    _kbConcepts = data.concepts || [];
    renderKbSidebar();
  } catch (e) {
    console.error('KB init failed', e);
  }
}

function renderKbSidebar() {
  const list = $('#kbConceptList');
  if (!list) return;
  const q = ($('#kbSearchInput')?.value || '').toLowerCase();
  const filtered = _kbConcepts.filter(c => {
    if (_kbFilter !== 'all' && c.kind !== _kbFilter) return false;
    if (q && !c.title.toLowerCase().includes(q) && !(c.abstract || '').toLowerCase().includes(q)) return false;
    return true;
  });
  list.innerHTML = filtered.map(c => {
    const iconLetter = {ontology:'KG', paper:'📄', relationship:'🔗'}[c.kind] || '?';
    const meta = c.entity_count ? `${c.entity_count} entities` :
                 c.year ? `${c.year}${c.project_call ? ' · ' + c.project_call : ''}` :
                 c.count ? `${c.count} links` : '';
    return `
      <div class="kb-concept-item" data-id="${c.id}" data-kind="${c.kind}" onclick="openKbArticle('${c.id}')">
        <div class="kb-concept-icon ${c.kind}">${iconLetter}</div>
        <div class="kb-concept-info">
          <div class="kb-concept-title">${escapeHtml(c.title)}</div>
          <div class="kb-concept-meta">${escapeHtml(meta)}</div>
        </div>
      </div>
    `;
  }).join('');
}
function filterKbConcepts() { renderKbSidebar(); }
function setKbFilter(btn, filter) {
  _kbFilter = filter;
  $$('.kb-pill').forEach(p => p.classList.remove('active'));
  btn.classList.add('active');
  renderKbSidebar();
}

async function openKbArticle(conceptId) {
  $$('.kb-concept-item').forEach(i => i.classList.remove('active'));
  const active = document.querySelector(`.kb-concept-item[data-id="${conceptId}"]`);
  if (active) active.classList.add('active');

  const article = $('#kbArticle');
  article.innerHTML = '<div style="padding:60px;text-align:center;color:var(--muted)">Loading article…</div>';

  try {
    const data = await fetch(`/api/knowledge-base/article/${encodeURIComponent(conceptId)}`, {credentials: 'same-origin'}).then(r => r.json());
    if (data.type === 'ontology') {
      renderKbOntologyArticle(article, data);
    } else if (data.type === 'paper') {
      renderKbPaperArticle(article, data);
    }
  } catch (e) {
    article.innerHTML = `<div style="padding:40px;color:var(--muted)">Error: ${e.message}</div>`;
  }
}

function renderKbOntologyArticle(el, data) {
  const entities = data.entities || [];
  const chunks = data.related_chunks || [];
  const backlinks = [...new Set(data.backlinks || [])];
  el.innerHTML = `
    <div class="kb-article-header">
      <div class="kb-breadcrumb">Knowledge Graph → ${data.title}</div>
      <h2>${escapeHtml(data.title)}</h2>
      <p style="color:var(--muted);font-size:13px">${entities.length} entities in the ontology · ${chunks.length} related text segments</p>
    </div>
    <div class="kb-article-section">
      <h3>Entities (${entities.length})</h3>
      ${entities.map(e => {
        let props = {};
        try { props = typeof e.properties === 'string' ? JSON.parse(e.properties) : (e.properties || {}); } catch(_){}
        const propStr = Object.entries(props).slice(0, 4).map(([k,v]) => `${k.replace(/_/g,' ')}=${v}`).join(' · ');
        return `
          <div class="kb-entity-card" onclick="openInsDetail('${e.id}')">
            <div class="kb-entity-badge">🔬</div>
            <div>
              <div class="kb-entity-name">${escapeHtml(e.name)}</div>
              <div class="kb-entity-detail">${escapeHtml(e.vendor || '')}${propStr ? ' · ' + propStr : ''}</div>
              <div class="kb-entity-detail" style="margin-top:2px">${e.rel_count || 0} relationships</div>
            </div>
          </div>
        `;
      }).join('')}
    </div>
    ${chunks.length ? `
    <div class="kb-article-section">
      <h3>Related Passages</h3>
      ${chunks.map(c => `
        <div class="kb-chunk-ref">
          ${escapeHtml((c.text || '').slice(0, 300))}${(c.text || '').length > 300 ? '…' : ''}
          <div class="kb-chunk-source">Source: ${escapeHtml(c.source_title || c.project_id || '—')} · ${c.section}</div>
        </div>
      `).join('')}
    </div>` : ''}
    ${backlinks.length ? `
    <div class="kb-article-section">
      <h3>Backlinks</h3>
      ${backlinks.map(b => `<span class="kb-backlink" onclick="openKbArticle('${b}')">${b.replace('concept-','').replace(/_/g,' ')}</span>`).join('')}
    </div>` : ''}
  `;
}

function renderKbPaperArticle(el, data) {
  const a = data.asset || {};
  const chunks = data.chunks || [];
  el.innerHTML = `
    <div class="kb-article-header">
      <div class="kb-breadcrumb">Papers → ${a.year || '—'}</div>
      <h2>${escapeHtml(data.title)}</h2>
      <p style="color:var(--muted);font-size:13px">${a.category} · ${a.year || 'n.d.'} · ${a.pages || '?'} pages · ${(a.full_text_chars || 0).toLocaleString()} chars indexed</p>
    </div>
    ${a.funding_acknowledgment ? `
    <div class="kb-article-section">
      <h3>Funding Acknowledgment</h3>
      <div class="kb-chunk-ref" style="font-style:italic">"${escapeHtml(a.funding_acknowledgment.slice(0, 400))}"</div>
    </div>` : ''}
    ${a.abstract ? `
    <div class="kb-article-section">
      <h3>Abstract / Opening Text</h3>
      <div style="font-size:13px;line-height:1.6">${escapeHtml(a.abstract.slice(0, 600))}</div>
    </div>` : ''}
    ${chunks.length ? `
    <div class="kb-article-section">
      <h3>Indexed Content (${chunks.length} chunks)</h3>
      ${chunks.slice(0, 6).map(c => `
        <div class="kb-chunk-ref">
          ${escapeHtml((c.text || '').slice(0, 250))}…
          <div class="kb-chunk-source">Section: ${c.section} · Page ${c.page}</div>
        </div>
      `).join('')}
    </div>` : ''}
    ${data.download_url ? `
    <div class="kb-article-section">
      <h3>Download</h3>
      <a href="${data.download_url}" target="_blank" class="file-card" style="display:inline-flex;text-decoration:none;color:inherit">
        <div class="file-icon pdf">PDF</div>
        <div class="file-meta"><div class="file-name">${escapeHtml(a.title?.slice(0,50))}</div><div class="file-desc">${((a.file_size_bytes || 0)/1024/1024).toFixed(1)} MB</div></div>
        <div class="file-action">Open ↗</div>
      </a>
    </div>` : ''}
  `;
}

async function runKbQuery() {
  const q = $('#kbQueryInput')?.value?.trim();
  if (!q) return;
  const panel = $('#kbQueryResult');
  panel.innerHTML = '<div style="padding:12px;text-align:center;color:var(--muted);font-size:12px">Querying GraphRAG…</div>';
  try {
    const d = await fetch('/api/graphrag', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({question: q}), credentials: 'same-origin',
    }).then(r => r.json());
    let html = `<div style="padding:14px;background:var(--bg);border:1px solid var(--border);border-radius:10px;font-size:13px;line-height:1.6;margin-bottom:8px">${escapeHtml(d.answer)}</div>`;
    html += `<div style="display:flex;gap:6px;flex-wrap:wrap">`;
    for (const c of d.citations) {
      const color = {pdf:'#1e40af',pptx:'#ea580c',public:'#047857',narrative:'#6b7280'}[c.source_type] || '#6b7280';
      html += `<span style="font-size:10px;padding:3px 8px;border-radius:5px;background:${color}22;color:${color};font-weight:600;cursor:pointer" title="${escapeHtml(c.snippet?.slice(0,100) || '')}">[${c.source_type}] ${escapeHtml((c.project_title || '').slice(0,30))}</span>`;
    }
    html += `</div>`;
    panel.innerHTML = html;
  } catch (e) {
    panel.innerHTML = `<div style="color:var(--muted)">${e.message}</div>`;
  }
}

// ═══ INSIGHTS VISUALIZER ═══

let _insInitDone = false;
let _insData = {nodes:[], edges:[]};
let _insFilter = 'all';
let _insView = 'grid';

async function initInsights() {
  if (_insInitDone) return;
  _insInitDone = true;
  try {
    _insData = await fetch('/api/insights/graph', {credentials: 'same-origin'}).then(r => r.json());
    renderInsights();
  } catch (e) {
    console.error('Insights init failed', e);
  }
}

function renderInsights() {
  const grid = $('#insGrid');
  if (!grid) return;

  // Count connections per node
  const connCount = {};
  for (const e of _insData.edges) {
    connCount[e.source] = (connCount[e.source] || 0) + 1;
    connCount[e.target] = (connCount[e.target] || 0) + 1;
  }

  let nodes = _insData.nodes || [];
  if (_insFilter !== 'all') {
    nodes = nodes.filter(n => n.group === _insFilter);
  }

  // Sort by connection count (most connected first)
  nodes.sort((a, b) => (connCount[b.id] || 0) - (connCount[a.id] || 0));

  if (_insView === 'clusters') {
    // Group by type
    const groups = {};
    for (const n of nodes) {
      const g = n.group;
      if (!groups[g]) groups[g] = [];
      groups[g].push(n);
    }
    let html = '';
    for (const [group, items] of Object.entries(groups)) {
      html += `<div style="grid-column:1/-1;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);padding:10px 0 4px;border-bottom:1px solid var(--border);margin-top:8px">${group} (${items.length})</div>`;
      html += items.map(n => renderInsNode(n, connCount)).join('');
    }
    grid.innerHTML = html;
  } else if (_insView === 'papers') {
    const papers = nodes.filter(n => n.group === 'paper');
    grid.innerHTML = papers.map(n => renderInsNode(n, connCount)).join('');
  } else {
    grid.innerHTML = nodes.map(n => renderInsNode(n, connCount)).join('');
  }

  const countEl = $('#insNodeCount');
  if (countEl) countEl.textContent = `${nodes.length} nodes · ${_insData.edges.length} edges`;
}

function renderInsNode(n, connCount) {
  const conns = connCount[n.id] || 0;
  const meta = n.vendor ? n.vendor :
               n.year ? `${n.year}${n.pc ? ' · ' + n.pc : ''}` :
               n.subtype ? n.subtype.replace(/_/g, ' ') : '';
  return `
    <div class="ins-node ${n.group}" onclick="openInsDetail('${n.id}')" title="${escapeHtml(n.label)}">
      <div class="ins-node-type">
        <span style="width:8px;height:8px;border-radius:50%;display:inline-block;background:currentColor"></span>
        ${n.group} ${n.subtype && n.subtype !== n.group ? '· ' + n.subtype.replace(/_/g,' ') : ''}
      </div>
      <div class="ins-node-label">${escapeHtml(n.label)}</div>
      <div class="ins-node-meta">${escapeHtml(meta)}</div>
      ${conns > 0 ? `<div class="ins-node-connections">${conns} ↔</div>` : ''}
    </div>
  `;
}

function setInsFilter(btn, filter) {
  _insFilter = filter;
  $$('.ins-pill').forEach(p => p.classList.remove('active'));
  btn.classList.add('active');
  renderInsights();
}
function setInsView(btn, view) {
  _insView = view;
  $$('.ins-view-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  renderInsights();
}

async function openInsDetail(nodeId) {
  const detail = $('#insDetail');
  const content = $('#insDetailContent');
  if (!detail || !content) return;
  detail.classList.remove('hidden');

  const node = _insData.nodes.find(n => n.id === nodeId);
  if (!node) { content.innerHTML = '<p>Node not found</p>'; return; }

  // Find connected nodes
  const connected = [];
  for (const e of _insData.edges) {
    if (e.source === nodeId) {
      const t = _insData.nodes.find(n => n.id === e.target);
      if (t) connected.push({node: t, rel: e.type, direction: '→'});
    }
    if (e.target === nodeId) {
      const s = _insData.nodes.find(n => n.id === e.source);
      if (s) connected.push({node: s, rel: e.type, direction: '←'});
    }
  }

  // Check if it's a public asset (paper, patent, etc.) — offer download
  let downloadSection = '';
  if (node.group === 'paper' && node.has_file) {
    downloadSection = `
      <div style="margin-top:16px">
        <a href="/api/public-dataset/${encodeURIComponent(nodeId)}/download" target="_blank"
           class="file-card" style="display:flex;text-decoration:none;color:inherit">
          <div class="file-icon pdf">PDF</div>
          <div class="file-meta"><div class="file-name">Download source document</div><div class="file-desc">Click to open</div></div>
          <div class="file-action">Open ↗</div>
        </a>
      </div>
    `;
  } else if (node.group === 'project') {
    downloadSection = `
      <div style="margin-top:16px;display:grid;grid-template-columns:1fr 1fr;gap:8px">
        <a href="/api/projects/${encodeURIComponent(nodeId)}/files/pdf" target="_blank"
           class="file-card" style="display:flex;text-decoration:none;color:inherit;padding:10px 12px">
          <div class="file-icon pdf" style="width:32px;height:32px;font-size:9px">PDF</div>
          <div class="file-meta"><div class="file-name">Final Report</div></div>
        </a>
        <a href="/api/projects/${encodeURIComponent(nodeId)}/files/pptx" target="_blank"
           class="file-card" style="display:flex;text-decoration:none;color:inherit;padding:10px 12px">
          <div class="file-icon pptx" style="width:32px;height:32px;font-size:9px">PPT</div>
          <div class="file-meta"><div class="file-name">Briefing</div></div>
        </a>
      </div>
    `;
  }

  content.innerHTML = `
    <div style="margin-bottom:16px">
      <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;margin-bottom:6px;color:${
        {material:'#4f46e5',process:'#059669',performance:'#d97706',paper:'#7c3aed',project:'#0891b2'}[node.group] || 'var(--muted)'
      }">${node.group} · ${(node.subtype || '').replace(/_/g,' ')}</div>
      <h2 style="margin:0 0 8px;font-size:18px;line-height:1.3">${escapeHtml(node.label)}</h2>
      ${node.vendor ? `<div style="font-size:12px;color:var(--muted)">Vendor: ${escapeHtml(node.vendor)}</div>` : ''}
      ${node.year ? `<div style="font-size:12px;color:var(--muted)">Year: ${node.year}${node.pc ? ' · ' + node.pc : ''}</div>` : ''}
    </div>

    ${downloadSection}

    ${connected.length ? `
    <div style="margin-top:20px">
      <div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin-bottom:10px;padding-bottom:6px;border-bottom:1px solid var(--border)">
        Connected Nodes (${connected.length})
      </div>
      ${connected.slice(0, 20).map(c => `
        <div onclick="openInsDetail('${c.node.id}')" style="display:flex;align-items:center;gap:10px;padding:8px 10px;border-radius:8px;cursor:pointer;margin-bottom:4px;transition:all .12s;font-size:12px" onmouseover="this.style.background='rgba(10,143,143,.05)'" onmouseout="this.style.background='transparent'">
          <span style="font-size:10px;color:var(--muted);font-family:'JetBrains Mono',monospace;min-width:20px">${c.direction}</span>
          <span style="width:6px;height:6px;border-radius:50%;background:${
            {material:'#4f46e5',process:'#059669',performance:'#d97706',paper:'#7c3aed',project:'#0891b2'}[c.node.group] || '#6b7280'
          };flex-shrink:0"></span>
          <span style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escapeHtml(c.node.label)}</span>
          <span style="font-size:10px;color:var(--muted)">${c.rel.replace(/_/g,' ')}</span>
        </div>
      `).join('')}
    </div>` : '<div style="padding:20px;color:var(--muted);font-size:12px">No direct connections in the knowledge graph.</div>'}

    <div style="margin-top:20px">
      <div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin-bottom:8px">Query about this entity</div>
      <button onclick="document.querySelector('.nav-btn[data-view=knowledge]').click(); setTimeout(() => { document.getElementById('kbQueryInput').value = '${escapeHtml(node.label.replace(/'/g, ''))}'; runKbQuery(); }, 500);"
        style="padding:8px 16px;border-radius:8px;border:1px solid var(--teal);background:transparent;color:var(--teal);font-size:12px;font-weight:600;cursor:pointer;transition:all .12s"
        onmouseover="this.style.background='rgba(10,143,143,.08)'" onmouseout="this.style.background='transparent'">
        Ask Knowledge Base about "${escapeHtml(node.label.slice(0,30))}" →
      </button>
    </div>
  `;
}

function closeInsDetail() {
  const d = $('#insDetail');
  if (d) d.classList.add('hidden');
}

window.filterPubBy = filterPubBy;
window.loadPublicAssets = loadPublicAssets;
window.openAssetModal = openAssetModal;
window.initKnowledgeBase = initKnowledgeBase;
window.openKbArticle = openKbArticle;
window.filterKbConcepts = filterKbConcepts;
window.setKbFilter = setKbFilter;
window.runKbQuery = runKbQuery;
window.initInsights = initInsights;
window.setInsFilter = setInsFilter;
window.setInsView = setInsView;
window.openInsDetail = openInsDetail;
window.closeInsDetail = closeInsDetail;

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
