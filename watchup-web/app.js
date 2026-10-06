const toast = document.querySelector('#toast');
const authGate = document.querySelector('#auth-gate');
const appShell = document.querySelector('#app-shell');
let toastTimer;
let csrfToken = '';
let liveRefreshTimer;
let activeEvents = [];
let lastDashboardData = null;
let selectedGroupJid = '';
let alertsPrimed = false;
let alertsEnabled = false;
const heardAlertIds = new Set();
const API_TIMEOUT_MS = 20000;

function fetchWithTimeout(url, options = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), API_TIMEOUT_MS);
  return fetch(url, { ...options, signal: controller.signal }).finally(() => clearTimeout(timer));
}

function announce(message) {
  toast.textContent = message;
  toast.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove('show'), 2600);
}

function setCount(kind, value) {
  document.querySelectorAll(`[data-event-count="${kind}"]`).forEach((target) => { target.textContent = String(value); });
}

function safeText(value, fallback = '') {
  return typeof value === 'string' && value.trim() ? value.trim() : fallback;
}

function pad2(value) {
  return String(value).padStart(2, '0');
}

function formatDateDDMMYYYY(date) {
  return `${pad2(date.getDate())}/${pad2(date.getMonth() + 1)}/${date.getFullYear()}`;
}

function formatDateTime(date) {
  if (!(date instanceof Date) || Number.isNaN(date.getTime())) return 'זמן לא זמין';
  return `${formatDateDDMMYYYY(date)} ${pad2(date.getHours())}:${pad2(date.getMinutes())}`;
}

function eventTime(event) {
  return formatDateTime(new Date(event.timestamp || event.source_timestamp || event.received_at));
}

function israeliMobileDigits(value) {
  const digits = safeText(value).replace(/\D/g, '');
  if (!digits) return '';
  if (digits.startsWith('972') && digits.length >= 12) return `0${digits.slice(3, 12)}`;
  if (digits.startsWith('05') && digits.length >= 10) return digits.slice(0, 10);
  if (/^5\d{8}$/.test(digits)) return `0${digits}`;
  return '';
}

function phoneLabel(value) {
  const local = israeliMobileDigits(value);
  if (!local) return 'מספר לא בפורמט ישראלי';
  return `\u2066${local.slice(0, 3)}-${local.slice(3)}\u2069`;
}

function phoneLabelInternational(value) {
  const local = israeliMobileDigits(value);
  if (!local) return '';
  return `\u2066+972${local.slice(1)}\u2069`;
}

function renderSyncStatus(connectionEvent) {
  const refreshed = formatDateTime(new Date());
  const state = connectionHealth(connectionEvent);
  const connectionStamp = connectionEvent ? eventTime(connectionEvent) : 'לא ידוע';
  document.querySelector('#sync-status span').textContent = `רענון מסך: ${refreshed} · אימות חיבור WhatsApp: ${state.label} · עדכון אחרון: ${connectionStamp}`;
}

function latestGroups(events) {
  const groups = new Map();
  events.filter((event) => event.type === 'group.snapshot').forEach((event) => {
    const jid = safeText(event.account?.chat_jid);
    if (jid && !groups.has(jid)) groups.set(jid, event);
  });
  return groups;
}

function trackingWords() {
  return Array.isArray(lastDashboardData?.tracking_words) ? lastDashboardData.tracking_words : [];
}

async function saveTrackingWords(words) {
  const response = await fetch('/api/watchup/tracking-words', {
    method: 'POST', credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', 'X-WatchUp-CSRF': csrfToken },
    body: JSON.stringify({ words }),
  });
  if (!response.ok) throw new Error('tracking words unavailable');
  const result = await response.json();
  lastDashboardData.tracking_words = result.words;
  return result.words;
}

function senderPhone(event) {
  return phoneLabel(event.account?.sender);
}

function senderLabel(event) {
  if (event.account?.is_from_me) return 'הטלפון של יולי';
  return safeText(event.account?.display_name) || senderPhone(event) || 'שולח שטרם זוהה';
}

function isRecognizedSender(event) {
  if (event.account?.is_from_me) return true;
  return event.account?.is_recognized === true;
}

function matchedWord(event, words) {
  const content = safeText(event.payload?.content).toLocaleLowerCase('he-IL');
  return words.find((word) => content.includes(word.toLocaleLowerCase('he-IL'))) || '';
}

