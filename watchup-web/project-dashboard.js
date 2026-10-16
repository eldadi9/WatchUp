const spreadsheetId = '1YyMkAxCWOsnR-FmpDa80OcqSVuO5ntQIXg75ztfjgMo';
const sheetBase = `https://docs.google.com/spreadsheets/d/${spreadsheetId}/gviz/tq`;
let tasks = [];

const statusLabel = { 'In Progress': 'בביצוע', Blocked: 'חסומה', Planned: 'מתוכננת', Done: 'הושלמה' };
const escapeHtml = (value = '') => String(value).replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
const classForStatus = value => String(value || '').toLowerCase().replace(/[^a-z0-9-]+/g, '-');

function loadSheet(sheetName, callbackName) {
  return new Promise((resolve, reject) => {
    const script = document.createElement('script');
    const timer = window.setTimeout(() => finish(new Error('זמן הקריאה מהגיליון הסתיים')), 12000);
    const finish = result => {
      window.clearTimeout(timer);
      delete window[callbackName];
      script.remove();
      result instanceof Error ? reject(result) : resolve(result);
    };
    window[callbackName] = response => finish(response);
    script.onerror = () => finish(new Error('לא ניתן לטעון את נתוני הגיליון'));
    const query = new URLSearchParams({ tqx: `out:json;responseHandler:${callbackName}`, sheet: sheetName });
    script.src = `${sheetBase}?${query}`;
    document.head.append(script);
  });
}

function tableToRecords(response) {
  if (response.status !== 'ok') throw new Error('הגיליון החזיר שגיאה');
  const rows = response.table?.rows || [];
  const cells = row => (row.c || []).map(cell => cell?.v ?? '');
  const [header = [], ...data] = rows.map(cells);
  return data.filter(row => row.some(Boolean)).map(row => Object.fromEntries(header.map((name, index) => [name, row[index] ?? ''])));
}

function count(status) { return tasks.filter(task => task.Status === status).length; }
function renderMetrics() {
  document.querySelector('#metric-active').textContent = count('In Progress');
  document.querySelector('#metric-blocked').textContent = count('Blocked');
  document.querySelector('#metric-planned').textContent = count('Planned');
  document.querySelector('#metric-done').textContent = count('Done');
}
function renderRoadmap(items) {
  const list = document.querySelector('#roadmap');
  list.innerHTML = items.length ? items.map(item => {
    const active = item['סטטוס'] === 'In Progress' ? ' is-active' : '';
    return `<li class="${active}"><i aria-hidden="true"></i><div><strong>${escapeHtml(item['שם'] || item['Phase ID'])}</strong><small><bdi dir="ltr">${escapeHtml(item['Phase ID'])}</bdi> · ${escapeHtml(item['Epic ID'])}</small></div><em>${escapeHtml(statusLabel[item['סטטוס']] || item['סטטוס'])}</em></li>`;
  }).join('') : '<li class="loading-row">אין עדיין שלבים להצגה.</li>';
}
function renderTasks(filter = 'all') {
  const visible = tasks.filter(task => filter === 'all' || task.Status === filter);
  document.querySelector('#tasks').innerHTML = visible.length ? visible.map(task => `<article class="task"><span class="task-id"><bdi>${escapeHtml(task.ID)}</bdi></span><div><h3>${escapeHtml(task.Title)}</h3><p><bdi dir="ltr">${escapeHtml(task.Phase)}</bdi> · ${escapeHtml(task.Owner || 'ללא בעלים')} · <bdi dir="ltr">${escapeHtml(task.Release)}</bdi></p></div><span class="status ${classForStatus(task.Status)}">${escapeHtml(statusLabel[task.Status] || task.Status)}</span></article>`).join('') : '<p class="loading-row">אין משימות בתצוגה זו.</p>';
}
function renderFocus() {
  const urgent = tasks.filter(task => ['In Progress', 'Blocked'].includes(task.Status));
  document.querySelector('#focus').innerHTML = urgent.length ? urgent.map(task => `<article class="focus-item"><div><b>${escapeHtml(task.Title)}</b><span><bdi dir="ltr">${escapeHtml(task.ID)}</bdi> · ${escapeHtml(statusLabel[task.Status] || task.Status)}</span></div><small><bdi dir="ltr">${escapeHtml(task.Phase)}</bdi></small></article>`).join('') : '<p class="loading-row">אין כרגע משימות פעילות או חסומות.</p>';
}
function setStatus(message, isError = false) {
  const node = document.querySelector('.sync-state');
  node.classList.toggle('error', isError);
  document.querySelector('#sync-status').textContent = message;
}
async function refresh() {
  setStatus('מסנכרן מול Google Sheets…');
  try {
    const [backlogResponse, roadmapResponse] = await Promise.all([loadSheet('Backlog', 'watchUpBacklog'), loadSheet('Roadmap', 'watchUpRoadmap')]);
    tasks = tableToRecords(backlogResponse).filter(task => task.ID && task.Status);
    const roadmap = tableToRecords(roadmapResponse).filter(item => item['Phase ID']);
    renderMetrics(); renderTasks(); renderRoadmap(roadmap); renderFocus();
    const time = new Intl.DateTimeFormat('he-IL', { hour: '2-digit', minute: '2-digit' }).format(new Date());
    setStatus(`מסונכרן מול הגיליון · ${time}`);
  } catch (error) {
    console.error(error);
    setStatus('לא ניתן לקרוא את הגיליון כרגע — נסו רענון או פתחו אותו ישירות.', true);
  }
}
document.querySelectorAll('[data-filter]').forEach(button => button.addEventListener('click', () => { document.querySelectorAll('[data-filter]').forEach(item => item.classList.toggle('active', item === button)); renderTasks(button.dataset.filter); }));
document.querySelector('#refresh').addEventListener('click', refresh);
const ideaForm = document.querySelector('#idea-form');
if (ideaForm) {
  const ideaInput = document.querySelector('#idea-input');
  const ideaFeedback = document.querySelector('#idea-feedback');
  const ideaButton = ideaForm.querySelector('button');
  ideaForm.addEventListener('submit', async event => {
    event.preventDefault();
    if (!ideaForm.reportValidity()) return;
    const submittedIdea = ideaInput.value.trim();
    ideaButton.disabled = true;
    ideaFeedback.classList.remove('error');
    ideaFeedback.textContent = 'שומר את הרעיון…';
    try {
      const response = await fetch('/idea-capture', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8', Accept: 'application/json' },
        body: new URLSearchParams({ idea: submittedIdea })
      });
      const result = await response.json().catch(() => ({}));
      if (!response.ok || result.Idea !== submittedIdea || !result.ID) throw new Error('לא התקבל אישור שמירה');
      ideaInput.value = '';
      ideaFeedback.textContent = `נשמר ב־Ideas · ${result.ID}`;
    } catch (error) {
      console.error(error);
      ideaFeedback.classList.add('error');
      ideaFeedback.textContent = 'לא נשמר. נסו שוב — הרעיון נשאר בשדה.';
    } finally {
      ideaButton.disabled = false;
    }
  });
}
refresh();