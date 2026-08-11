const questionInput = document.querySelector('#question');
const askButton = document.querySelector('#ask-button');
const emptyState = document.querySelector('#empty-state');
const answerSection = document.querySelector('#answer-section');
const answerContent = document.querySelector('#answer-content');
const safetyNote = document.querySelector('#safety-note');
const citationList = document.querySelector('#citation-list');
const sourceCount = document.querySelector('#source-count');
const pubmedToggle = document.querySelector('#pubmed-toggle');
const pubmedResults = document.querySelector('#pubmed-results');
const retrievalNote = document.querySelector('#retrieval-note');
const historyToggle = document.querySelector('#history-toggle');
const historyCount = document.querySelector('#history-count');
const historyDrawer = document.querySelector('#history-drawer');
const historyBackdrop = document.querySelector('#history-backdrop');
const historyClose = document.querySelector('#history-close');
const historyList = document.querySelector('#history-list');
const historyEmpty = document.querySelector('#history-empty');
const historyClear = document.querySelector('#history-clear');
const ethicsToggle = document.querySelector('#ethics-toggle');
const ethicsDialog = document.querySelector('#ethics-dialog');
const ethicsClose = document.querySelector('#ethics-close');

let lastQuestion = '';
let pinnedEvidence = [];
const HISTORY_KEY = 'nutrition-evidence-history-v1';
const HISTORY_LIMIT = 30;
const simplifiedEvidence = new Map();

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>'"]/g, char => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', "'":'&#39;', '"':'&quot;' }[char]));
}

function renderMarkdown(text) {
  return text.split('\n').map(line => {
    if (line.startsWith('### ')) return `<h3>${escapeHtml(line.slice(4))}</h3>`;
    if (!line.trim()) return '';
    const labels = [...line.matchAll(/\[E(\d+)\]/g)].map(match => `E${match[1]}`);
    const withCitations = escapeHtml(line).replace(/\[E(\d+)\]/g, (_, number) => `<button class="citation-ref" type="button" data-evidence-label="E${number}" title="查看 E${number} 证据原文">[E${number}]</button>`);
    const attributes = labels.length ? ` class="evidence-claim" data-citations="${labels.join(',')}"` : '';
    return `<p${attributes}>${withCitations}</p>`;
  }).join('');
}

function renderCitations(citations) {
  sourceCount.textContent = citations.length;
  citationList.innerHTML = citations.map(citation => `
    <article class="citation-card" id="citation-${escapeHtml(citation.label)}" data-evidence-label="${escapeHtml(citation.label)}">
      <div class="citation-title-row">
        <button class="citation-label" type="button" data-focus-claim="${escapeHtml(citation.label)}" title="定位对应结论">[${escapeHtml(citation.label)}]</button>
        <a href="${escapeHtml(citation.url)}" target="_blank" rel="noreferrer">${escapeHtml(citation.title)}</a>
      </div>
      <div class="citation-meta">${escapeHtml(citation.source_type)} · ${escapeHtml(citation.year)} · ${escapeHtml(citation.evidence_level)}</div>
      <div class="citation-provenance"><span>${escapeHtml(citation.evidence_role)}</span><code>${escapeHtml(citation.source_id)}</code></div>
      <div class="citation-excerpt-heading">
        <div class="citation-excerpt-label">证据摘录</div>
        <button class="simplify-button" type="button" data-simplify-source="${escapeHtml(citation.source_id)}">精简</button>
      </div>
      <p class="citation-excerpt" data-original-excerpt="${escapeHtml(citation.excerpt)}">${escapeHtml(citation.excerpt)}</p>
    </article>`).join('');
  bindEvidenceInteractions();
  bindSimplifyInteractions();
}

function bindSimplifyInteractions() {
  document.querySelectorAll('[data-simplify-source]').forEach(button => {
    button.addEventListener('click', async () => {
      const sourceId = button.dataset.simplifySource;
      const excerpt = button.closest('.citation-card')?.querySelector('.citation-excerpt');
      if (!excerpt) return;
      if (button.dataset.mode === 'plain') {
        excerpt.textContent = excerpt.dataset.originalExcerpt;
        button.dataset.mode = 'original';
        button.textContent = '精简';
        return;
      }
      button.disabled = true;
      button.textContent = '处理中';
      try {
        let plainLanguage = simplifiedEvidence.get(sourceId);
        if (!plainLanguage) {
          const response = await fetch('/api/evidence/simplify', {
            method:'POST',
            headers:{'Content-Type':'application/json'},
            body:JSON.stringify({source_id:sourceId}),
          });
          if (!response.ok) throw new Error();
          const data = await response.json();
          plainLanguage = data.plain_language;
          simplifiedEvidence.set(sourceId, plainLanguage);
        }
        excerpt.textContent = plainLanguage;
        button.dataset.mode = 'plain';
        button.textContent = '原文';
      } catch (_) {
        button.textContent = '重试';
      } finally {
        button.disabled = false;
      }
    });
  });
}