function isException(event, words) {
  if (event.type === 'group.snapshot' || event.account?.is_from_me) return false;
  if (event.type === 'connection.status') {
    const status = safeText(event.account?.status);
    return status === 'disconnected' || status === 'relink_required';
  }
  if (!isRecognizedSender(event)) return true;
  return Boolean(matchedWord(event, words));
}

function contentTypeLabel(event) {
  if (event.type === 'reaction.received') return 'תגובה';
  const media = safeText(event.payload?.mediaType);
  return ({ image: 'תמונה', video: 'סרטון', audio: 'הודעה קולית', document: 'מסמך', sticker: 'מדבקה' })[media] || 'הודעת טקסט';
}

function connectionLabel(status) {
  return ({ connected: 'מחובר', disconnected: 'מנותק זמנית', relink_required: 'נדרש חיבור מחדש' })[status] || 'מצב לא ידוע';
}

function connectionHealth(connectionEvent) {
  const status = safeText(connectionEvent?.account?.status);
  const stamp = new Date(connectionEvent?.received_at || connectionEvent?.timestamp || 0);
  const verified = status === 'connected' && !Number.isNaN(stamp.getTime()) && Date.now() - stamp.getTime() < 5 * 60 * 1000;
  return { status, verified, label: verified ? 'מחובר' : status === 'connected' ? 'החיבור לא אומת לאחרונה' : connectionLabel(status) };
}

function chatSource(event, groups) {
  const group = groups.get(safeText(event.account?.chat_jid));
  if (group) return safeText(group.payload?.name, 'קבוצה');
  return event.account?.chat_type === 'group' ? 'קבוצה שטרם סונכרנה' : 'שיחה פרטית';
}

function eventPresentation(event, groups, words) {
  if (event.type === 'connection.status') {
    const status = safeText(event.account?.status);
    return { category: 'connection', title: `מצב החיבור: ${connectionLabel(status)}`, details: 'חשבון WhatsApp של יולי', art: 'connection', severity: 'דורש בדיקה', critical: true };
  }
  const source = chatSource(event, groups);
  const word = matchedWord(event, words);
  if (isRecognizedSender(event) && word) {
    return { category: 'keyword', title: `מילת מעקב: ${word}`, details: source, art: 'messages', severity: 'דחוף', critical: true };
  }
  const phone = senderPhone(event) || 'המספר לא זמין';
  return { category: 'stranger', title: `התקבלה הודעה ממספר טלפון לא מזוהה: ${phone}`, details: source, art: 'unresolved', severity: 'דחוף', critical: true };
}

function createArtwork(name, className) {
  const frame = document.createElement('span');
  frame.className = className;
  frame.setAttribute('aria-hidden', 'true');
  const image = document.createElement('img');
  image.src = `assets/feature-${name}.jpg`;
  image.alt = '';
  frame.append(image);
  return frame;
}

function createEventCard(event, groups, words, index = 0) {
  const view = eventPresentation(event, groups, words);
  const article = document.createElement('article');
  article.className = `feed-item${index === 0 ? ' selected' : ''}`;
  article.dataset.category = view.category;
  const icon = createArtwork(view.art, 'feed-artwork');
  const content = document.createElement('div');
  const meta = document.createElement('div');
  meta.className = 'feed-meta';
  const severity = document.createElement('span');
  severity.className = `severity ${view.critical ? 'important' : 'info'}`;
  severity.textContent = view.severity;
  const time = document.createElement('time');
  time.textContent = eventTime(event);
  const title = document.createElement('h2');
  title.textContent = view.title;
  const details = document.createElement('p');
  details.textContent = view.details;
  meta.append(severity, time);
  content.append(meta, title, details);
  article.append(icon, content);
  return article;
}

function renderEvents(events, groups, words) {
  const feed = document.querySelector('#alerts-feed');
  feed.replaceChildren();
  events.forEach((event, index) => feed.append(createEventCard(event, groups, words, index)));
  if (!events.length) {
    const empty = document.createElement('p');
    empty.className = 'empty-live-state';
    empty.textContent = 'אין חריגים חדשים. שיחות מזוהות לא מוצגות כאן.';
    feed.append(empty);
  }
  const count = (category) => events.filter((event) => eventPresentation(event, groups, words).category === category).length;
  document.querySelector('#alerts-count').textContent = String(events.length);
  document.querySelector('[data-filter-count="all"]').textContent = String(events.length);
  document.querySelector('[data-filter-count="stranger"]').textContent = String(count('stranger'));
  document.querySelector('[data-filter-count="keyword"]').textContent = String(count('keyword'));
  document.querySelector('[data-filter-count="connection"]').textContent = String(count('connection'));
}

