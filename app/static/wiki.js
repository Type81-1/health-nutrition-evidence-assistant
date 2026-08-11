/* ═══════════════════════════════════════════════════
   Wiki / 证据库浏览 — 交互逻辑
   ═══════════════════════════════════════════════════ */

const state = {
  query: '',
  level: '',
  yearFrom: 0,
  yearTo: 3000,
  page: 1,
  size: 24,
  total: 0,
  totalPages: 0,
};

// ── Init ────────────────────────────────────────────

async function init() {
  await loadStats();
  await loadArticles();
  setupFilters();
  setupModal();
}

async function loadStats() {
  try {
    const res = await fetch('/api/knowledge?size=0');
    const data = await res.json();
    renderStats(data);
    populateFilters(data);
  } catch (e) {
    document.getElementById('wiki-stats').innerHTML =
      '<div class="stat-card" style="grid-column:1/-1">无法加载统计数据</div>';
  }
}

function renderStats(d) {
  const levels = d.evidence_levels || {};
  const topLevel = Object.entries(levels).sort((a, b) => b[1] - a[1])[0];
  document.getElementById('wiki-stats').innerHTML = `
    <div class="stat-card">
      <div class="stat-value">${d.total_articles}</div>
      <div class="stat-label">循证文献</div>
    </div>
    <div class="stat-card">
      <div class="stat-value">${d.total_journals}</div>
      <div class="stat-label">来源期刊</div>
    </div>
    <div class="stat-card">
      <div class="stat-value">${d.year_span}</div>
      <div class="stat-label">年份跨度</div>
    </div>
    <div class="stat-card">
      <div class="stat-value">${topLevel ? topLevel[0] : '--'}</div>
      <div class="stat-label">最多证据等级（${topLevel ? topLevel[1] : 0} 篇）</div>
    </div>
  `;
}

function populateFilters(d) {
  const levelSelect = document.getElementById('filter-level');
  const levels = d.evidence_levels || {};
  for (const [name, count] of Object.entries(levels)) {
    levelSelect.innerHTML += `<option value="${name}">${name} (${count})</option>`;
  }
  const yearSelect = document.getElementById('filter-year');
  const yearDist = d.year_distribution || {};
  const years = Object.keys(yearDist).filter(y => y.length === 4).sort();
  const decades = new Set();
  for (const y of years) decades.add(y.slice(0, 3) + '0');
  for (const dec of [...decades].sort()) {
    const end = String(parseInt(dec) + 9);
    yearSelect.innerHTML += `<option value="${dec}|${end}">${dec}-${end}</option>`;
  }
}

// ── Article loading ────────────────────────────────

async function loadArticles() {
  const grid = document.getElementById('wiki-grid');
  grid.innerHTML = '<div class="wiki-loading">加载中...</div>';

  const params = new URLSearchParams({
    q: state.query,
    level: state.level,
    year_from: state.yearFrom,
    year_to: state.yearTo,
    page: state.page,
    size: state.size,
  });

  try {
    const res = await fetch(`/api/knowledge?${params}`);
    const data = await res.json();
    state.total = data.filtered_total;
    state.totalPages = Math.ceil(data.filtered_total / state.size);
    renderArticles(data.articles);
    renderPagination();
  } catch (e) {
    grid.innerHTML = '<div class="wiki-loading">加载失败，请重试</div>';
  }
}

function renderArticles(articles) {
  const grid = document.getElementById('wiki-grid');
  if (!articles.length) {
    grid.innerHTML = `<div class="wiki-empty">
      <h3>没有匹配的文献</h3>
      <p>试试调整筛选条件或搜索关键词</p>
    </div>`;
    return;
  }
  grid.innerHTML = articles.map(a => `
    <article class="article-card" onclick="openArticle('${a.id}')" data-id="${a.id}">
      <div class="article-card-header">
        <span class="article-card-title">${esc(a.title)}</span>
        ${evidenceBadge(a.evidence_level)}
      </div>
      <div class="article-card-meta">
        <span>${esc(shortJournal(a.source_type))}</span>
        <span>·</span>
        <span>${esc(a.year)}</span>
      </div>
      <p class="article-card-excerpt">${esc(a.excerpt)}</p>
      <div class="article-card-footer">
        <span class="article-card-link">查看详情 →</span>
      </div>
    </article>
  `).join('');
}

function evidenceBadge(level) {
  const map = {
    '系统综述/Meta分析': { cls: 'badge-gold', label: 'Meta' },
    '临床指南/专家共识': { cls: 'badge-blue', label: '指南' },
    '随机对照试验': { cls: 'badge-green', label: 'RCT' },
    '综述': { cls: 'badge-teal', label: '综述' },
    '观察性研究': { cls: 'badge-gray', label: '观察' },
  };
  const b = map[level] || { cls: 'badge-gray', label: level.slice(0, 4) };
  return `<span class="ev-badge ${b.cls}">${b.label}</span>`;
}

function shortJournal(src) {
  return src.split('·')[0].replace('PubMed', 'PMID').replace('Europe PMC', 'EPMC').slice(0, 28);
}