function applyEvidenceHighlight(labels) {
  const active = new Set(labels);
  document.querySelectorAll('.evidence-claim').forEach(claim => {
    const claimLabels = (claim.dataset.citations || '').split(',');
    claim.classList.toggle('is-evidence-active', claimLabels.some(label => active.has(label)));
  });
  document.querySelectorAll('.citation-card').forEach(card => {
    card.classList.toggle('is-evidence-active', active.has(card.dataset.evidenceLabel));
  });
}

function bindEvidenceInteractions() {
  pinnedEvidence = [];
  document.querySelectorAll('.citation-ref').forEach(button => {
    const label = button.dataset.evidenceLabel;
    button.addEventListener('mouseenter', () => applyEvidenceHighlight([label]));
    button.addEventListener('mouseleave', () => applyEvidenceHighlight(pinnedEvidence));
    button.addEventListener('focus', () => applyEvidenceHighlight([label]));
    button.addEventListener('blur', () => applyEvidenceHighlight(pinnedEvidence));
    button.addEventListener('click', () => {
      pinnedEvidence = [label];
      applyEvidenceHighlight(pinnedEvidence);
      document.querySelector(`#citation-${label}`)?.scrollIntoView({ behavior:'smooth', block:'center' });
    });
  });
  document.querySelectorAll('.citation-card').forEach(card => {
    const label = card.dataset.evidenceLabel;
    card.addEventListener('mouseenter', () => applyEvidenceHighlight([label]));
    card.addEventListener('mouseleave', () => applyEvidenceHighlight(pinnedEvidence));
  });
  document.querySelectorAll('[data-focus-claim]').forEach(button => {
    button.addEventListener('click', () => {
      const label = button.dataset.focusClaim;
      pinnedEvidence = [label];
      applyEvidenceHighlight(pinnedEvidence);
      [...document.querySelectorAll('.evidence-claim')]
        .find(claim => (claim.dataset.citations || '').split(',').includes(label))
        ?.scrollIntoView({ behavior:'smooth', block:'center' });
    });
  });
}

function readHistory() {
  try {
    const value = JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]');
    return Array.isArray(value) ? value : [];
  } catch (_) {
    return [];
  }
}

function writeHistory(items) {
  localStorage.setItem(HISTORY_KEY, JSON.stringify(items.slice(0, HISTORY_LIMIT)));
  renderHistory();
}

function saveHistory(question, answer) {
  const existing = readHistory().filter(item => item.question !== question);
  writeHistory([{ id: crypto.randomUUID?.() || String(Date.now()), question, answer, createdAt: new Date().toISOString() }, ...existing]);
}

function formatHistoryTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return new Intl.DateTimeFormat('zh-CN', { month:'numeric', day:'numeric', hour:'2-digit', minute:'2-digit' }).format(date);
}

function renderHistory() {
  const items = readHistory();
  historyCount.textContent = items.length;
  historyEmpty.classList.toggle('is-hidden', items.length > 0);
  historyClear.disabled = items.length === 0;
  historyList.innerHTML = items.map(item => `
    <article class="history-item">
      <button class="history-entry" type="button" data-history-id="${escapeHtml(item.id)}">
        <span>${escapeHtml(item.question)}</span>
        <time>${escapeHtml(formatHistoryTime(item.createdAt))}</time>
      </button>
      <button class="history-delete" type="button" data-delete-history="${escapeHtml(item.id)}" aria-label="删除这条历史" title="删除">×</button>
    </article>`).join('');
  historyList.querySelectorAll('[data-history-id]').forEach(button => button.addEventListener('click', () => {
    const item = readHistory().find(entry => entry.id === button.dataset.historyId);
    if (!item) return;
    questionInput.value = item.question;
    showAnswer(item.question, item.answer, false);
    closeHistory();
  }));
  historyList.querySelectorAll('[data-delete-history]').forEach(button => button.addEventListener('click', () => {
    writeHistory(readHistory().filter(item => item.id !== button.dataset.deleteHistory));
  }));
}