function playCriticalTone() {
  const AudioContext = window.AudioContext || window.webkitAudioContext;
  if (!AudioContext) return;
  const context = playCriticalTone.context || new AudioContext();
  playCriticalTone.context = context;
  if (context.state === 'suspended') context.resume();
  const oscillator = context.createOscillator();
  const gain = context.createGain();
  oscillator.frequency.value = 880;
  gain.gain.setValueAtTime(0.0001, context.currentTime);
  gain.gain.exponentialRampToValueAtTime(0.05, context.currentTime + 0.02);
  gain.gain.exponentialRampToValueAtTime(0.0001, context.currentTime + 0.28);
  oscillator.connect(gain).connect(context.destination);
  oscillator.start();
  oscillator.stop(context.currentTime + 0.3);
}

function notifyNewCritical(events) {
  const fresh = events.filter((event) => event.event_id && !heardAlertIds.has(event.event_id));
  events.forEach((event) => { if (event.event_id) heardAlertIds.add(event.event_id); });
  if (!alertsPrimed) {
    alertsPrimed = true;
    return;
  }
  if (fresh.length && alertsEnabled) {
    playCriticalTone();
    if ('Notification' in window && Notification.permission === 'granted') new Notification('WatchUp', { body: 'התקבלה התראה חדשה שדורשת בדיקה.' });
  }
}

function validGroupImage(payload) {
  const mimeType = safeText(payload?.imageMimeType);
  const imageBase64 = safeText(payload?.imageBase64);
  return ['image/jpeg', 'image/png', 'image/webp'].includes(mimeType) && imageBase64.length <= 140000 && /^[A-Za-z0-9+/]+={0,2}$/.test(imageBase64)
    ? `data:${mimeType};base64,${imageBase64}` : '';
}

function messageCountLabel(count) {
  if (!count) return 'אין הודעות';
  return count === 1 ? 'הודעה אחת' : `${count} הודעות`;
}

function groupMessageCount(jid, events) {
  return events.filter((event) => event.type !== 'connection.status' && event.type !== 'group.snapshot' && safeText(event.account?.chat_jid) === jid).length;
}

function rosterFor(group, events) {
  const people = new Map();
  const payloadPeople = Array.isArray(group.payload?.participants) ? group.payload.participants : [];
  payloadPeople.forEach((person) => {
    const phone = phoneLabel(person?.phone);
    const name = safeText(person?.name);
    const key = phone || name;
    if (!key) return;
    people.set(key, { name, phone, count: 0, recognized: person?.isRecognized === true });
  });
  events.forEach((event) => {
    if (safeText(event.account?.chat_jid) !== safeText(group.account?.chat_jid)) return;
    if (event.type === 'group.snapshot' || event.type === 'connection.status' || event.account?.is_from_me) return;
    const phone = senderPhone(event);
    const name = safeText(event.account?.display_name);
    const key = phone || name || 'שולח שטרם זוהה';
    const current = people.get(key) || { name, phone, count: 0, recognized: isRecognizedSender(event) };
    current.count += 1;
    if (name) current.name = name;
    current.recognized = current.recognized || isRecognizedSender(event);
    people.set(key, current);
  });
  return [...people.values()].sort((left, right) => right.count - left.count || Number(left.recognized) - Number(right.recognized));
}

function renderGroupDetail(group, events) {
  const panel = document.querySelector('#group-detail');
  if (!group) {
    panel.hidden = true;
    return;
  }
  panel.hidden = false;
  const jid = safeText(group.account?.chat_jid);
  const messages = groupMessageCount(jid, events);
  const members = Number(group.payload?.participantCount) || 0;
  document.querySelector('#group-detail-title').textContent = safeText(group.payload?.name, 'קבוצה ללא שם');
  document.querySelector('#group-detail-stats').textContent = `${messageCountLabel(messages)} · ${members || 'מספר לא ידוע של'} משתתפים`;
  const list = document.querySelector('#group-detail-people');
  list.replaceChildren();
  const people = rosterFor(group, events);
  people.forEach((person) => {
    const item = document.createElement('li');
    const title = document.createElement('b');
    title.textContent = person.recognized ? person.name : `מספר לא מזוהה: ${person.phone || 'שולח שטרם זוהה'}`;
    const detail = document.createElement('small');
    detail.textContent = person.count ? `${messageCountLabel(person.count)} בקבוצה` : 'ברשימת המשתתפים, בלי הודעה אחרונה';
    item.append(title, detail);
    if (!person.recognized) item.className = 'stranger';
    list.append(item);
  });
  if (!people.length) {
    const empty = document.createElement('li');
    empty.textContent = 'רשימת המשתתפים עדיין לא הגיעה מהטלפון.';
    list.append(empty);
  }
}

