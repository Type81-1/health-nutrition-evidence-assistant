const questionInput = document.querySelector('#question');
const askButton = document.querySelector('#ask-button');
const chatMessages = document.querySelector('#chat-messages');
const chatEmpty = document.querySelector('#chat-empty');
const intro = document.querySelector('#intro');
const newChatButton = document.querySelector('#new-chat-button');
const suggestions = document.querySelectorAll('[data-question]');

// v20260811b — new-chat fix
console.log('[食证] app.js v20260811b loaded');
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
  const _intro = document.querySelector('#intro');
  if (messages.length === 0) {
    // 清空所有消息，只留空态
    chatMessages.innerHTML = '<div id="chat-empty" class="chat-empty"><div class="empty-icon"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"/><path d="M16.5 16.5L21 21"/><path d="M8 11h6M11 8v6"/></svg></div><p><strong>输入你的健康营养问题</strong><br>系统将检索 PubMed + Europe PMC 公开文献，用通俗语言给出有据可查的回答。</p></div>';
    if (_intro) _intro.classList.remove('is-compact');
    if (newChatButton) newChatButton.classList.remove('is-visible');
    return;
  }
  if (_intro) _intro.classList.add('is-compact');
  if (newChatButton) newChatButton.classList.add('is-visible');

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
  questionInput.value = '';
  questionInput.focus();
}

// ── Demo panel ──────────────────────────────────────
const demoToggle = document.getElementById('demo-toggle');
const demoPanel = document.getElementById('demo-panel');
const demoGrid = document.getElementById('demo-grid');
const demoClose = document.getElementById('demo-close');

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
  const featClass = { rejection: 'rejection', safety: 'safety', hallucination: 'hallucination' };
  demoGrid.innerHTML = DEMO_QUESTIONS.map(q => `
    <div class="demo-card" data-demo-id="${q.id}" data-follows="${q.follows || ''}">
      <div class="demo-card-label ${featClass[q.feat] || ''}">${q.label}</div>
      <div class="demo-card-question">${q.question}</div>
      <div class="demo-card-desc">${q.desc}</div>
    </div>
  `).join('');

  demoGrid.querySelectorAll('.demo-card').forEach(card => {
    card.addEventListener('click', () => {
      const follows = card.dataset.follows;
      const q = card.querySelector('.demo-card-question').textContent;

      // 多轮追问：确保前一个问题在会话中
      if (follows) {
        const prev = DEMO_QUESTIONS.find(d => d.id === follows);
        if (prev && messages.length === 0) {
          questionInput.value = prev.question;
          askQuestion().then(() => {
            setTimeout(() => {
              questionInput.value = q;
              askQuestion();
            }, 500);
          });
          return;
        }
      }

      questionInput.value = q;
      askQuestion();
      demoPanel.style.display = 'none';
    });
  });
}

if (demoToggle) {
  demoToggle.addEventListener('click', () => {
    const isVisible = demoPanel.style.display !== 'none';
    demoPanel.style.display = isVisible ? 'none' : '';
    if (!isVisible) buildDemoPanel();
  });
}
if (demoClose) {
  demoClose.addEventListener('click', () => { demoPanel.style.display = 'none'; });
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
