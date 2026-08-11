const questionInput = document.querySelector('#question');
const askButton = document.querySelector('#ask-button');
const chatMessages = document.querySelector('#chat-messages');
const chatEmpty = document.querySelector('#chat-empty');
const intro = document.querySelector('#intro');
const newChatButton = document.querySelector('#new-chat-button');
const suggestions = document.querySelectorAll('[data-question]');

const REJECTION_PREAMBLE = '基于安全与伦理准则，';
let conversationId = null;
let messages = [];

// ── 关键词高亮词表（按长度降序）──
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
    HIGHLIGHT_TERMS.forEach(term => {
      safe = safe.replace(new RegExp(term, 'g'), `<mark class="kw">${term}</mark>`);
    });
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

function countCitedLabels(answerText) {
  const refs = answerText.match(/\[E(\d+)\]/g) || [];
  return [...new Set(refs)].length;
}

// ── 复制回答 ──
function copyAnswer(msgIndex) {
  const msg = messages[msgIndex];
  if (!msg || msg._pending) return;
  // 提取纯文本（去 HTML 标签）
  const tmp = document.createElement('div');
  tmp.innerHTML = renderAnswer(msg.answer, msgIndex);
  const plain = tmp.textContent || tmp.innerText || '';
  navigator.clipboard.writeText(plain).then(() => {
    const btn = document.querySelector(`#copy-btn-${msgIndex}`);
    if (btn) {
      btn.classList.add('copied');
      setTimeout(() => btn.classList.remove('copied'), 1500);
    }
  }).catch(() => {});
}

// ── 重新生成 ──
function regenerate(msgIndex) {
  const msg = messages[msgIndex];
  if (!msg || msg._pending) return;
  questionInput.value = msg.question;
  askQuestion();
  // 滚动输入框到视野
  questionInput.scrollIntoView({ behavior: 'smooth' });
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
    // 操作按钮（仅在回答非空且未在流式传输中时显示）
    const isStreaming = msg._streaming && !msg.answer;
    const actionsHtml = msg.answer && !msg._pending && !msg._streaming
      ? `<div class="message-actions">
           <button class="msg-action-btn" id="copy-btn-${i}" onclick="copyAnswer(${i})" title="复制回答">
             <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>
             <span class="copy-feedback">已复制</span>
           </button>
           <button class="msg-action-btn" onclick="regenerate(${i})" title="换个说法">
             <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 4v6h6"/><path d="M3.5 15a9 9 0 102.1-8.3L1 10"/></svg>
           </button>
         </div>`
      : '';

    html += `
      <div class="message" id="msg-${i}">
        <div class="message-question"><svg class="message-question-prefix" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z"/><path d="M9.09 9a3 3 0 015.83 1c0 2-3 3-3 3"/><circle cx="12" cy="17" r=".5" fill="currentColor" stroke="none"/></svg>${escapeHtml(msg.question)}</div>
        <div class="message-answer">
          ${retrievalHtml}
          <div class="answer-content">${renderAnswer(msg.answer, i)}</div>
          ${actionsHtml}
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

// ── 打字动画圆点 ──
function startTypingDots() {
  askButton.innerHTML = '正在检索<span class="typing-dots"><i>.</i><i>.</i><i>.</i></span>';
}
function stopTypingDots() {
  askButton.textContent = '获取证据';
}

async function askQuestion() {
  const question = questionInput.value.trim();
  if (question.length < 4) { questionInput.focus(); return; }
  askButton.disabled = true;
  questionInput.value = '';

  if (!conversationId) {
    conversationId = 'conv-' + Date.now() + '-' + Math.random().toString(36).slice(2, 8);
  }

  const tempMsgIndex = messages.length;
  messages.push({ question, answer: '', citations: [], retrievalNote: '', safetyNote: '', _pending: true });
  renderAllMessages();
  startTypingDots();

  // 缓存 DOM 引用，避免每次 chunk 都全量重绘
  const answerEl = () => document.querySelector(`#msg-${tempMsgIndex} .answer-content`);
  const retrievalEl = () => document.querySelector(`#msg-${tempMsgIndex} .message-retrieval`);
  const questionEl = () => document.querySelector(`#msg-${tempMsgIndex} .message-question`);
  const citationsContainer = () => document.querySelector(`#msg-${tempMsgIndex} .message-citations-wrap`);
  const safetyEl = () => document.querySelector(`#msg-${tempMsgIndex} .message-safety-wrap`);
  const actionsEl = () => document.querySelector(`#msg-${tempMsgIndex} .message-actions`);

  try {
    const response = await fetch('/api/answer/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question, include_pubmed: true, conversation_id: conversationId })
    });
    if (!response.ok) throw new Error('回答接口暂时不可用');

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
            case 'meta':
              streamMeta = event;
              messages[tempMsgIndex] = {
                question,
                answer: '',
                citations: event.citations || [],
                retrievalNote: event.retrieval_note || '',
                safetyNote: event.safety_note || '',
                _pending: false,
                _streaming: true,
              };
              // 初始渲染：显示检索来源 + 引用骨架
              renderAllMessages();
              break;
            case 'chunk':
              answerText += event.text;
              messages[tempMsgIndex].answer = answerText;
              messages[tempMsgIndex]._pending = false;
              // 直接更新 DOM，不重绘整个页面
              const aEl = answerEl();
              if (aEl) {
                aEl.innerHTML = renderAnswer(answerText, tempMsgIndex);
              }
              // 首次收到文本时隐藏骨架
              if (answerText.length < 20) {
                const skel = document.querySelector(`#msg-${tempMsgIndex} .skeleton`);
                if (skel) skel.style.display = 'none';
              }
              break;
            case 'blocked':
              messages[tempMsgIndex] = {
                question,
                answer: REJECTION_PREAMBLE + event.reason,
                citations: [],
                retrievalNote: '请求已被安全拦截。',
                safetyNote: '',
              };
              renderAllMessages();
              break;
            case 'error':
              messages[tempMsgIndex] = {
                question,
                answer: event.message || '检索失败',
                citations: [],
                retrievalNote: '',
                safetyNote: '',
              };
              renderAllMessages();
              break;
          }
        } catch (_) { /* skip malformed events */ }
      }
    }
    // 流结束，最终渲染引用 + 安全声明
    messages[tempMsgIndex]._streaming = false;
    if (messages[tempMsgIndex]._pending) {
      messages[tempMsgIndex]._pending = false;
      if (!messages[tempMsgIndex].answer) {
        messages[tempMsgIndex].answer = '未能生成回答，请稍后重试。';
      }
    }
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
    stopTypingDots();
    askButton.disabled = false;
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