function renderGroups(groups, events) {
  const list = document.querySelector('#groups-list');
  list.replaceChildren();
  let imageCount = 0;
  const ranked = [...groups.values()].sort((left, right) => {
    const activity = groupMessageCount(safeText(right.account?.chat_jid), events) - groupMessageCount(safeText(left.account?.chat_jid), events);
    return activity || (Number(right.payload?.participantCount) || 0) - (Number(left.payload?.participantCount) || 0);
  });
  ranked.forEach((event) => {
    const jid = safeText(event.account?.chat_jid);
    const row = document.createElement('button');
    row.type = 'button';
    row.className = `directory-live-row${jid === selectedGroupJid ? ' selected' : ''}`;
    const imageSource = validGroupImage(event.payload);
    if (imageSource) {
      const image = document.createElement('img');
      image.className = 'directory-avatar live-image';
      image.src = imageSource;
      image.alt = '';
      row.append(image);
      imageCount += 1;
    } else {
      row.append(createArtwork('groups', 'directory-avatar generated-artwork'));
    }
    const text = document.createElement('span');
    const name = document.createElement('b');
    name.textContent = safeText(event.payload?.name, 'קבוצה ללא שם');
    const detail = document.createElement('small');
    const messages = groupMessageCount(jid, events);
    const members = Number(event.payload?.participantCount) || 0;
    detail.textContent = `${messageCountLabel(messages)}${members ? ` · ${members} משתתפים` : ''}`;
    text.append(name, detail);
    const status = document.createElement('em');
    status.className = messages ? 'status-review' : 'status-known';
    status.textContent = messages ? 'פעילה' : 'שקטה';
    row.append(text, status);
    row.addEventListener('click', () => {
      selectedGroupJid = selectedGroupJid === jid ? '' : jid;
      renderGroups(groups, events);
    });
    list.append(row);
  });
  if (!groups.size) {
    const empty = document.createElement('p');
    empty.className = 'empty-live-state';
    empty.textContent = 'הקבוצות עדיין לא הגיעו מהטלפון המחובר.';
    list.append(empty);
  }
  renderGroupDetail(ranked.find((event) => safeText(event.account?.chat_jid) === selectedGroupJid), events);
  setCount('group', groups.size);
  setCount('image', imageCount);
  document.querySelector('#groups-kicker').textContent = `${groups.size} קבוצות · לפי פעילות`;
}

function renderContacts(events) {
  const list = document.querySelector('#contacts-list');
  list.replaceChildren();
  const strangers = new Map();
  events.filter((event) => event.type !== 'connection.status' && event.type !== 'group.snapshot' && !event.account?.is_from_me && !isRecognizedSender(event)).forEach((event) => {
    const phone = senderPhone(event) || 'שולח שטרם זוהה';
    if (!strangers.has(phone)) strangers.set(phone, event);
  });
  strangers.forEach((event, phone) => {
    const row = document.createElement('article');
    row.className = 'directory-live-row';
    const avatar = createArtwork('unresolved', 'directory-avatar generated-artwork');
    const text = document.createElement('span');
    const name = document.createElement('b');
    name.textContent = `התקבלה הודעה ממספר טלפון לא מזוהה: ${phone}`;
    const detail = document.createElement('small');
    detail.textContent = eventTime(event);
    text.append(name, detail);
    row.append(avatar, text);
    list.append(row);
  });
  if (!strangers.size) {
    const empty = document.createElement('p');
    empty.className = 'empty-live-state';
    empty.textContent = 'אין מספרים לא מזוהים כרגע.';
    list.append(empty);
  }
  setCount('sender', strangers.size);
}

