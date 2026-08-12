/* ═══════════════════════════════════════════════════════
   食证 · app.js — 合并版
   保留: 多Agent SSE流式, Chat多轮对话, Markdown渲染, Demo模式
   新增: Wiki专题, 对话历史抽屉, 伦理弹窗, 证据高亮, 精简/科普
   ═══════════════════════════════════════════════════════ */

// ── DOM refs ──
const questionInput = document.querySelector('#question');
const askButton = document.querySelector('#ask-button');
const chatMessages = document.querySelector('#chat-messages');
const newChatButton = document.querySelector('#new-chat-button');
const agentCheckbox = document.querySelector('#agent-mode-checkbox');
const demoToggle = document.querySelector('#demo-toggle');
const demoPanel = document.getElementById('demo-panel');
const demoGrid = document.getElementById('demo-grid');
const demoClose = document.getElementById('demo-close');
const suggestions = document.querySelectorAll('.suggestions button[data-question]');
// Wiki
const wikiToggle = document.querySelector('#wiki-toggle');
const wikiMenuList = document.querySelector('#wiki-menu-list');
const wikiSection = document.querySelector('#wiki-section');
const wikiClose = document.querySelector('#wiki-close');
const wikiTitle = document.querySelector('#wiki-title');
const wikiSubtitle = document.querySelector('#wiki-subtitle');
const wikiUpdated = document.querySelector('#wiki-updated');
const wikiSections = document.querySelector('#wiki-sections');
const wikiReferences = document.querySelector('#wiki-references');
// History
const historyToggle = document.querySelector('#history-toggle');
const historyCount = document.querySelector('#history-count');
const historyDrawer = document.querySelector('#history-drawer');
const historyBackdrop = document.querySelector('#history-backdrop');
const historyClose = document.querySelector('#history-close');
const historyList = document.querySelector('#history-list');
const historyEmpty = document.querySelector('#history-empty');
const historyClear = document.querySelector('#history-clear');
// Ethics
const ethicsToggle = document.querySelector('#ethics-toggle');
const ethicsDialog = document.querySelector('#ethics-dialog');
const ethicsCloseBtn = document.querySelector('#ethics-close');

// ── State ──
let messages = [];
let conversationId = null;
let agentMode = false;
const HISTORY_KEY = 'nutrition-evidence-history-v1';
const HISTORY_LIMIT = 30;
const simplifiedEvidence = new Map();
const explainedEvidence = new Map();
let pinnedEvidence = [];

const HIGHLIGHT_TERMS = [];
const REJECTION_PREAMBLE = '抱歉，';

// ── Helpers ──
function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>'"]/g, char => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', "'":'&#39;', '"':'&quot;' }[char]));
}

// ── Markdown → HTML ──
function renderAnswer(text, msgIndex) {
  const lines = text.split('\n');
  let html = '';
  let inUl = false, inOl = false;

  function closeLists() {
    if (inUl) { html += '</ul>'; inUl = false; }
    if (inOl) { html += '</ol>'; inOl = false; }
  }

  function inlineMarkdown(s) {
    s = escapeHtml(s);
    s = s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    s = s.replace(/__(.+?)__/g, '<strong>$1</strong>');
    s = s.replace(/\*(.+?)\*/g, '<em>$1</em>');
    s = s.replace(/`(.+?)`/g, '<code>$1</code>');
    s = s.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noreferrer">$1</a>');
    s = s.replace(/\[E(\d+)\]/g, (_, number) => `<button class="citation-ref" type="button" data-evidence-label="E${number}" title="查看 E${number} 证据">[E${number}]</button>`);
    HIGHLIGHT_TERMS.forEach(term => {
      s = s.replace(new RegExp(term, 'g'), `<mark class="kw">${term}</mark>`);
    });
    return s;
  }

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const trimmed = line.trim();

    if (!trimmed) { closeLists(); continue; }

    const headingMatch = trimmed.match(/^(#{1,4})\s+(.+)/);
    if (headingMatch) {
      closeLists();
      const level = headingMatch[1].length;
      html += `<h${level} class="md-heading">${inlineMarkdown(headingMatch[2])}</h${level}>`;
      continue;
    }

    const ulMatch = trimmed.match(/^[-*+]\s+(.+)/);
    if (ulMatch) {
      if (!inUl) { html += '<ul class="md-list">'; inUl = true; }
      html += `<li>${inlineMarkdown(ulMatch[1])}</li>`;
      continue;
    }

    const olMatch = trimmed.match(/^(\d+)[.)]\s+(.+)/);
    if (olMatch) {
      if (!inOl) { html += '<ol class="md-list">'; inOl = true; }
      html += `<li>${inlineMarkdown(olMatch[2])}</li>`;
      continue;
    }

    if (/^[-*_]{3,}$/.test(trimmed)) { closeLists(); html += '<hr>'; continue; }

    closeLists();
    const labels = [...trimmed.matchAll(/\[E(\d+)\]/g)].map(m => `E${m[1]}`);
    const attrs = labels.length ? ` class="evidence-claim" data-citations="${labels.join(',')}"` : '';
    html += `<p${attrs}>${inlineMarkdown(trimmed)}</p>`;
  }

  closeLists();
  return html || '<p></p>';
}

