const questionInput = document.querySelector('#question');
const askButton = document.querySelector('#ask-button');
const chatMessages = document.querySelector('#chat-messages');
const chatEmpty = document.querySelector('#chat-empty');
const intro = document.querySelector('#intro');
const newChatButton = document.querySelector('#new-chat-button');
const suggestions = document.querySelectorAll('[data-question]');

let conversationId = null;
let messages = [];

// ── 关键词高亮词表（按长度降序，避免短词破坏长词） ──
const HIGHLIGHT_TERMS = [
  '随机对照试验', '系统综述', 'Meta分析', '观察性研究', '临床指南',
  '地中海饮食', 'DASH饮食', '低碳水', '生酮饮食',
  '膳食纤维', '碳水化合物', '血糖指数', '饱和脂肪', '反式脂肪', '不饱和脂肪',
  '甘油三酯', '心血管', '冠心病', '骨质疏松', '氧化应激',
  '高血压', '高血脂', '高血糖', '糖尿病', '肥胖',
  '蛋白质', '维生素', '矿物质', '胆固醇', '胰岛素',
  '全谷物', '橄榄油', '深海鱼', '加工食品', '精制碳水',
  '抗氧化', '炎症', '痛风', '中风', '肠道菌群',
  '豆类', '坚果', '红肉', '钙', '铁', '锌', '镁', '钾', '钠', '叶酸',
];

function escapeHtml(value) {
  return value.replace(/[&<>'"]/g, char => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', "'":'&#39;', '"':'&quot;' }[char]));
}

function renderAnswer(text, msgIndex) {
  return text.split('\n').map(line => {
    if (!line.trim()) return '';
    let safe = escapeHtml(line);
    // 关键词高亮（在引用链接之前，防止高亮进入 <a> 标签内）
    HIGHLIGHT_TERMS.forEach(term => {
      safe = safe.replace(new RegExp(term, 'g'), `<mark class="kw">${term}</mark>`);
    });
    // 引用链接
    const withCitations = safe.replace(/\[E(\d+)\]/g, (_, number) => `<a class="citation-ref" href="#citation-${msgIndex}-E${number}">[E${number}]</a>`);
    return `<p>${withCitations}</p>`;
  }).join('');
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

function renderCitations(citations, msgIndex) {
  return citations.map(citation => `
    <article class="citation-mini" id="citation-${msgIndex}-${escapeHtml(citation.label)}">
      <div class="citation-mini-header">
        ${evidenceBadge(citation.evidence_level)}
        <span class="citation-label-badge">[${escapeHtml(citation.label)}]</span>
      </div>
      <a href="${escapeHtml(citation.url)}" target="_blank" rel="noreferrer">${escapeHtml(citation.title)}</a>
      <span class="meta">${escapeHtml(citation.source_type)} · ${escapeHtml(citation.year)}</span>
    </article>`).join('');
}

// ── 统计每条消息中实际被引用的证据编号 ──
function countCitedLabels(answerText) {
  const refs = answerText.match(/\[E(\d+)\]/g) || [];
  return [...new Set(refs)].length;
}

function renderAllMessages() {
  if (messages.length === 0) {
    chatEmpty.style.display = '';
    newChatButton.classList.remove('is-visible');
    intro.classList.remove('is-compact');
    return;
  }
  chatEmpty.style.display = 'none';
  newChatButton.classList.add('is-visible');
  intro.classList.add('is-compact');

  let html = '';
  messages.forEach((msg, i) => {
    // 骨架屏：等待回答中
    if (msg._pending) {
      html += `
        <div class="message" id="msg-${i}">
          <div class="message-question"><svg class="message-question-prefix" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z"/><path d="M9.09 9a3 3 0 015.83 1c0 2-3 3-3 3"/><circle cx="12" cy="17" r=".5" fill="currentColor" stroke="none"/></svg>${escapeHtml(msg.question)}</div>
          <div class="message-answer">
            <div class="skeleton skeleton-line"></div>
            <div class="skeleton skeleton-line"></div>
            <div class="skeleton skeleton-line"></div>
          </div>
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

    html += `
      <div class="message" id="msg-${i}">
        <div class="message-question"><svg class="message-question-prefix" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z"/><path d="M9.09 9a3 3 0 015.83 1c0 2-3 3-3 3"/><circle cx="12" cy="17" r=".5" fill="currentColor" stroke="none"/></svg>${escapeHtml(msg.question)}</div>
        <div class="message-answer">
          ${retrievalHtml}
          <div class="answer-content">${renderAnswer(msg.answer, i)}</div>
          ${citationsHtml}
          ${safetyHtml}
        </div>
      </div>`;
  });
  chatMessages.innerHTML = html + '<div id="chat-end"></div>';
  requestAnimationFrame(() => {
    document.querySelector('#chat-end')?.scrollIntoView({ behavior: 'smooth' });
  });
}

const LOADING_STAGES = [
  { text: '正在分析问题...', delay: 0 },
  { text: '正在检索 PubMed...', delay: 800 },
  { text: '正在检索本地证据...', delay: 1800 },
  { text: '正在生成回答...', delay: 2500 },
];

async function askQuestion() {
  const question = questionInput.value.trim();
  if (question.length < 4) { questionInput.focus(); return; }
  askButton.disabled = true;
  questionInput.value = '';

  if (!conversationId) {
    conversationId = 'conv-' + Date.now() + '-' + Math.random().toString(36).slice(2, 8);
  }

  // 立即显示骨架屏
  const tempMsgIndex = messages.length;
  messages.push({ question, answer: '', citations: [], retrievalNote: '', safetyNote: '', _pending: true });
  renderAllMessages();

  let stageIndex = 0;
  askButton.textContent = LOADING_STAGES[0].text;
  const stageTimer = setInterval(() => {
    stageIndex++;
    if (stageIndex < LOADING_STAGES.length) {
      askButton.textContent = LOADING_STAGES[stageIndex].text;
    }
  }, 900);

  try {
    const response = await fetch('/api/answer', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question, include_pubmed: true, conversation_id: conversationId })
    });
    clearInterval(stageTimer);
    if (!response.ok) throw new Error('回答接口暂时不可用');
    const data = await response.json();

    messages[tempMsgIndex] = {
      question,
      answer: data.answer_markdown,
      citations: data.citations,
      retrievalNote: data.retrieval_note,
      safetyNote: data.safety_note,
    };
    renderAllMessages();
  } catch (error) {
    messages[tempMsgIndex] = {
      question,
      answer: '暂时无法完成检索，请稍后重试。',
      citations: [],
      retrievalNote: '',
      safetyNote: '',
    };
    renderAllMessages();
  } finally {
    clearInterval(stageTimer);
    askButton.disabled = false;
    askButton.textContent = '获取证据';
    questionInput.focus();
  }
}

function startNewChat() {
  conversationId = null;
  messages = [];
  renderAllMessages();
  chatEmpty.style.display = '';
  newChatButton.classList.remove('is-visible');
  intro.classList.remove('is-compact');
  questionInput.value = '';
  questionInput.focus();
}

// ── Event listeners ──
suggestions.forEach(button => button.addEventListener('click', () => {
  questionInput.value = button.dataset.question;
  askQuestion();
}));
askButton.addEventListener('click', askQuestion);
questionInput.addEventListener('keydown', event => {
  if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') askQuestion();
});
newChatButton.addEventListener('click', startNewChat);