function renderInsights(events, groups, words) {
  const strangers = events.filter((event) => eventPresentation(event, groups, words).category === 'stranger');
  const ranked = [...groups.values()].sort((left, right) => groupMessageCount(safeText(right.account?.chat_jid), events) - groupMessageCount(safeText(left.account?.chat_jid), events));
  const busiest = ranked[0];
  const latest = events[0] ? eventPresentation(events[0], groups, words) : null;
  document.querySelector('#insight-unrecognized').textContent = `${new Set(strangers.map((event) => senderPhone(event) || 'שולח שטרם זוהה')).size} מספרים לא מזוהים`;
  document.querySelector('#insight-active-group').textContent = busiest ? `הקבוצה הפעילה ביותר: ${safeText(busiest.payload?.name, 'קבוצה ללא שם')} · ${messageCountLabel(groupMessageCount(safeText(busiest.account?.chat_jid), events))}` : 'עדיין אין קבוצה פעילה';
  document.querySelector('#insight-critical').textContent = latest ? `ההתראה האחרונה: ${latest.title}` : 'אין התראה דחופה כרגע';
}

function renderDailyReport(events, groups, words, connectionEvent) {
  const list = document.querySelector('#daily-report');
  const exceptions = events.filter((event) => isException(event, words));
  const strangers = new Set(exceptions.filter((event) => eventPresentation(event, groups, words).category === 'stranger').map((event) => senderPhone(event) || 'שולח שטרם זוהה'));
  const ranked = [...groups.values()].sort((left, right) => groupMessageCount(safeText(right.account?.chat_jid), events) - groupMessageCount(safeText(left.account?.chat_jid), events));
  const busiest = ranked[0];
  const stamps = events.map((event) => new Date(event.received_at || event.timestamp || event.source_timestamp)).filter((date) => !Number.isNaN(date.getTime()));
  const latest = stamps.sort((left, right) => right - left)[0];
  const lines = [
    `חריגים בחלון החי: ${exceptions.length}`,
    `מספרים לא מזוהים: ${strangers.size}`,
    `קבוצות מחוברות: ${groups.size}`,
    busiest ? `הקבוצה הפעילה ביותר: ${safeText(busiest.payload?.name, 'קבוצה ללא שם')} · ${messageCountLabel(groupMessageCount(safeText(busiest.account?.chat_jid), events))}` : 'עדיין אין קבוצה פעילה',
    `מצב החיבור: ${connectionHealth(connectionEvent).label}`,
    latest ? `האירוע האחרון שנשמר: ${formatDateTime(latest)}` : 'עדיין אין אירוע שמור',
  ];
  list.replaceChildren();
  lines.forEach((line) => {
    const item = document.createElement('li');
    item.textContent = line;
    list.append(item);
  });
}

const AUDIT_LABELS = {
  login_succeeded: 'כניסה מוצלחת',
  login_failed: 'כניסה נכשלה',
  login_rate_limited: 'חסימה זמנית אחרי ניסיונות',
  logout: 'יציאה',
  view_dashboard: 'צפייה בלוח הבקרה',
  view_session: 'בדיקת חיבור לחשבון',
  view_audit: 'צפייה ביומן',
  delete_family: 'מחיקת נתוני משפחה',
};

async function loadAuditLog() {
  const list = document.querySelector('#audit-log');
  if (!list) return;
  try {
    const response = await fetch('/api/watchup/audit', { credentials: 'same-origin', cache: 'no-store' });
    if (!response.ok) throw new Error('audit unavailable');
    const payload = await response.json();
    const entries = Array.isArray(payload.entries) ? payload.entries : [];
    list.replaceChildren();
    entries.slice(0, 40).forEach((entry) => {
      const item = document.createElement('li');
      const title = document.createElement('b');
      const label = AUDIT_LABELS[entry.action] || entry.action;
      title.textContent = `${label} · ${safeText(entry.username, 'משתמש לא ידוע')}`;
      const detail = document.createElement('small');
      detail.dir = 'ltr';
      detail.textContent = formatDateTime(new Date(entry.created_at));
      item.append(title, detail);
      list.append(item);
    });
    if (!entries.length) {
      const empty = document.createElement('li');
      empty.textContent = 'עדיין אין רשומות. כל כניסה וצפייה בלוח הבקרה יופיעו כאן.';
      list.append(empty);
    }
  } catch {
    list.replaceChildren();
    const error = document.createElement('li');
    error.textContent = 'לא ניתן לטעון את יומן הצפייה כרגע.';
    list.append(error);
  }
}