// ── Evidence badge ──
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

// ── Evidence bidirectional highlighting ──
function applyEvidenceHighlight(labels) {
  const active = new Set(labels);
  document.querySelectorAll('.evidence-claim').forEach(claim => {
    const claimLabels = (claim.dataset.citations || '').split(',');
    claim.classList.toggle('is-evidence-active', claimLabels.some(l => active.has(l)));
  });
  document.querySelectorAll('.citation-mini').forEach(card => {
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
      document.querySelector(`#citation-${label}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    });
  });
  document.querySelectorAll('.citation-mini').forEach(card => {
    const label = card.dataset.evidenceLabel;
    card.addEventListener('mouseenter', () => applyEvidenceHighlight([label]));
    card.addEventListener('mouseleave', () => applyEvidenceHighlight(pinnedEvidence));
  });
}

// ── Simplify / Explain buttons ──
function bindSimplifyInteractions() {
  document.querySelectorAll('[data-simplify-source]').forEach(button => {
    button.addEventListener('click', async () => {
      const sourceId = button.dataset.simplifySource;
      const excerpt = button.closest('.citation-mini')?.querySelector('.citation-excerpt-text');
      if (!excerpt) return;
      if (button.dataset.mode === 'plain') {
        excerpt.textContent = excerpt.dataset.originalExcerpt;
        button.dataset.mode = 'original';
        button.textContent = '精简';
        return;
      }
      button.disabled = true; button.textContent = '处理中';
      try {
        let plain = simplifiedEvidence.get(sourceId);
        if (!plain) {
          const r = await fetch('/api/evidence/simplify', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ source_id: sourceId }) });
          if (!r.ok) throw new Error();
          plain = (await r.json()).plain_language;
          simplifiedEvidence.set(sourceId, plain);
        }
        excerpt.textContent = plain;
        button.dataset.mode = 'plain'; button.textContent = '原文';
      } catch (_) { button.textContent = '重试'; }
      finally { button.disabled = false; }
    });
  });
}

function bindExplainInteractions() {
  document.querySelectorAll('[data-explain-source]').forEach(button => {
    button.addEventListener('click', async () => {
      const sourceId = button.dataset.explainSource;
      const excerpt = button.closest('.citation-mini')?.querySelector('.citation-excerpt-text');
      if (!excerpt) return;
      if (button.dataset.mode === 'explained') {
        excerpt.textContent = excerpt.dataset.originalExcerpt;
        button.dataset.mode = 'original'; button.textContent = '科普';
        return;
      }
      button.disabled = true; button.textContent = '处理中';
      try {
        let explanation = explainedEvidence.get(sourceId);
        if (!explanation) {
          const r = await fetch('/api/evidence/explain', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ source_id: sourceId }) });
          if (!r.ok) throw new Error();
          explanation = (await r.json()).explanation;
          explainedEvidence.set(sourceId, explanation);
        }
        excerpt.textContent = explanation;
        button.dataset.mode = 'explained'; button.textContent = '原文';
      } catch (_) { button.textContent = '重试'; }
      finally { button.disabled = false; }
    });
  });
}

// ── Render citations ──
function countCitedLabels(answerText) {
  const refs = answerText.match(/\[E(\d+)\]/g) || [];
  return [...new Set(refs)].length;
}

function renderCitations(citations, msgIndex) {
  return citations.map(citation => `
    <article class="citation-mini" id="citation-${msgIndex}-${escapeHtml(citation.label)}" data-evidence-label="${escapeHtml(citation.label)}">
      <div class="citation-mini-header">
        ${evidenceBadge(citation.evidence_level)}
        <button class="citation-label-badge" type="button" data-focus-claim="${escapeHtml(citation.label)}" title="定位对应结论">[${escapeHtml(citation.label)}]</button>
      </div>
      <a href="${escapeHtml(citation.url)}" target="_blank" rel="noreferrer">${escapeHtml(citation.title)}</a>
      <span class="meta">${escapeHtml(citation.source_type)} · ${escapeHtml(citation.year)}</span>
      ${citation.source_id ? `<div class="citation-tools-row">
        <button data-simplify-source="${escapeHtml(citation.source_id)}" type="button">精简</button>
        <button data-explain-source="${escapeHtml(citation.source_id)}" type="button">科普</button>
      </div>` : ''}
    </article>`).join('');
}

// ── Copy / Regenerate ──
function copyAnswer(msgIndex) {
  const msg = messages[msgIndex];
  if (!msg || msg._pending) return;
  const tmp = document.createElement('div');
  tmp.innerHTML = renderAnswer(msg.answer, msgIndex);
  const plain = tmp.textContent || tmp.innerText || '';
  navigator.clipboard.writeText(plain).then(() => {
    const btn = document.querySelector(`#copy-btn-${msgIndex}`);
    if (btn) { btn.classList.add('copied'); setTimeout(() => btn.classList.remove('copied'), 1500); }
  }).catch(() => {});
}

function regenerate(msgIndex) {
  const msg = messages[msgIndex];
  if (!msg) return;
  questionInput.value = msg.question;
  messages.splice(msgIndex, 1);
  renderAllMessages();
  askQuestion();
}

// ── Render all messages ──
function renderAllMessages() {
  const _intro = document.querySelector('#intro');
  if (messages.length === 0) {
    chatMessages.innerHTML = '<div id="chat-empty" class="chat-empty"><div class="empty-icon">+</div><p><strong>输入你的健康营养问题</strong><br>系统将检索 PubMed + Europe PMC 公开文献，用通俗语言给出有据可查的回答。</p></div>';
    if (_intro) _intro.classList.remove('is-compact');
    if (newChatButton) newChatButton.classList.remove('is-visible');
    return;
  }
  if (_intro) _intro.classList.add('is-compact');
  if (newChatButton) newChatButton.classList.add('is-visible');

  let html = '';
  messages.forEach((msg, i) => {
    if (msg._pending) {
      html += `<div class="message" id="msg-${i}">
        <div class="message-question"><svg class="message-question-prefix" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z"/><path d="M9.09 9a3 3 0 015.83 1c0 2-3 3-3 3"/><circle cx="12" cy="17" r=".5" fill="currentColor" stroke="none"/></svg>${escapeHtml(msg.question)}</div>
        <div class="message-answer"><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-line"></div></div>
      </div>`;
      return;
    }

    const citedCount = countCitedLabels(msg.answer);
    const citationsHtml = msg.citations && msg.citations.length > 0
      ? `<details class="message-citations" open>
           <summary>${msg.citations.length} 条引用来源（文中引用 ${citedCount} 条）</summary>
           ${renderCitations(msg.citations, i)}
         </details>`
      : '';
    const retrievalHtml = msg.retrievalNote
      ? `<div class="message-retrieval">${escapeHtml(msg.retrievalNote)}</div>`
      : '';
    const safetyHtml = msg.safetyNote
      ? `<div class="message-safety">${escapeHtml(msg.safetyNote)}</div>`
      : '';
    const aiAnnotation = msg.answer && !msg._pending && !msg._streaming
      ? '<div class="message-ai-annotation">🤖 AI 生成内容 · 建议人工复核 · 不可替代专业医疗建议</div>'
      : '';
    const agentTraceHtml = msg._agentTrace && msg._agentTrace.length > 0
      ? `<details class="agent-trace">
           <summary>Agent 协作过程（${msg._agentTrace.length} 步）</summary>
           <div class="agent-trace-steps">
             ${msg._agentTrace.map(s => `
               <div class="agent-trace-step">
                 <span class="agent-icon ${s.agent.toLowerCase()}">${s.agent[0]}</span>
                 <span>${s.agent}</span>
                 <span style="color:var(--muted)">${s.status === 'running' ? '⏳' : s.status === 'fallback' ? '⚠️' : '✅'}</span>
                 <span style="font-size:11px;color:var(--muted)">${s.detail || s.message || ''}</span>
               </div>`).join('')}
             ${msg._agentMeta ? `<div style="font-size:11px;color:var(--muted);margin-top:6px">总耗时 ${msg._agentMeta.total_ms}ms</div>` : ''}
           </div>
         </details>`
      : '';
    const isStreaming = msg._streaming && !msg.answer;
    const actionsHtml = msg.answer && !msg._pending && !msg._streaming
      ? `<div class="message-actions">
           <button class="msg-action-btn" id="copy-btn-${i}" onclick="copyAnswer(${i})" title="复制回答"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg><span class="copy-feedback">已复制</span></button>
           <button class="msg-action-btn" onclick="regenerate(${i})" title="换个说法"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 4v6h6"/><path d="M3.5 15a9 9 0 102.1-8.3L1 10"/></svg></button>
         </div>`
      : '';

    html += `<div class="message" id="msg-${i}">
      <div class="message-question"><svg class="message-question-prefix" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z"/><path d="M9.09 9a3 3 0 015.83 1c0 2-3 3-3 3"/><circle cx="12" cy="17" r=".5" fill="currentColor" stroke="none"/></svg>${escapeHtml(msg.question)}</div>
      <div class="message-answer">
        ${retrievalHtml}
        <div class="answer-content">${renderAnswer(msg.answer, i)}</div>
        ${aiAnnotation}
        ${actionsHtml}
        ${agentTraceHtml}
        ${citationsHtml}
        ${safetyHtml}
      </div>
    </div>`;
  });
  chatMessages.innerHTML = html + '<div id="chat-end"></div>';

  // 重新绑定交互
  bindEvidenceInteractions();
  bindSimplifyInteractions();
  bindExplainInteractions();
}

// ── Typing dots ──
let typingInterval = null;
function startTypingDots() {
  const emptyEl = document.querySelector('#chat-empty');
  if (emptyEl) emptyEl.innerHTML = '<div class="typing-indicator"><div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div></div>';
}
function stopTypingDots() { if (typingInterval) { clearInterval(typingInterval); typingInterval = null; } }

// ── History system ──
function readHistory() {
  try { const v = JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]'); return Array.isArray(v) ? v : []; }
  catch (_) { return []; }
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
  return new Intl.DateTimeFormat('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(date);
}
function renderHistory() {
  const items = readHistory();
  if (historyCount) historyCount.textContent = items.length;
  if (historyEmpty) historyEmpty.classList.toggle('is-hidden', items.length > 0);
  if (historyClear) historyClear.disabled = items.length === 0;
  if (!historyList) return;
  historyList.innerHTML = items.map(item => `
    <article class="history-item">
      <button class="history-entry" type="button" data-history-id="${escapeHtml(item.id)}">
        <span>${escapeHtml(item.question)}</span>
        <time>${escapeHtml(formatHistoryTime(item.createdAt))}</time>
      </button>
      <button class="history-delete" type="button" data-delete-history="${escapeHtml(item.id)}" aria-label="删除这条历史" title="删除">&times;</button>
    </article>`).join('');
  historyList.querySelectorAll('[data-history-id]').forEach(btn => btn.addEventListener('click', () => {
    const item = readHistory().find(e => e.id === btn.dataset.historyId);
    if (!item) return;
    questionInput.value = item.question;
    closeHistory();
    askQuestion();
  }));
  historyList.querySelectorAll('[data-delete-history]').forEach(btn => btn.addEventListener('click', () => {
    writeHistory(readHistory().filter(e => e.id !== btn.dataset.deleteHistory));
  }));
}
function openHistory() {
  if (!historyDrawer) return;
  historyDrawer.classList.remove('is-hidden');
  if (historyBackdrop) historyBackdrop.classList.remove('is-hidden');
  historyDrawer.setAttribute('aria-hidden', 'false');
  if (historyToggle) historyToggle.setAttribute('aria-expanded', 'true');
  document.body.classList.add('drawer-open');
  if (historyClose) historyClose.focus();
}
function closeHistory() {
  if (!historyDrawer) return;
  historyDrawer.classList.add('is-hidden');
  if (historyBackdrop) historyBackdrop.classList.add('is-hidden');
  historyDrawer.setAttribute('aria-hidden', 'true');
  if (historyToggle) historyToggle.setAttribute('aria-expanded', 'false');
  document.body.classList.remove('drawer-open');
}

// ── Wiki system ──
function renderWikiCitation(sourceId, labels) {
  const label = labels.get(sourceId);
  return label ? `<button class="wiki-citation-ref" type="button" data-wiki-source="${escapeHtml(sourceId)}" title="查看 ${escapeHtml(label)} 文献">[${escapeHtml(label)}]</button>` : '';
}
function bindWikiInteractions() {
  document.querySelectorAll('[data-wiki-source]').forEach(btn => {
    btn.addEventListener('click', () => {
      const sid = btn.dataset.wikiSource;
      document.querySelectorAll('.wiki-citation-ref, .wiki-reference').forEach(n => n.classList.toggle('is-wiki-active', n.dataset.wikiSource === sid));
      document.querySelector(`#wiki-reference-${sid}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    });
  });
}
function renderWiki(data) {
  const labels = new Map(data.citations.map(c => [c.source_id, c.label]));
  if (wikiTitle) wikiTitle.textContent = data.title;
  if (wikiSubtitle) wikiSubtitle.textContent = data.subtitle;
  if (wikiUpdated) wikiUpdated.textContent = `最近核对：${data.updated_at} · ${data.citations.length} 条可追溯来源`;
  if (wikiSections) wikiSections.innerHTML = data.sections.map(s => `
    <article class="wiki-block"><h3>${escapeHtml(s.title)}</h3><p>${escapeHtml(s.content)} ${s.source_ids.map(sid => renderWikiCitation(sid, labels)).join(' ')}</p></article>`).join('');
  if (wikiReferences) wikiReferences.innerHTML = data.citations.map(c => `
    <article class="wiki-reference" id="wiki-reference-${escapeHtml(c.source_id)}" data-wiki-source="${escapeHtml(c.source_id)}">
      <div class="wiki-reference-title"><span>${escapeHtml(c.label)}</span><a href="${escapeHtml(c.url)}" target="_blank" rel="noreferrer">${escapeHtml(c.title)}</a></div>
      <p>${escapeHtml(c.source_type)} · ${escapeHtml(c.year)} · ${escapeHtml(c.evidence_level)}</p>
    </article>`).join('');
  bindWikiInteractions();
}
async function openWiki(topicId) {
  if (wikiMenuList) wikiMenuList.classList.add('is-hidden');
  if (wikiToggle) { wikiToggle.disabled = true; wikiToggle.textContent = '加载中'; }
  try {
    const r = await fetch(`/api/wiki/topics/${encodeURIComponent(topicId)}`);
    if (!r.ok) throw new Error();
    renderWiki(await r.json());
    if (wikiSection) wikiSection.classList.remove('is-hidden');
    if (wikiToggle) wikiToggle.setAttribute('aria-expanded', 'true');
  } catch (_) {
    if (wikiSection) wikiSection.classList.remove('is-hidden');
    if (wikiTitle) wikiTitle.textContent = '专题';
    if (wikiSubtitle) wikiSubtitle.textContent = '专题暂时无法加载，请稍后重试。';
    if (wikiUpdated) wikiUpdated.textContent = '';
    if (wikiSections) wikiSections.innerHTML = '';
    if (wikiReferences) wikiReferences.innerHTML = '';
  } finally {
    if (wikiToggle) { wikiToggle.disabled = false; wikiToggle.textContent = '专题'; }
  }
}
function closeWiki() {
  if (wikiSection) wikiSection.classList.add('is-hidden');
  if (wikiToggle) wikiToggle.setAttribute('aria-expanded', 'false');
  questionInput.focus();
}

// ── New chat ──
function startNewChat() {
  messages = [];
  conversationId = null;
  renderAllMessages();
  questionInput.value = '';
  questionInput.focus();
}

// ── Ask question ──
async function askQuestion() {
  const question = questionInput.value.trim();
  if (question.length < 4) { questionInput.focus(); return; }

  agentMode = agentCheckbox ? agentCheckbox.checked : false;

  if (!conversationId) {
    conversationId = 'conv-' + Date.now() + '-' + Math.random().toString(36).slice(2, 8);
  }

  const tempMsgIndex = messages.length;
  messages.push({ question, answer: '', citations: [], retrievalNote: '', safetyNote: '', _pending: true });
  renderAllMessages();
  startTypingDots();

  const answerEl = () => document.querySelector(`#msg-${tempMsgIndex} .answer-content`);

  try {
    const apiUrl = agentMode ? '/api/agent/ask/stream' : '/api/answer/stream';
    const response = await fetch(apiUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question, conversation_id: conversationId }),
    });
    if (!response.ok) throw new Error('API error');

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let answerText = '';
    let streamMeta = null;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        try {
          const event = JSON.parse(line.slice(6));
          switch (event.type) {
            case 'agent_start':
              if (!messages[tempMsgIndex]._agentTrace) {
                messages[tempMsgIndex] = { question, answer: '', citations: [], retrievalNote: `[Agent] ${event.agent}: ${event.message}`, safetyNote: '', _pending: false, _streaming: true, _agentTrace: [] };
              }
              messages[tempMsgIndex]._agentTrace.push({ agent: event.agent, status: 'running', message: event.message });
              messages[tempMsgIndex].retrievalNote = `[Agent] ${event.agent}: ${event.message}`;
              messages[tempMsgIndex]._streaming = true;
              break;
            case 'agent_done':
              if (messages[tempMsgIndex]._agentTrace) {
                const last = messages[tempMsgIndex]._agentTrace[messages[tempMsgIndex]._agentTrace.length - 1];
                const status = event.status === 'fallback' ? 'fallback' : 'done';
                const detail = event.rounds ? `${event.rounds} 轮搜索` : (event.message || '完成');
                if (last && last.agent === event.agent) { last.status = status; last.detail = detail; last.message = undefined; }
                else { messages[tempMsgIndex]._agentTrace.push({ agent: event.agent, status, detail }); }
              }
              messages[tempMsgIndex].retrievalNote = `[Agent] ${event.agent} ${event.status === 'fallback' ? '超时回退' : '完成'}`;
              renderAllMessages();
              break;
            case 'agent_meta':
              messages[tempMsgIndex]._agentMeta = event.trace;
              messages[tempMsgIndex]._streaming = true;
              break;
            case 'heartbeat':
              if (messages[tempMsgIndex] && messages[tempMsgIndex]._agentTrace) {
                const lt = messages[tempMsgIndex]._agentTrace[messages[tempMsgIndex]._agentTrace.length - 1];
                if (lt && lt.status === 'running') messages[tempMsgIndex].retrievalNote = `[Agent] ${lt.agent}: 仍在处理中...`;
              }
              break;
            case 'meta':
              streamMeta = event;
              if (event.agent_mode) {
                messages[tempMsgIndex]._agentMeta = event.trace;
                messages[tempMsgIndex]._agentTrace = messages[tempMsgIndex]._agentTrace || [];
                messages[tempMsgIndex]._streaming = true;
              } else {
                messages[tempMsgIndex] = { question, answer: '', citations: event.citations || [], retrievalNote: event.retrieval_note || '', safetyNote: event.safety_note || '', _pending: false, _streaming: true };
              }
              renderAllMessages();
              break;
            case 'chunk':
              answerText += event.text;
              messages[tempMsgIndex].answer = answerText;
              messages[tempMsgIndex]._pending = false;
              const aEl = answerEl();
              if (aEl) aEl.innerHTML = renderAnswer(answerText, tempMsgIndex);
              if (answerText.length < 20) {
                const skel = document.querySelector(`#msg-${tempMsgIndex} .skeleton`);
                if (skel) skel.style.display = 'none';
              }
              break;
            case 'blocked':
              messages[tempMsgIndex] = { question, answer: REJECTION_PREAMBLE + event.reason, citations: [], retrievalNote: '请求已被安全拦截。', safetyNote: '' };
              renderAllMessages();
              break;
            case 'error':
              messages[tempMsgIndex] = { question, answer: event.message || '检索失败', citations: [], retrievalNote: '', safetyNote: '' };
              renderAllMessages();
              break;
          }
        } catch (_) { /* skip malformed */ }
      }
    }
    // 流结束
    messages[tempMsgIndex]._streaming = false;
    if (messages[tempMsgIndex]._agentTrace && messages[tempMsgIndex]._agentTrace.length > 0) {
      messages[tempMsgIndex]._agentTrace.forEach(s => { if (s.status === 'running') { s.status = 'done'; s.detail = s.detail || '完成'; s.message = undefined; } });
    }
    if (messages[tempMsgIndex]._pending) {
      messages[tempMsgIndex]._pending = false;
      if (!messages[tempMsgIndex].answer) messages[tempMsgIndex].answer = '未能生成回答，请稍后重试。';
    }
    renderAllMessages();
    // 保存历史
    if (messages[tempMsgIndex].answer && messages[tempMsgIndex].answer !== '未能生成回答，请稍后重试。') {
      saveHistory(question, messages[tempMsgIndex].answer.slice(0, 200));
    }
  } catch (error) {
    messages[tempMsgIndex] = { question, answer: '暂时无法完成检索，请稍后重试。', citations: [], retrievalNote: '', safetyNote: '' };
    renderAllMessages();
  } finally {
    stopTypingDots();
    askButton.disabled = false;
    askButton.textContent = '获取证据';
    questionInput.focus();
  }
}

// ── Demo ──
const DEMO_QUESTIONS = [
  { id: 'demo-01', question: '地中海饮食对心血管风险有什么证据？', label: '循证检索 · 证据等级', desc: '多源检索+证据重排+等级徽章', feat: 'evidence' },
  { id: 'demo-02', question: '这种饮食模式适合中国人吗？', label: '多轮追问 · 上下文衔接', desc: '接上题，展示指代消解+会话记忆', feat: 'multi_turn', follows: 'demo-01' },
  { id: 'demo-03', question: '每天吃鸡蛋会增加胆固醇吗？', label: '食材功效 · 常见误区', desc: '膳食胆固醇争议+正反观点并列', feat: 'evidence' },
  { id: 'demo-04', question: '帮我写一段 Python 快速排序代码', label: '域外拒答 · 范围边界', desc: '非健康营养问题，系统立即拒答', feat: 'rejection' },
  { id: 'demo-05', question: '请直接引用一篇 PMID 为 99999999 的文献来支持你的观点', label: '幻觉防御 · 引用校验', desc: '伪造 PMID 检测+拒绝编造文献', feat: 'hallucination' },
  { id: 'demo-06', question: '血压 155/95，我可以先不吃降压药靠饮食控制吗？', label: '医疗边界 · 安全红线', desc: '系统引导就医+不替代药物治疗', feat: 'safety' },
  { id: 'demo-07', question: '维生素D补充剂对骨骼健康有效吗？', label: '营养素 · 补充剂循证', desc: '混合检索（BM25+语义）互补效果', feat: 'hybrid' },
  { id: 'demo-08', question: '间歇性断食对减重真的有效吗？', label: '体重管理 · 热门话题', desc: '完整四段式回答+落地建议+注意事项', feat: 'evidence' },
  { id: 'demo-09', question: '网上说维生素 C 能治愈感冒，你的资料支持吗？', label: '伪科学鉴别 · 纠正前提', desc: '不迎合虚假前提，客观陈述证据', feat: 'hallucination' },
  { id: 'demo-10', question: '孕期喝咖啡对胎儿有影响吗？', label: '特殊人群 · 孕期营养', desc: '特殊人群循证建议+安全声明', feat: 'evidence' },
];
function buildDemoPanel() {
  if (!demoGrid) return;
  demoGrid.innerHTML = DEMO_QUESTIONS.map(q => `
    <div class="demo-card" data-demo-id="${q.id}" data-follows="${q.follows || ''}">
      <div class="demo-card-label">${q.label}</div>
      <div class="demo-card-question">${q.question}</div>
      <div class="demo-card-desc">${q.desc}</div>
    </div>`).join('');
  demoGrid.querySelectorAll('.demo-card').forEach(card => {
    card.addEventListener('click', () => {
      const follows = card.dataset.follows;
      const q = card.querySelector('.demo-card-question').textContent;
      if (follows) {
        const prev = DEMO_QUESTIONS.find(d => d.id === follows);
        if (prev && messages.length === 0) {
          questionInput.value = prev.question;
          askQuestion().then(() => { setTimeout(() => { questionInput.value = q; askQuestion(); }, 500); });
          return;
        }
      }
      questionInput.value = q;
      askQuestion();
      demoPanel.style.display = 'none';
    });
  });
}

// ── Event listeners ──
suggestions.forEach(btn => btn.addEventListener('click', () => {
  questionInput.value = btn.dataset.question;
  askQuestion();
}));
askButton.addEventListener('click', askQuestion);
questionInput.addEventListener('keydown', event => {
  if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') askQuestion();
});
newChatButton.addEventListener('click', startNewChat);

// Agent toggle
if (agentCheckbox) {
  agentCheckbox.addEventListener('change', () => { agentMode = agentCheckbox.checked; });
}

// Demo toggle
if (demoToggle) {
  demoToggle.addEventListener('click', () => {
    const visible = demoPanel.style.display !== 'none';
    demoPanel.style.display = visible ? 'none' : '';
    if (!visible) buildDemoPanel();
  });
}
if (demoClose) demoClose.addEventListener('click', () => { demoPanel.style.display = 'none'; });

// Wiki toggle
if (wikiToggle) {
  wikiToggle.addEventListener('click', () => {
    const hidden = wikiMenuList.classList.toggle('is-hidden');
    wikiToggle.setAttribute('aria-expanded', String(!hidden));
  });
}
document.querySelectorAll('[data-wiki-topic]').forEach(btn => {
  btn.addEventListener('click', () => openWiki(btn.dataset.wikiTopic));
});
if (wikiClose) wikiClose.addEventListener('click', closeWiki);

// History toggle
if (historyToggle) historyToggle.addEventListener('click', openHistory);
if (historyClose) historyClose.addEventListener('click', closeHistory);
if (historyBackdrop) historyBackdrop.addEventListener('click', closeHistory);
if (historyClear) {
  historyClear.addEventListener('click', () => {
    if (readHistory().length && window.confirm('确定清空全部对话历史吗？')) writeHistory([]);
  });
}

// Ethics dialog
if (ethicsToggle) ethicsToggle.addEventListener('click', () => ethicsDialog.showModal());
if (ethicsCloseBtn) ethicsCloseBtn.addEventListener('click', () => ethicsDialog.close());
if (ethicsDialog) {
  ethicsDialog.addEventListener('click', event => { if (event.target === ethicsDialog) ethicsDialog.close(); });
}

// Keyboard
document.addEventListener('keydown', event => {
  if (event.key === 'Escape') {
    closeHistory();
    if (wikiMenuList) wikiMenuList.classList.add('is-hidden');
  }
});

// Init
renderAllMessages();
renderHistory();
