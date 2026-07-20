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

let lastQuestion = '';

function escapeHtml(value) {
  return value.replace(/[&<>'"]/g, char => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', "'":'&#39;', '"':'&quot;' }[char]));
}

function renderMarkdown(text) {
  return text.split('\n').map(line => {
    if (line.startsWith('### ')) return `<h3>${escapeHtml(line.slice(4))}</h3>`;
    if (!line.trim()) return '';
    const withCitations = escapeHtml(line).replace(/\[E(\d+)\]/g, (_, number) => `<a class="citation-ref" href="#citation-E${number}">[E${number}]</a>`);
    return `<p>${withCitations}</p>`;
  }).join('');
}

function renderCitations(citations) {
  sourceCount.textContent = citations.length;
  citationList.innerHTML = citations.map(citation => `
    <article class="citation-card" id="citation-${escapeHtml(citation.label)}">
      <a href="${escapeHtml(citation.url)}" target="_blank" rel="noreferrer"><span class="citation-label">[${escapeHtml(citation.label)}]</span>${escapeHtml(citation.title)}</a>
      <div class="citation-meta">${escapeHtml(citation.source_type)} · ${escapeHtml(citation.year)} · ${escapeHtml(citation.evidence_level)}</div>
      <p class="citation-excerpt">${escapeHtml(citation.excerpt)}</p>
    </article>`).join('');
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
    lastQuestion = question;
    answerContent.innerHTML = renderMarkdown(data.answer_markdown);
    safetyNote.textContent = data.safety_note;
    renderCitations(data.citations);
    emptyState.classList.add('is-hidden');
    answerSection.classList.remove('is-hidden');
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

pubmedToggle.addEventListener('click', async () => {
  if (!lastQuestion) return;
  pubmedToggle.disabled = true;
  pubmedToggle.textContent = '正在查询...';
  try {
    const response = await fetch('/api/pubmed/search', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({query:lastQuestion, limit:4}) });
    if (!response.ok) throw new Error();
    const { articles } = await response.json();
    pubmedResults.innerHTML = articles.map(article => `<article class="pubmed-item"><a href="${escapeHtml(article.url)}" target="_blank" rel="noreferrer">${escapeHtml(article.title)}</a><p>${escapeHtml(article.journal)} · ${escapeHtml(article.year)} · PMID ${escapeHtml(article.pmid)}</p></article>`).join('') || '<p class="citation-excerpt">未找到匹配的 PubMed 条目。</p>';
  } catch (_) {
    pubmedResults.innerHTML = '<p class="citation-excerpt">PubMed 当前无法访问，请稍后重试。</p>';
  } finally {
    pubmedToggle.disabled = false;
    pubmedToggle.textContent = '实时检索 PubMed';
  }
});