function renderWords() {
  const list = document.querySelector('#tracking-words');
  list.replaceChildren();
  trackingWords().forEach((word) => {
    const item = document.createElement('li');
    const label = document.createElement('b');
    label.textContent = word;
    const remove = document.createElement('button');
    remove.type = 'button';
    remove.textContent = 'הסרה';
    remove.addEventListener('click', async () => {
      try {
        await saveTrackingWords(trackingWords().filter((itemWord) => itemWord !== word));
        renderDashboard(lastDashboardData);
        document.querySelector('#tracking-words-status').textContent = 'המילה הוסרה ונשמרה.';
      } catch { announce('לא הצלחנו לשמור את השינוי'); }
    });
    item.append(label, remove);
    list.append(item);
  });
  if (!list.childElementCount) {
    const empty = document.createElement('li');
    empty.textContent = 'עדיין אין מילות מעקב. שיחה מזוהה לא תתריע בלי מילה מהרשימה.';
    list.append(empty);
  }
}

function renderHome(events, groups, words, connectionEvent) {
  const focus = document.querySelector('#home-focus');
  focus.replaceChildren();
  if (events[0]) focus.append(createEventCard(events[0], groups, words));
  else {
    const empty = document.createElement('p');
    empty.className = 'empty-live-state';
    empty.textContent = 'אין חריג חדש. שיחות מזוהות לא מוצגות כאן.';
    focus.append(empty);
  }
  const timeline = document.querySelector('#home-timeline');
  timeline.replaceChildren();
  events.slice(0, 3).forEach((event) => {
    const view = eventPresentation(event, groups, words);
    const button = document.createElement('button');
    button.type = 'button';
    button.addEventListener('click', () => showView('alerts'));
    const dot = createArtwork(view.art, 'timeline-artwork');
    const text = document.createElement('span');
    const title = document.createElement('b');
    title.textContent = view.title;
    const detail = document.createElement('small');
    detail.textContent = view.details;
    text.append(title, detail);
    const time = document.createElement('em');
    time.textContent = eventTime(event);
    button.append(dot, text, time);
    timeline.append(button);
  });
  if (!events.length) {
    const empty = document.createElement('p');
    empty.className = 'empty-live-state';
    empty.textContent = 'אין חריגים להצגה.';
    timeline.append(empty);
  }
  const { status, verified: connected, label: connectionState } = connectionHealth(connectionEvent);
  document.querySelector('#home-title').textContent = connected ? 'הטלפון של יולי מחובר' : 'בודקים את החיבור של יולי';
  document.querySelector('#home-status-detail').textContent = connected ? 'מוצגים רק חריגים: מספר לא מזוהה, מילת מעקב, או ניתוק. הקריאה בלבד.' : 'מצב החיבור דורש בדיקה לפני שניתן לסמוך על הנתונים.';
  document.querySelector('#api-state-title').textContent = connected ? 'ה־API והטלפון מחוברים' : connectionState;
  document.querySelector('#connection-summary').textContent = connectionState;
  document.querySelector('#settings-connection-state').textContent = connectionState;
  document.querySelector('#settings-connection-detail').textContent = connected ? 'החיבור אומת בדקות האחרונות' : status === 'connected' ? `האישור האחרון היה ב־${eventTime(connectionEvent)}` : 'יש לבדוק את חיבור WhatsApp';
  const childLabel = document.querySelector('#child-connection-label');
  if (childLabel) childLabel.textContent = connected ? 'חשבון מחובר' : connectionState;
  setCount('connection', connected ? 1 : 0);
}

function renderDashboard(data) {
  lastDashboardData = data;
  const allEvents = Array.isArray(data.events) ? data.events : [];
  const groups = latestGroups([...(Array.isArray(data.groups) ? data.groups : []), ...allEvents]);
  activeEvents = allEvents.filter((event) => event.type !== 'group.snapshot');
  const words = trackingWords();
  const exceptions = activeEvents.filter((event) => isException(event, words)).slice(0, 20);
  const connectionFromApi = data.connection && data.connection.type === 'connection.status' ? data.connection : null;
  const connectionEvent = connectionFromApi || activeEvents
    .filter((event) => event.type === 'connection.status')
    .sort((left, right) => new Date(right.received_at || right.timestamp || 0) - new Date(left.received_at || left.timestamp || 0))[0];
  const exceptionCount = exceptions.filter((event) => event.type !== 'connection.status').length;
  setCount('message', exceptionCount);
  setCount('unresolved', exceptions.filter((event) => matchedWord(event, words)).length);
  document.querySelector('#environment-status').textContent = connectionHealth(connectionEvent).verified ? 'סביבת POC · נתונים חיים מהטלפון המחובר' : 'סביבת POC · החיבור לא אומת לאחרונה';
  renderSyncStatus(connectionEvent);
  document.querySelector('#api-state-detail').textContent = `${groups.size} קבוצות · ${exceptionCount} חריגים · קריאה בלבד`;
  notifyNewCritical(exceptions);
  renderEvents(exceptions, groups, words);
  renderGroups(groups, activeEvents);
  renderContacts(activeEvents);
  renderHome(exceptions, groups, words, connectionEvent);
  renderInsights(activeEvents, groups, words);
  renderDailyReport(activeEvents, groups, words, connectionEvent);
  renderWords();
  document.body.classList.remove('auth-pending', 'auth-required');
  authGate.hidden = true;
  appShell.inert = false;
}