function esc(str) {
  return String(str).replace(/[&<>'"]/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[c]));
}

// ── Pagination ─────────────────────────────────────

function renderPagination() {
  const el = document.getElementById('wiki-pagination');
  if (state.totalPages <= 1) { el.innerHTML = ''; return; }
  let html = `<button class="page-btn" ${state.page <= 1 ? 'disabled' : ''} onclick="goPage(${state.page - 1})">‹</button>`;
  const start = Math.max(1, state.page - 2);
  const end = Math.min(state.totalPages, state.page + 2);
  for (let i = start; i <= end; i++) {
    html += `<button class="page-btn ${i === state.page ? 'active' : ''}" onclick="goPage(${i})">${i}</button>`;
  }
  html += `<button class="page-btn" ${state.page >= state.totalPages ? 'disabled' : ''} onclick="goPage(${state.page + 1})">›</button>`;
  html += `<span style="margin-left:12px;font-size:13px;color:var(--muted);align-self:center">共 ${state.total} 篇</span>`;
  el.innerHTML = html;
}

function goPage(n) {
  if (n < 1 || n > state.totalPages) return;
  state.page = n;
  loadArticles();
  document.getElementById('wiki-grid').scrollIntoView({ behavior: 'smooth' });
}

// ── Filters ────────────────────────────────────────

function setupFilters() {
  let debounce;
  document.getElementById('filter-search').addEventListener('input', e => {
    clearTimeout(debounce);
    debounce = setTimeout(() => {
      state.query = e.target.value.trim();
      state.page = 1;
      loadArticles();
      updateFilterTags();
    }, 350);
  });
  document.getElementById('filter-level').addEventListener('change', e => {
    state.level = e.target.value;
    state.page = 1;
    loadArticles();
    updateFilterTags();
  });
  document.getElementById('filter-year').addEventListener('change', e => {
    const val = e.target.value;
    if (val) {
      const [from, to] = val.split('|');
      state.yearFrom = parseInt(from);
      state.yearTo = parseInt(to);
    } else {
      state.yearFrom = 0;
      state.yearTo = 3000;
    }
    state.page = 1;
    loadArticles();
    updateFilterTags();
  });
}

function updateFilterTags() {
  const el = document.getElementById('filter-active');
  let tags = '';
  if (state.query) tags += `<span class="filter-tag">搜索: ${esc(state.query)} <button onclick="clearFilter('query')">&times;</button></span>`;
  if (state.level) tags += `<span class="filter-tag">${esc(state.level)} <button onclick="clearFilter('level')">&times;</button></span>`;
  if (state.yearFrom > 0) tags += `<span class="filter-tag">${state.yearFrom}-${state.yearTo} <button onclick="clearFilter('year')">&times;</button></span>`;
  el.innerHTML = tags;
}

function clearFilter(type) {
  if (type === 'query') {
    state.query = '';
    document.getElementById('filter-search').value = '';
  } else if (type === 'level') {
    state.level = '';
    document.getElementById('filter-level').value = '';
  } else if (type === 'year') {
    state.yearFrom = 0; state.yearTo = 3000;
    document.getElementById('filter-year').value = '';
  }
  state.page = 1;
  loadArticles();
  updateFilterTags();
}

// ── Modal ──────────────────────────────────────────

let _articleCache = {};

function setupModal() {
  document.getElementById('modal-close').addEventListener('click', closeModal);
  document.getElementById('article-modal').addEventListener('click', e => {
    if (e.target === e.currentTarget) closeModal();
  });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && document.getElementById('article-modal').classList.contains('is-open')) {
      closeModal();
    }
  });
}

async function openArticle(id) {
  const modal = document.getElementById('article-modal');
  const body = document.getElementById('modal-body');
  modal.classList.add('is-open');
  body.innerHTML = '<p style="color:var(--muted)">加载中...</p>';

  // Load full article data
  try {
    let article;
    if (_articleCache[id]) {
      article = _articleCache[id];
    } else {
      // Fetch all articles for this ID (simplified — search by title)
      const res = await fetch(`/api/knowledge?q=${encodeURIComponent(id)}&size=1`);
      const data = await res.json();
      article = data.articles[0];
      if (article) _articleCache[id] = article;
    }

    if (!article) {
      body.innerHTML = '<p style="color:var(--muted)">文章未找到</p>';
      return;
    }

    body.innerHTML = `
      <h2>${esc(article.title)}</h2>
      <div class="modal-meta">
        ${evidenceBadge(article.evidence_level)}
        <span>${esc(article.source_type)}</span>
        <span>${esc(article.year)}</span>
      </div>
      <div class="modal-content">${esc(article.excerpt)}</div>
      ${article.url ? `<a class="modal-link" href="${esc(article.url)}" target="_blank" rel="noreferrer">在 PubMed 中查看原文 →</a>` : ''}
    `;
  } catch (e) {
    body.innerHTML = '<p style="color:var(--muted)">加载失败</p>';
  }
}

function closeModal() {
  document.getElementById('article-modal').classList.remove('is-open');
}

// ── Bootstrap ──────────────────────────────────────
init();