function openHistory() {
  historyDrawer.classList.remove('is-hidden');
  historyBackdrop.classList.remove('is-hidden');
  historyDrawer.setAttribute('aria-hidden', 'false');
  historyToggle.setAttribute('aria-expanded', 'true');
  document.body.classList.add('drawer-open');
  historyClose.focus();
}

function closeHistory() {
  historyDrawer.classList.add('is-hidden');
  historyBackdrop.classList.add('is-hidden');
  historyDrawer.setAttribute('aria-hidden', 'true');
  historyToggle.setAttribute('aria-expanded', 'false');
  document.body.classList.remove('drawer-open');
}

function showAnswer(question, data, persist = true) {
  lastQuestion = question;
  answerContent.innerHTML = renderMarkdown(data.answer_markdown || '');
  safetyNote.textContent = data.safety_note || '';
  retrievalNote.textContent = data.retrieval_note || '';
  renderCitations(data.citations || []);
  pubmedResults.innerHTML = '';
  emptyState.classList.add('is-hidden');
  answerSection.classList.remove('is-hidden');
  if (persist) saveHistory(question, data);
}

async function askQuestion() {
  const question = questionInput.value.trim();
  if (question.length < 4) { questionInput.focus(); return; }
  askButton.disabled = true;
  askButton.textContent = '检索中...';
  pubmedResults.innerHTML = '';
  try {
    const response = await fetch('/api/answer', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({question}) });
    if (!response.ok) throw new Error('回答接口暂时不可用');
    const data = await response.json();
    showAnswer(question, data);
  } catch (error) {
    answerContent.innerHTML = `<p>暂时无法完成检索，请稍后重试。</p>`;
    emptyState.classList.add('is-hidden');
    answerSection.classList.remove('is-hidden');
  } finally {
    askButton.disabled = false;
    askButton.textContent = '获取证据';
  }
}

document.querySelectorAll('[data-question]').forEach(button => button.addEventListener('click', () => { questionInput.value = button.dataset.question; askQuestion(); }));
askButton.addEventListener('click', askQuestion);
questionInput.addEventListener('keydown', event => { if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') askQuestion(); });
historyToggle.addEventListener('click', openHistory);
historyClose.addEventListener('click', closeHistory);
historyBackdrop.addEventListener('click', closeHistory);
historyClear.addEventListener('click', () => {
  if (readHistory().length && window.confirm('确定清空全部对话历史吗？')) writeHistory([]);
});
document.addEventListener('keydown', event => { if (event.key === 'Escape') closeHistory(); });
ethicsToggle.addEventListener('click', () => ethicsDialog.showModal());
ethicsClose.addEventListener('click', () => ethicsDialog.close());
ethicsDialog.addEventListener('click', event => {
  if (event.target === ethicsDialog) ethicsDialog.close();
});

pubmedToggle.addEventListener('click', async () => {
  if (!lastQuestion) return;
  pubmedToggle.disabled = true;
  pubmedToggle.textContent = '正在查询...';
  try {
    const response = await fetch('/api/pubmed/search', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({query:lastQuestion, limit:4}) });
    if (!response.ok) throw new Error();
    const { articles, query_used: queryUsed } = await response.json();
    const queryNote = `<div class="pubmed-query"><span>实际检索式</span><code>${escapeHtml(queryUsed)}</code></div>`;
    const articleList = articles.map(article => `<article class="pubmed-item"><a href="${escapeHtml(article.url)}" target="_blank" rel="noreferrer">${escapeHtml(article.title)}</a><p>${escapeHtml(article.journal)} · ${escapeHtml(article.year)} · PMID ${escapeHtml(article.pmid)}</p></article>`).join('');
    pubmedResults.innerHTML = queryNote + (articleList || '<p class="citation-excerpt">未找到匹配的 PubMed 条目。</p>');
  } catch (_) {
    pubmedResults.innerHTML = '<p class="citation-excerpt">PubMed 当前无法访问，请稍后重试。</p>';
  } finally {
    pubmedToggle.disabled = false;
    pubmedToggle.textContent = '实时检索 PubMed';
  }
});

renderHistory();