function requireAuthentication(message = 'יש להתחבר כדי לצפות בנתונים.') {
  clearInterval(liveRefreshTimer);
  csrfToken = '';
  document.body.classList.remove('auth-pending');
  document.body.classList.add('auth-required');
  document.querySelector('#auth-gate-message').textContent = message;
  authGate.hidden = false;
  appShell.inert = true;
}

async function loadDashboard(notify = false) {
  try {
    const response = await fetchWithTimeout('/api/watchup/dashboard', { credentials: 'same-origin', cache: 'no-store' });
    if (response.status === 401) {
      requireAuthentication();
      return false;
    }
    if (!response.ok) throw new Error('dashboard unavailable');
    renderDashboard(await response.json());
    if (notify) announce('החיבור לנתונים החיים הצליח');
    return true;
  } catch {
    requireAuthentication('המערכת אינה זמינה כרגע. הנתונים לא הוצגו.');
    if (notify) announce('המערכת אינה זמינה כרגע');
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
  window.scrollTo(0, 0);
  if (view === 'rules') loadAuditLog();
}

document.querySelectorAll('[data-view-link]').forEach((link) => link.addEventListener('click', (event) => {
  event.preventDefault();
  showView(link.dataset.viewLink);
  closeMobileMenu();
}));
document.querySelectorAll('[data-view-button]').forEach((button) => button.addEventListener('click', () => showView(button.dataset.viewButton)));
document.querySelectorAll('[data-filter]').forEach((button) => button.addEventListener('click', () => {
  document.querySelectorAll('[data-filter]').forEach((item) => item.classList.remove('active'));
  button.classList.add('active');
  const filter = button.dataset.filter;
  document.querySelectorAll('#alerts-feed [data-category]').forEach((item) => item.classList.toggle('filtered', filter !== 'all' && item.dataset.category !== filter));
}));
document.querySelectorAll('[data-people-tab]').forEach((button) => button.addEventListener('click', () => {
  document.querySelectorAll('[data-people-tab]').forEach((tab) => {
    const active = tab === button;
    tab.classList.toggle('active', active);
    tab.setAttribute('aria-selected', String(active));
  });
  document.querySelectorAll('[data-people-panel]').forEach((panel) => { panel.hidden = panel.dataset.peoplePanel !== button.dataset.peopleTab; });
}));

const apiForm = document.querySelector('#api-connect-form');
const passwordInput = document.querySelector('#parent-password');
const passwordToggle = document.querySelector('#toggle-password');
const loginError = document.querySelector('#login-error');
const loginSubmit = document.querySelector('#login-submit');

document.querySelector('#tracking-words-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const input = document.querySelector('#tracking-word');
  const word = safeText(input.value);
  if (!word) return;
  const words = trackingWords();
  const status = document.querySelector('#tracking-words-status');
  try {
    if (!words.some((item) => item.toLocaleLowerCase('he-IL') === word.toLocaleLowerCase('he-IL'))) await saveTrackingWords([...words, word]);
    input.value = '';
    renderDashboard(lastDashboardData);
    status.textContent = 'מילת המעקב נשמרה.';
  } catch { status.textContent = 'השמירה נכשלה. נסו שוב.'; }
});

const mobileMenu = document.querySelector('#mobile-nav');
const mobileMenuButton = document.querySelector('#mobile-menu-button');
function closeMobileMenu() {
  mobileMenu.hidden = true;
  mobileMenu.classList.remove('open');
  mobileMenuButton.setAttribute('aria-expanded', 'false');
  mobileMenuButton.setAttribute('aria-label', 'פתח תפריט');
}
mobileMenuButton.addEventListener('click', () => {
  const open = mobileMenu.hidden;
  mobileMenu.hidden = !open;
  mobileMenu.classList.toggle('open', open);
  mobileMenuButton.setAttribute('aria-expanded', String(open));
  mobileMenuButton.setAttribute('aria-label', open ? 'סגור תפריט' : 'פתח תפריט');
});

