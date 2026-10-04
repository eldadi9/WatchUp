const toast = document.querySelector('#toast');
let toastTimer;
const API_TOKEN_KEY = 'watchup_dashboard_token';

function announce(message) {
  toast.textContent = message;
  toast.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove('show'), 2600);
}

function setCount(kind, value) {
  const target = document.querySelector(`[data-event-count="${kind}"]`);
  if (target) target.textContent = value;
}

function renderDashboard(data) {
  const events = Array.isArray(data.events) ? data.events : [];
  const count = (types) => events.filter((event) => types.includes(event.type)).length;
  setCount('alert', count(['rule.match', 'alert.created']));
  setCount('contact', count(['contact.added', 'contact.unknown']));
  setCount('group', count(['group.joined', 'group.added']));
  document.querySelector('#environment-status').textContent = 'סביבת POC · מוצגים אירועי בדיקה מהשרת';
  document.querySelector('#sync-status').lastChild.textContent = 'עודכן עכשיו';
  document.querySelector('#api-state-title').textContent = 'ה־API מחובר';
  document.querySelector('#api-state-detail').textContent = `${events.length} אירועי בדיקה · קריאה בלבד`;
  document.querySelector('#api-disconnect').hidden = false;
}

function setDemoState() {
  document.querySelector('#environment-status').textContent = 'סביבת הדגמה · כל הנתונים במסך זה מדומים';
  document.querySelector('#sync-status').lastChild.textContent = 'נתוני הדגמה';
  document.querySelector('#api-state-title').textContent = 'מצב הדגמה';
  document.querySelector('#api-state-detail').textContent = 'נתונים מקומיים · קריאה בלבד';
  document.querySelector('#api-disconnect').hidden = true;
}

async function loadDashboard(token, notify = false) {
  try {
    const response = await fetch('/api/watchup/dashboard', {
      headers: { Authorization: `Bearer ${token}` },
      cache: 'no-store',
    });
    if (!response.ok) throw new Error('dashboard unavailable');
    renderDashboard(await response.json());
    if (notify) announce('החיבור לנתוני ה־POC הצליח');
    return true;
  } catch {
    setDemoState();
    if (notify) announce('קוד הגישה שגוי או שה־API אינו זמין');
    return false;
  }
}

function showView(view, updateHash = true) {
  const next = document.querySelector(`[data-view="${view}"]`);
  if (!next) return;
  document.querySelectorAll('[data-view]').forEach((panel) => {
    const active = panel === next;
    panel.hidden = !active;
    panel.classList.toggle('active', active);
  });
  document.querySelectorAll('[data-view-link]').forEach((link) => {
    const active = link.dataset.viewLink === view;
    link.classList.toggle('active', active);
    if (active) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  });
  if (updateHash) history.replaceState(null, '', `#${view}`);
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

document.querySelectorAll('[data-view-link]').forEach((link) => link.addEventListener('click', (event) => {
  event.preventDefault();
  showView(link.dataset.viewLink);
}));
document.querySelectorAll('[data-view-button]').forEach((button) => button.addEventListener('click', () => showView(button.dataset.viewButton)));

document.querySelectorAll('[data-review]').forEach((button) => button.addEventListener('click', () => {
  button.closest('[data-alert]').classList.add('reviewed');
  button.disabled = true;
  button.textContent = 'נבדק';
  announce('ההתראה סומנה כנבדקה');
}));
document.querySelector('[data-review-preview]').addEventListener('click', (event) => {
  event.currentTarget.disabled = true;
  event.currentTarget.textContent = 'ההתראה נבדקה';
  announce('ההתראה סומנה כנבדקה');
});

document.querySelectorAll('[data-filter]').forEach((button) => button.addEventListener('click', () => {
  document.querySelectorAll('[data-filter]').forEach((item) => item.classList.remove('active'));
  button.classList.add('active');
  const filter = button.dataset.filter;
  document.querySelectorAll('[data-category]').forEach((item) => item.classList.toggle('filtered', filter !== 'all' && item.dataset.category !== filter));
}));

const form = document.querySelector('#rule-form');
const input = document.querySelector('#rule-input');
const list = document.querySelector('#rule-list');
form.addEventListener('submit', (event) => {
  event.preventDefault();
  const phrase = input.value.trim();
  if (phrase.length < 2) return;
  const severity = document.querySelector('#severity-select').value;
  const tone = severity === 'קריטי' ? 'critical' : severity === 'חשוב' ? 'important' : 'review';
  const item = document.createElement('li');
  item.innerHTML = `<span class="rule-status" aria-hidden="true"></span><span><b></b><small>התאמה מדויקת · כל הצ׳אטים</small></span><span class="severity ${tone}"></span><button type="button" data-remove>הסר</button>`;
  item.querySelector('b').textContent = phrase;
  item.querySelector('.severity').textContent = severity;
  item.querySelector('[data-remove]').setAttribute('aria-label', `הסר את הביטוי ${phrase}`);
  list.prepend(item);
  input.value = '';
  input.focus();
  announce(`הביטוי “${phrase}” נוסף למעקב בהדגמה`);
});
list.addEventListener('click', (event) => {
  const button = event.target.closest('[data-remove]');
  if (!button) return;
  button.closest('li').remove();
  announce('הביטוי הוסר מרשימת ההדגמה');
});
document.querySelectorAll('[data-people-tab]').forEach((button) => button.addEventListener('click', () => {
  document.querySelectorAll('[data-people-tab]').forEach((tab) => {
    const active = tab === button;
    tab.classList.toggle('active', active);
    tab.setAttribute('aria-selected', String(active));
  });
  document.querySelectorAll('[data-people-panel]').forEach((panel) => {
    panel.hidden = panel.dataset.peoplePanel !== button.dataset.peopleTab;
  });
}));

document.querySelector('[data-review-event]').addEventListener('click', (event) => {
  event.currentTarget.disabled = true;
  event.currentTarget.textContent = 'האירוע נבדק';
  announce('האירוע סומן כנבדק');
});

const apiForm = document.querySelector('#api-connect-form');
apiForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const token = document.querySelector('#api-token').value;
  if (await loadDashboard(token, true)) {
    sessionStorage.setItem(API_TOKEN_KEY, token);
    apiForm.reset();
  }
});
document.querySelector('#api-disconnect').addEventListener('click', () => {
  sessionStorage.removeItem(API_TOKEN_KEY);
  setDemoState();
  announce('החיבור ל־API נותק');
});

const initialView = location.hash.slice(1);
showView(['home', 'alerts', 'people', 'event', 'rules'].includes(initialView) ? initialView : 'home', false);
const savedToken = sessionStorage.getItem(API_TOKEN_KEY);
if (savedToken) loadDashboard(savedToken);