document.querySelector('#enable-alerts').addEventListener('click', async () => {
  const AudioContext = window.AudioContext || window.webkitAudioContext;
  if (AudioContext) {
    const context = playCriticalTone.context || new AudioContext();
    playCriticalTone.context = context;
    await context.resume();
  }
  if ('Notification' in window && Notification.permission === 'default') await Notification.requestPermission();
  alertsEnabled = true;
  playCriticalTone();
  document.querySelector('#alert-sound-status').textContent = 'הצליל נבדק וההתראות פעילות במכשיר הזה.';
});

passwordToggle.addEventListener('click', () => {
  const reveal = passwordInput.type === 'password';
  passwordInput.type = reveal ? 'text' : 'password';
  passwordToggle.setAttribute('aria-pressed', String(reveal));
  passwordToggle.setAttribute('aria-label', reveal ? 'הסתר סיסמה' : 'הצג סיסמה');
  passwordToggle.classList.toggle('revealed', reveal);
});

function showLoginError(message) {
  loginError.textContent = message;
  loginError.hidden = false;
}

apiForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  loginError.hidden = true;
  if (passwordInput.value.length < 8) {
    showLoginError('הסיסמה קצרה מדי. נדרשות לפחות 8 תווים.');
    return;
  }
  loginSubmit.disabled = true;
  loginSubmit.textContent = 'מתחבר…';
  try {
    const response = await fetchWithTimeout('/api/watchup/session', {
      method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: document.querySelector('#parent-username').value.trim(), password: passwordInput.value }),
    });
    const result = response.ok ? await response.json() : null;
    if (result?.authenticated) {
      csrfToken = result.csrf_token;
      apiForm.reset();
      document.querySelector('#parent-username').value = 'eldad';
      if (await loadDashboard(true)) startPolling();
    } else if (response.status === 429) showLoginError('בוצעו יותר מדי ניסיונות. המתינו כמה דקות ונסו שוב.');
    else showLoginError('שם המשתמש או הסיסמה אינם נכונים.');
  } catch (error) {
    const timedOut = error instanceof DOMException && error.name === 'AbortError';
    showLoginError(timedOut ? 'השרת לא הגיב בזמן. נסו שוב בעוד רגע.' : 'לא הצלחנו להתחבר לשרת. בדקו את החיבור ונסו שוב.');
  } finally {
    loginSubmit.disabled = false;
    loginSubmit.textContent = 'כניסה ל־POC';
  }
});

function startPolling() {
  clearInterval(liveRefreshTimer);
  liveRefreshTimer = setInterval(() => loadDashboard(false), 15000);
}

document.querySelector('#api-disconnect').addEventListener('click', async () => {
  try {
    const response = await fetch('/api/watchup/session', { method: 'DELETE', credentials: 'same-origin', headers: { 'X-WatchUp-CSRF': csrfToken } });
    if (!response.ok) throw new Error('logout failed');
    requireAuthentication('יצאתם מהמערכת בבטחה.');
    announce('יצאתם מהמערכת');
  } catch { announce('היציאה לא בוצעה'); }
});

document.querySelector('#delete-family-data').addEventListener('click', async () => {
  if (!confirm('למחוק את אירועי המשפחה ב־WatchUp ולבטל את כניסות ההורים? חיבור WhatsApp והגיבויים אינם נמחקים.')) return;
  try {
    const response = await fetch('/api/watchup/family', { method: 'POST', credentials: 'same-origin', headers: { 'X-WatchUp-CSRF': csrfToken } });
    if (!response.ok) throw new Error('deletion failed');
    requireAuthentication('אירועי WatchUp נמחקו וכניסות ההורים בוטלו.');
    announce('אירועי WatchUp נמחקו');
  } catch { announce('המחיקה לא בוצעה'); }
});

if ('scrollRestoration' in history) history.scrollRestoration = 'manual';
history.replaceState(null, '', '#home');
showView('home', false);
async function restoreSession() {
  try {
    const response = await fetchWithTimeout('/api/watchup/session', { credentials: 'same-origin', cache: 'no-store' });
    if (!response.ok) {
      requireAuthentication();
      return;
    }
    const session = await response.json();
    if (!session.authenticated || !session.csrf_token) throw new Error('invalid session');
    csrfToken = session.csrf_token;
    if (await loadDashboard()) startPolling();
  } catch { requireAuthentication('המערכת אינה זמינה כרגע. הנתונים לא הוצגו.'); }
}
restoreSession();
