const toast = document.querySelector('#toast');
const authGate = document.querySelector('#auth-gate');
const appShell = document.querySelector('#app-shell');
const BUILD_ID = 'wp80-words';
function setEnvironmentStatus(message) {
  const el = document.querySelector('#environment-status');
  if (!el) return;
  el.textContent = `${message} · ${BUILD_ID}`;
}
let toastTimer;
let csrfToken = '';
let liveRefreshTimer;
let activeEvents = [];
let lastDashboardData = null;
let selectedGroupJid = '';
let alertsPrimed = false;
let alertsEnabled = false;
let dashboardRequest = 0;
let alertsCategoryFilter = 'all';
let groupSort = 'activity';
let parentUsername = '';
let scheduleStamp = '';
let lastGroups = new Map();
let lastOffHours = [];
let selectedChildId = '';
let pairingTimer;

// Every child-scoped call names the selected child; the server checks it belongs to this parent's family.
function childQuery() {
  return selectedChildId ? `?child_id=${encodeURIComponent(selectedChildId)}` : '';
}

function selectedChildName() {
  const children = Array.isArray(lastDashboardData?.children) ? lastDashboardData.children : [];
  return safeText(children.find((child) => child.child_id === selectedChildId)?.name);
}

function pickerLabel(child) {
  const name = safeText(child.name) || child.child_id;
  if (typeof child.connected !== 'boolean') return name;
  return `${name} · ${child.connected ? 'מחובר' : 'לא מחובר'}`;
}

function renderChildPicker(data) {
  const children = Array.isArray(data.children) ? data.children : [];
  selectedChildId = safeText(data.child_id);
  const picker = document.querySelector('#child-picker');
  const select = document.querySelector('#child-select');
  const name = selectedChildName();
  document.querySelector('.child-switch b').textContent = name || 'הטלפון המחובר';
  document.querySelector('.child-avatars i').textContent = (name || 'טלפון').charAt(0);
  if (!picker || !select) return;
  picker.hidden = children.length < 2;
  const stamp = children.map((child) => `${child.child_id}:${child.name}:${child.connected}`).join('|');
  if (select.dataset.stamp !== stamp) {
    select.replaceChildren(...children.map((child) => new Option(pickerLabel(child), child.child_id)));
    select.dataset.stamp = stamp;
  }
  select.value = selectedChildId;
}
const heardAlertIds = new Set();
try { parentUsername = localStorage.getItem('watchup-parent') || ''; } catch {}
try { alertsEnabled = localStorage.getItem('watchup-alerts') === 'on'; } catch {}
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

function matchText(value) {
  return safeText(value).replace(/[\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]/g, '').replace(/\s+/g, ' ').toLocaleLowerCase('he-IL');
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
  const response = await fetch(`/api/watchup/tracking-words${childQuery()}`, {
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
  if (event.account?.is_from_me) return 'הטלפון המחובר';
  return safeText(event.account?.display_name) || senderPhone(event) || 'שולח שטרם זוהה';
}

function isRecognizedSender(event) {
  if (event.account?.is_from_me) return true;
  return event.account?.is_recognized === true || event.payload?.isRecognized === true;
}

function messageText(event) {
  const payload = event.payload || {};
  return [payload.content, payload.Content, payload.quotedContent].map((item) => safeText(item)).filter(Boolean).join('\n');
}

function wordForms(word) {
  const base = matchText(word).replace(/[^\u0590-\u05FF]/g, '');
  const forms = new Set();
  if (!base) return forms;
  const finals = { 'ם': 'מ', 'ן': 'נ', 'ץ': 'צ', 'ף': 'פ', 'ך': 'כ' };
  const withSuffix = (core, suffix) => {
    const letters = [...core];
    if (finals[letters[letters.length - 1]]) letters[letters.length - 1] = finals[letters[letters.length - 1]];
    return letters.join('') + suffix;
  };
  const cores = new Set([base]);
  ['ה', 'ים', 'ות'].forEach((suffix) => {
    if (!base.endsWith(suffix)) cores.add(withSuffix(base, suffix));
  });
  const chars = [...base];
  const vavAt = chars.findIndex((character, index) => character === 'ו' && index > 0 && index < chars.length - 1);
  if (vavAt > 0) {
    const dropped = chars.filter((_, index) => index !== vavAt).join('');
    cores.add(`נ${dropped}`);
    cores.add(withSuffix(`נ${dropped}`, 'ה'));
  }
  cores.forEach((core) => {
    forms.add(core);
    ['ו', 'ה', 'ב', 'ל', 'מ', 'ש'].forEach((prefix) => forms.add(prefix + core));
    ['ה', 'ב', 'ל', 'מ', 'ש'].forEach((prefix) => forms.add(`ו${prefix}${core}`));
  });
  return forms;
}

function matchedWord(event, words) {
  const content = matchText(messageText(event));
  const tokens = new Set(content.split(/[^\u0590-\u05FFa-z0-9]+/).filter(Boolean));
  return words.find((word) => {
    const needle = matchText(word);
    if (!needle) return false;
    if (/\s/.test(needle)) return content.includes(needle);
    return [...wordForms(needle)].some((form) => tokens.has(form));
  }) || '';
}

function isException(event, words) {
  if (event.type === 'group.snapshot' || event.account?.is_from_me || event.type === 'connection.status') return false;
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
  // ponytail: bridge heartbeats every ~2 minutes. Allow clock skew and late ticks.
  const ageMs = Number.isNaN(stamp.getTime()) ? Number.POSITIVE_INFINITY : Date.now() - stamp.getTime();
  const fresh = ageMs < 15 * 60 * 1000 || (ageMs < 0 && ageMs > -15 * 60 * 1000);
  if (status === 'disconnected' || status === 'relink_required') return { status, verified: false, label: connectionLabel(status), tone: 'critical' };
  if (status === 'connected' && fresh) return { status, verified: true, label: 'מחובר', tone: 'ok' };
  return { status: status || 'disconnected', verified: false, label: 'הניטור נעצר', tone: 'critical' };
}

function groupActivityMaps(events) {
  const messageCounts = new Map();
  const todayCounts = new Map();
  events.forEach((event) => {
    if (!isGroupMessage(event)) return;
    const jid = safeText(event.account?.chat_jid);
    if (!jid) return;
    messageCounts.set(jid, (messageCounts.get(jid) || 0) + 1);
    if (isJerusalemToday(event)) todayCounts.set(jid, (todayCounts.get(jid) || 0) + 1);
  });
  return { messageCounts, todayCounts };
}

function chatSource(event, groups) {
  const chatType = safeText(event.account?.chat_type);
  const chatJid = safeText(event.account?.chat_jid);
  if (chatType === 'status' || chatJid === 'status@broadcast') return 'סטטוס וואטסאפ';
  if (chatType === 'newsletter') return 'ערוץ';
  const group = groups.get(chatJid);
  if (group) return safeText(group.payload?.name, 'קבוצה');
  if (chatType === 'group' || chatJid.endsWith('@g.us')) return 'קבוצה שטרם סונכרנה';
  return 'שיחה פרטית';
}

function messageBody(event) {
  const text = safeText(event.payload?.content || event.payload?.Content);
  if (text) return text;
  return contentTypeLabel(event);
}

function seenKey() {
  return parentUsername || 'parent';
}

function seenMap() {
  try { return JSON.parse(localStorage.getItem('watchup-seen-alerts') || '{}'); } catch { return {}; }
}

function isAlertSeen(eventId) {
  if (!eventId) return false;
  return Boolean(seenMap()[seenKey()]?.[eventId]);
}

function markAlertSeen(eventId) {
  if (!eventId) return;
  const map = seenMap();
  map[seenKey()] = map[seenKey()] || {};
  map[seenKey()][eventId] = 1;
  try { localStorage.setItem('watchup-seen-alerts', JSON.stringify(map)); } catch {}
}

function linkState(connectionEvent) {
  const health = connectionHealth(connectionEvent);
  const detail = 'זה מצב הקישור לטלפון, לא איש קשר חדש ולא קבוצה חדשה.';
  if (health.verified) return { label: 'מחובר', detail };
  const status = safeText(connectionEvent?.account?.status);
  if (!connectionEvent || status === 'relink_required') return { label: 'ממתין לסריקה', detail };
  return { label: 'מנותק', detail: `הניטור נעצר. ${detail}` };
}

function schedule() {
  return lastDashboardData?.schedule && typeof lastDashboardData.schedule === 'object' ? lastDashboardData.schedule : {};
}

function minutesInJerusalem(date) {
  const parts = jerusalemParts(date, { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });
  const value = (type) => Number(parts.find((part) => part.type === type).value);
  return value('hour') * 60 + value('minute');
}

function outsideHours(event, hours) {
  const date = eventMoment(event);
  if (!date) return false;
  const day = hours?.[jerusalemWeekday(date)] || {};
  const windows = [day.study, day.evening].filter((pair) => Array.isArray(pair) && pair[0] && pair[1]);
  if (!windows.length) return false;
  const minute = minutesInJerusalem(date);
  return windows.every(([start, end]) => {
    const [startHour, startMinute] = start.split(':').map(Number);
    const [endHour, endMinute] = end.split(':').map(Number);
    return minute < startHour * 60 + startMinute || minute >= endHour * 60 + endMinute;
  });
}

function isActivity(event) {
  if (event.type === 'group.snapshot' || event.type === 'connection.status' || event.account?.is_from_me) return false;
  return event.type === 'message.received' || event.type === 'reaction.received';
}

function offHoursEvents(events, hours) {
  return events.filter((event) => isActivity(event) && outsideHours(event, hours));
}

function joinedToday(groups) {
  return [...groups.values()].filter((group) => isJerusalemToday({ timestamp: group.first_seen || group.received_at }));
}

function eventPresentation(event, groups, words) {
  if (event.type === 'connection.status') {
    const health = connectionHealth(event);
    return { category: 'connection', categories: ['connection'], title: `מצב החיבור: ${health.label}`, details: 'חשבון WhatsApp המחובר', body: '', art: 'connection', severity: 'קריטי', tone: 'critical' };
  }
  const source = chatSource(event, groups);
  const word = matchedWord(event, words);
  const body = messageBody(event);
  if (word) {
    const phone = senderPhone(event);
    const categories = isRecognizedSender(event) ? ['keyword'] : ['stranger', 'keyword'];
    const keywordTitle = `מילת מעקב: ${word}`;
    const title = categories.includes('stranger')
      ? `התקבלה הודעה ממספר טלפון לא מזוהה: ${phone || 'המספר לא זמין'} · ${keywordTitle}`
      : keywordTitle;
    const details = isRecognizedSender(event) ? source : `${source} · מספר לא מזוהה: ${phone || 'המספר לא זמין'}`;
    return { category: 'keyword', categories, title, details, body, art: 'messages', severity: 'קריטי', tone: 'critical' };
  }
  if (isRecognizedSender(event)) {
    return { category: 'hours', categories: [], title: 'פעילות מחוץ לשעות', details: source, body: '', art: 'messages', severity: 'מידע', tone: 'info' };
  }
  const phone = senderPhone(event) || 'המספר לא זמין';
  return { category: 'stranger', categories: ['stranger'], title: `התקבלה הודעה ממספר טלפון לא מזוהה: ${phone}`, details: source, body, art: 'unresolved', severity: 'דחוף', critical: true };
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
  const categories = view.categories || [view.category];
  article.className = `feed-item${index === 0 ? ' selected' : ''}`;
  article.dataset.category = view.category;
  article.dataset.categories = categories.join(' ');
  article.dataset.today = isJerusalemToday(event) ? '1' : '0';
  if (categories.includes('stranger') && !isAlertSeen(event.event_id)) article.classList.add('unseen');
  const icon = createArtwork(view.art, 'feed-artwork');
  const content = document.createElement('div');
  content.className = 'feed-content';
  const meta = document.createElement('div');
  meta.className = 'feed-meta';
  const severity = document.createElement('span');
  severity.className = `severity ${view.tone || (view.critical ? 'important' : 'info')}`;
  severity.textContent = view.severity;
  const time = document.createElement('time');
  time.textContent = eventTime(event);
  const title = document.createElement('h2');
  title.textContent = view.title;
  const details = document.createElement('p');
  details.className = 'feed-details';
  details.textContent = view.details;
  meta.append(severity, time);
  content.append(meta, title, details);
  let body = null;
  if (view.body) {
    body = document.createElement('p');
    body.className = 'feed-message';
    body.dir = 'auto';
    body.textContent = view.body;
    content.append(body);
  }
  article.addEventListener('click', (clickEvent) => {
    if (categories.includes('stranger')) {
      markAlertSeen(event.event_id);
      article.classList.remove('unseen');
    }
    if (!body) return;
    // Click message (or card) toggles full text; default is 3-line clamp.
    const onMessage = clickEvent.target === body || body.contains(clickEvent.target);
    if (onMessage || !clickEvent.target.closest('a,button')) {
      body.classList.toggle('expanded');
    }
  });
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
  let strangerCount = 0;
  let keywordCount = 0;
  let todayCount = 0;
  events.forEach((event) => {
    const categories = eventPresentation(event, groups, words).categories || [];
    if (categories.includes('stranger')) strangerCount += 1;
    if (categories.includes('keyword')) keywordCount += 1;
    if (isJerusalemToday(event)) todayCount += 1;
  });
  document.querySelector('#alerts-count').textContent = String(events.length);
  document.querySelector('[data-filter-count="all"]').textContent = String(events.length);
  document.querySelector('[data-filter-count="today"]').textContent = String(todayCount);
  document.querySelector('[data-filter-count="stranger"]').textContent = String(strangerCount);
  document.querySelector('[data-filter-count="keyword"]').textContent = String(keywordCount);
  document.querySelector('[data-filter-count="joined"]').textContent = String(joinedToday(groups).length);
  document.querySelector('[data-filter-count="hours"]').textContent = String(lastOffHours.length);
  applyAlertsCategoryFilter();
}

function renderAlertsExtra() {
  const extra = document.querySelector('#alerts-extra');
  if (!extra) return;
  extra.replaceChildren();
  const special = alertsCategoryFilter === 'joined' || alertsCategoryFilter === 'hours';
  extra.hidden = !special;
  const feed = document.querySelector('#alerts-feed');
  if (feed) feed.hidden = special;
  if (alertsCategoryFilter === 'joined') {
    const groups = joinedToday(lastGroups);
    if (!groups.length) {
      const empty = document.createElement('p');
      empty.className = 'empty-live-state';
      empty.textContent = 'היום לא נוספו קבוצות.';
      extra.append(empty);
      return;
    }
    groups.forEach((group) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'directory-live-row';
      const name = document.createElement('b');
      name.textContent = safeText(group.payload?.name, 'קבוצה ללא שם');
      button.append(name);
      button.addEventListener('click', () => {
        selectedGroupJid = safeText(group.account?.chat_jid);
        showView('people');
        renderGroups(lastGroups, activeEvents);
      });
      extra.append(button);
    });
    return;
  }
  if (alertsCategoryFilter !== 'hours') return;
  if (!lastOffHours.length) {
    const empty = document.createElement('p');
    empty.className = 'empty-live-state';
    empty.textContent = 'אין פעילות מחוץ לשעות שהוגדרו.';
    extra.append(empty);
    return;
  }
  lastOffHours.forEach((event) => {
    const view = eventPresentation(event, lastGroups, trackingWords());
    const showBody = view.categories?.includes('stranger') || view.categories?.includes('keyword');
    const article = document.createElement('article');
    article.className = 'feed-item';
    const content = document.createElement('div');
    content.className = 'feed-content';
    const title = document.createElement('h2');
    title.textContent = 'פעילות מחוץ לשעות';
    const details = document.createElement('p');
    details.className = 'feed-details';
    details.textContent = `${eventTime(event)} · ${chatSource(event, lastGroups)}`;
    content.append(title, details);
    if (showBody && view.body) {
      const body = document.createElement('p');
      body.className = 'feed-message';
      body.dir = 'auto';
      body.textContent = view.body;
      body.addEventListener('click', () => body.classList.toggle('expanded'));
      content.append(body);
    }
    article.append(content);
    extra.append(article);
  });
}

function applyAlertsCategoryFilter() {
  document.querySelectorAll('[data-filter]').forEach((item) => {
    item.classList.toggle('active', item.dataset.filter === alertsCategoryFilter);
  });
  const special = alertsCategoryFilter === 'joined' || alertsCategoryFilter === 'hours';
  document.querySelectorAll('#alerts-feed [data-categories]').forEach((item) => {
    const categories = item.dataset.categories.split(' ');
    let show = !special;
    if (alertsCategoryFilter === 'today') show = item.dataset.today === '1';
    else if (alertsCategoryFilter !== 'all' && !special) show = categories.includes(alertsCategoryFilter);
    item.classList.toggle('filtered', !show);
  });
  renderAlertsExtra();
}

function playCriticalTone() {
  const AudioContext = window.AudioContext || window.webkitAudioContext;
  if (!AudioContext) return;
  const context = playCriticalTone.context || new AudioContext();
  playCriticalTone.context = context;
  const start = () => {
    const now = context.currentTime;
    [880, 1175].forEach((frequency, index) => {
      const oscillator = context.createOscillator();
      const gain = context.createGain();
      const at = now + index * 0.28;
      oscillator.type = 'sine';
      oscillator.frequency.value = frequency;
      gain.gain.setValueAtTime(0.0001, at);
      gain.gain.exponentialRampToValueAtTime(0.18, at + 0.03);
      gain.gain.exponentialRampToValueAtTime(0.0001, at + 0.24);
      oscillator.connect(gain).connect(context.destination);
      oscillator.start(at);
      oscillator.stop(at + 0.25);
    });
  };
  if (context.state === 'suspended') {
    context.resume().then(start).catch(() => {});
    return;
  }
  start();
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
  // Skip full-string regex on large base64 — it froze the parent UI on refresh.
  if (!['image/jpeg', 'image/png', 'image/webp'].includes(mimeType)) return '';
  if (!imageBase64 || imageBase64.length > 140000) return '';
  if (imageBase64.length % 4 === 1) return '';
  return `data:${mimeType};base64,${imageBase64}`;
}

function messageCountLabel(count) {
  if (!count) return 'אין הודעות';
  return count === 1 ? 'הודעה אחת' : `${count} הודעות`;
}

function eventMoment(event) {
  const date = new Date(event.timestamp || event.received_at || event.source_timestamp || 0);
  return Number.isNaN(date.getTime()) ? null : date;
}

function jerusalemParts(date, options) {
  return new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Jerusalem', ...options }).formatToParts(date);
}

function jerusalemDayKey(date) {
  const parts = jerusalemParts(date, { year: 'numeric', month: '2-digit', day: '2-digit' });
  const value = (type) => parts.find((part) => part.type === type).value;
  return `${value('year')}-${value('month')}-${value('day')}`;
}

function isJerusalemToday(event, now = new Date()) {
  const date = eventMoment(event);
  return Boolean(date) && jerusalemDayKey(date) === jerusalemDayKey(now);
}

function jerusalemWeekday(date) {
  const name = new Intl.DateTimeFormat('en-US', { timeZone: 'Asia/Jerusalem', weekday: 'short' }).format(date);
  return ({ Sun: 'sun', Mon: 'mon', Tue: 'tue', Wed: 'wed', Thu: 'thu', Fri: 'fri', Sat: 'sat' })[name] || 'sun';
}

function isGroupMessage(event) {
  if (event.type === 'connection.status' || event.type === 'group.snapshot' || event.account?.is_from_me) return false;
  const jid = safeText(event.account?.chat_jid);
  return safeText(event.account?.chat_type) === 'group' || jid.endsWith('@g.us');
}

function groupMessageCount(jid, events) {
  return events.filter((event) => isGroupMessage(event) && safeText(event.account?.chat_jid) === jid).length;
}

function messagesToday(events, jid) {
  return events.filter((event) => isGroupMessage(event) && isJerusalemToday(event) && safeText(event.account?.chat_jid) === jid).length;
}

function busiestHour(events) {
  const counts = new Map();
  events.filter((event) => isGroupMessage(event) && isJerusalemToday(event)).forEach((event) => {
    const hour = eventMoment(event).getHours();
    counts.set(hour, (counts.get(hour) || 0) + 1);
  });
  let best = null;
  counts.forEach((count, hour) => {
    if (!best || count > best.count) best = { hour, count };
  });
  return best;
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

function renderGroupDetail(group, events, anchor) {
  const panel = document.querySelector('#group-detail');
  if (!group || !anchor) {
    panel.hidden = true;
    return;
  }
  const jid = safeText(group.account?.chat_jid);
  const messages = groupMessageCount(jid, events);
  const members = Number(group.payload?.participantCount) || 0;
  const people = rosterFor(group, events);
  const top = people.find((person) => person.count > 0);
  const topLabel = top ? (top.name || top.phone || 'שולח שטרם זוהה') : '';
  const rest = Math.max(0, messages - (top ? top.count : 0));
  document.querySelector('#group-detail-title').textContent = safeText(group.payload?.name, 'קבוצה ללא שם');
  document.querySelector('#group-detail-stats').textContent = top
    ? `${messageCountLabel(messages)} · ${members || 'מספר לא ידוע של'} משתתפים · ${topLabel} · ${messageCountLabel(top.count)} מתוך ${messageCountLabel(messages)} · כל השאר ${messageCountLabel(rest)}`
    : `${messageCountLabel(messages)} · ${members || 'מספר לא ידוע של'} משתתפים`;
  const list = document.querySelector('#group-detail-people');
  list.replaceChildren();
  people.forEach((person) => {
    const item = document.createElement('li');
    const title = document.createElement('b');
    title.textContent = person.recognized
      ? person.name
      : person.name
        ? `${person.name} · מספר לא מזוהה: ${person.phone || 'שולח שטרם זוהה'}`
        : `מספר לא מזוהה: ${person.phone || 'שולח שטרם זוהה'}`;
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
  panel.hidden = false;
  anchor.after(panel);
}

function renderGroups(groups, events) {
  const list = document.querySelector('#groups-list');
  const openPanel = document.querySelector('#group-detail');
  if (openPanel && list.contains(openPanel)) {
    openPanel.hidden = true;
    list.parentElement.append(openPanel);
  }
  list.replaceChildren();
  let imageCount = 0;
  let openRow = null;
  const { messageCounts, todayCounts } = groupActivityMaps(events);
  const unrecognizedCount = (group) => {
    if (Number.isFinite(Number(group.payload?.unrecognized_count))) return Number(group.payload.unrecognized_count);
    const people = Array.isArray(group.payload?.participants) ? group.payload.participants : [];
    return people.filter((person) => person?.isRecognized !== true).length;
  };
  const ranked = [...groups.values()].sort((left, right) => {
    const leftJid = safeText(left.account?.chat_jid);
    const rightJid = safeText(right.account?.chat_jid);
    if (groupSort === 'today') return (todayCounts.get(rightJid) || 0) - (todayCounts.get(leftJid) || 0);
    if (groupSort === 'strangers') return unrecognizedCount(right) - unrecognizedCount(left);
    if (groupSort === 'newest') return new Date(right.first_seen || 0) - new Date(left.first_seen || 0);
    const activity = (messageCounts.get(rightJid) || 0) - (messageCounts.get(leftJid) || 0);
    return activity || (Number(right.payload?.participantCount) || 0) - (Number(left.payload?.participantCount) || 0);
  });
  ranked.forEach((event) => {
    const jid = safeText(event.account?.chat_jid);
    const row = document.createElement('button');
    row.type = 'button';
    const open = jid === selectedGroupJid;
    row.className = `directory-live-row${open ? ' selected' : ''}`;
    row.setAttribute('aria-expanded', String(open));
    // Dashboard no longer ships base64 avatars; keep placeholder artwork.
    const imageSource = validGroupImage(event.payload);
    if (imageSource) {
      const image = document.createElement('img');
      image.className = 'directory-avatar live-image';
      image.loading = 'lazy';
      image.src = imageSource;
      image.alt = '';
      row.append(image);
      imageCount += 1;
    } else {
      row.append(createArtwork('groups', 'directory-avatar generated-artwork'));
      if (event.payload?.has_image) imageCount += 1;
    }
    const text = document.createElement('span');
    const name = document.createElement('b');
    name.textContent = safeText(event.payload?.name, 'קבוצה ללא שם');
    const detail = document.createElement('small');
    const messages = messageCounts.get(jid) || 0;
    const members = Number(event.payload?.participantCount) || 0;
    detail.textContent = `${messageCountLabel(messages)}${members ? ` · ${members} משתתפים` : ''}`;
    text.append(name, detail);
    const status = document.createElement('em');
    status.className = messages ? 'status-review' : 'status-known';
    status.textContent = messages ? 'פעילה' : 'שקטה';
    row.append(text, status);
    row.addEventListener('click', () => {
      const opening = selectedGroupJid !== jid;
      selectedGroupJid = opening ? jid : '';
      renderGroups(groups, events);
      if (opening) document.querySelector('#group-detail')?.scrollIntoView({ block: 'nearest' });
    });
    list.append(row);
    if (open) openRow = row;
  });
  if (!groups.size) {
    const empty = document.createElement('p');
    empty.className = 'empty-live-state';
    empty.textContent = 'הקבוצות עדיין לא הגיעו מהטלפון המחובר.';
    list.append(empty);
  }
  renderGroupDetail(openRow ? ranked.find((event) => safeText(event.account?.chat_jid) === selectedGroupJid) : null, events, openRow);
  setCount('group', groups.size);
  setCount('image', imageCount);
  const sortLabel = ({ activity: 'לפי פעילות', today: 'הכי הרבה הודעות היום', strangers: 'הכי הרבה משתתפים לא מזוהים', newest: 'הקבוצה החדשה ביותר', sender: 'לפי שולח היום' })[groupSort] || 'לפי פעילות';
  document.querySelector('#groups-kicker').textContent = `${groups.size} קבוצות · ${sortLabel}`;
}

function renderContacts(events, groups) {
  const list = document.querySelector('#contacts-list');
  list.replaceChildren();
  const strangers = new Map();
  events.filter((event) => event.type !== 'connection.status' && event.type !== 'group.snapshot' && !event.account?.is_from_me && !isRecognizedSender(event)).forEach((event) => {
    const phone = senderPhone(event) || 'שולח שטרם זוהה';
    if (!strangers.has(phone)) strangers.set(phone, event);
  });
  const rankedStrangers = [...strangers.entries()].sort((left, right) => {
    if (groupSort !== 'sender') return 0;
    const countFor = (phone) => events.filter((event) => isActivity(event) && isJerusalemToday(event) && (senderPhone(event) || 'שולח שטרם זוהה') === phone).length;
    return countFor(right[0]) - countFor(left[0]);
  });
  rankedStrangers.forEach(([phone, event]) => {
    const row = document.createElement('article');
    row.className = 'directory-live-row';
    const avatar = createArtwork('unresolved', 'directory-avatar generated-artwork');
    const text = document.createElement('span');
    const name = document.createElement('b');
    name.textContent = `התקבלה הודעה ממספר טלפון לא מזוהה: ${phone}`;
    const detail = document.createElement('small');
    detail.dir = 'auto';
    const todayCount = events.filter((item) => isActivity(item) && isJerusalemToday(item) && (senderPhone(item) || 'שולח שטרם זוהה') === phone).length;
    detail.textContent = groupSort === 'sender'
      ? `${todayCount === 1 ? 'הודעה אחת היום' : `${todayCount} הודעות היום`} · ${eventTime(event)} · ${chatSource(event, groups)}`
      : `${eventTime(event)} · ${chatSource(event, groups)} · ${messageBody(event)}`;
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

function renderGroupBoard(events, groups, changes) {
  const root = document.querySelector('#group-dashboard');
  if (!root) return;
  root.replaceChildren();
  const { todayCounts } = groupActivityMaps(events);
  let todayCount = 0;
  todayCounts.forEach((count) => { todayCount += count; });
  const summary = document.createElement('p');
  const hour = busiestHour(events);
  summary.textContent = hour
    ? `${messageCountLabel(todayCount)} בקבוצות היום · השעה העמוסה ${pad2(hour.hour)}:00 · ${messageCountLabel(hour.count)}`
    : 'עדיין אין הודעות קבוצה מהיום.';
  root.append(summary);
  [...groups.values()]
    .filter((group) => (todayCounts.get(safeText(group.account?.chat_jid)) || 0) > 0)
    .sort((left, right) => (todayCounts.get(safeText(right.account?.chat_jid)) || 0) - (todayCounts.get(safeText(left.account?.chat_jid)) || 0))
    .slice(0, 6)
    .forEach((group) => {
      const jid = safeText(group.account?.chat_jid);
      const button = document.createElement('button');
      button.type = 'button';
      const name = document.createElement('b');
      name.textContent = safeText(group.payload?.name, 'קבוצה ללא שם');
      const count = document.createElement('span');
      count.textContent = messageCountLabel(todayCounts.get(jid) || 0);
      button.append(name, count);
      button.addEventListener('click', () => {
        selectedGroupJid = jid;
        showView('people');
        renderGroups(groups, events);
      });
      root.append(button);
    });
  const changeList = Array.isArray(changes) ? changes.filter((change) => safeText(change?.chat_jid)) : [];
  if (!changeList.length) {
    const quiet = document.createElement('p');
    quiet.textContent = 'אין הצטרפות או עזיבה מאז הסנכרון הקודם.';
    root.append(quiet);
    return;
  }
  const list = document.createElement('ul');
  changeList.slice(0, 4).forEach((change) => {
    const item = document.createElement('li');
    const parts = [];
    if (Array.isArray(change.added) && change.added.length) parts.push(`הצטרפו ${change.added.slice(0, 4).join(', ')}`);
    if (Array.isArray(change.left) && change.left.length) parts.push(`עזבו ${change.left.slice(0, 4).join(', ')}`);
    item.textContent = `${safeText(change.name, 'קבוצה')}: ${parts.join(' · ')}`;
    list.append(item);
  });
  root.append(list);
}

function busiestGroupToday(groups, todayCounts) {
  let best = null;
  let bestCount = 0;
  groups.forEach((group) => {
    const count = todayCounts.get(safeText(group.account?.chat_jid)) || 0;
    if (count > bestCount) {
      best = group;
      bestCount = count;
    }
  });
  return best ? { group: best, count: bestCount } : null;
}

function renderInsights(events, groups, words) {
  const strangers = events.filter((event) => (eventPresentation(event, groups, words).categories || []).includes('stranger'));
  const { todayCounts } = groupActivityMaps(events);
  const busiest = busiestGroupToday(groups, todayCounts);
  const latest = events.find((event) => isException(event, words));
  const latestView = latest ? eventPresentation(latest, groups, words) : null;
  document.querySelector('#insight-unrecognized').textContent = `${new Set(strangers.map((event) => senderPhone(event) || 'שולח שטרם זוהה')).size} מספרים לא מזוהים`;
  document.querySelector('#insight-active-group').textContent = busiest ? `הכי הרבה הודעות היום: ${safeText(busiest.group.payload?.name, 'קבוצה ללא שם')} · ${messageCountLabel(busiest.count)}` : 'עדיין אין קבוצה פעילה היום';
  document.querySelector('#insight-critical').textContent = latestView ? `ההתראה האחרונה: ${latestView.title}` : 'אין התראה דחופה כרגע';
  renderGroupBoard(events, groups, lastDashboardData?.group_changes);
}

function renderDailyReport(events, groups, words, connectionEvent) {
  const list = document.querySelector('#daily-report');
  const exceptions = events.filter((event) => isException(event, words));
  const strangers = new Set(exceptions.filter((event) => (eventPresentation(event, groups, words).categories || []).includes('stranger')).map((event) => senderPhone(event) || 'שולח שטרם זוהה'));
  const { todayCounts } = groupActivityMaps(events);
  const busiest = busiestGroupToday(groups, todayCounts);
  const stamps = events.map((event) => new Date(event.received_at || event.timestamp || event.source_timestamp)).filter((date) => !Number.isNaN(date.getTime()));
  const latest = stamps.sort((left, right) => right - left)[0];
  const lines = [
    `חריגים בחלון החי: ${exceptions.length}`,
    `מספרים לא מזוהים: ${strangers.size}`,
    `קבוצות מחוברות: ${groups.size}`,
    busiest ? `הכי הרבה הודעות היום: ${safeText(busiest.group.payload?.name, 'קבוצה ללא שם')} · ${messageCountLabel(busiest.count)}` : 'עדיין אין קבוצה פעילה היום',
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
  reset_today: 'השארת היום בלבד',
  update_schedule: 'עדכון שעות',
  update_tracking_words: 'עדכון מילות מעקב',
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
  const words = trackingWords();
  const countEl = document.querySelector('#tracking-words-count');
  if (countEl) {
    const n = words.length;
    countEl.textContent = n === 0 ? 'אין מילים · לחצו לפתיחה' : n === 1 ? 'מילה אחת · לחצו לפתיחה' : `${n} מילים · לחצו לפתיחה`;
  }
  list.replaceChildren();
  words.forEach((word) => {
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
    empty.className = 'words-empty';
    empty.textContent = 'עדיין אין מילות מעקב.';
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
    detail.dir = 'auto';
    detail.textContent = view.body ? `${view.details} · ${view.body}` : view.details;
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
  const { status, verified: connected } = connectionHealth(connectionEvent);
  const link = linkState(connectionEvent);
  document.querySelector('#home-title').textContent = connected ? 'הטלפון מחובר' : link.label;
  document.querySelector('#home-status-detail').textContent = connected ? 'מוצגים רק חריגים: מספר לא מזוהה, מילת מעקב, או ניתוק. הקריאה בלבד.' : 'האור וההתראה מראים את אותו מצב. הנתונים לא אמינים עד שהחיבור חוזר.';
  document.querySelector('#api-state-title').textContent = link.label;
  document.querySelector('#connection-summary').textContent = link.detail;
  document.querySelector('#settings-connection-state').textContent = link.label;
  document.querySelector('#settings-connection-detail').textContent = connected ? 'החיבור אומת בדקות האחרונות' : status === 'connected' ? `האישור האחרון היה ב־${eventTime(connectionEvent)}` : 'יש לבדוק את חיבור WhatsApp';
  const childLabel = document.querySelector('#child-connection-label');
  if (childLabel) childLabel.textContent = connected ? 'חשבון מחובר' : link.label;
  setCount('connection', link.label);
  const connectionCount = document.querySelector('[data-filter-count="connection"]');
  if (connectionCount) connectionCount.textContent = link.label;
}

function renderSchedule() {
  const grid = document.querySelector('#schedule-grid');
  if (!grid) return;
  const next = JSON.stringify(schedule());
  if (next === scheduleStamp && grid.childElementCount) return;
  scheduleStamp = next;
  const hours = schedule();
  const days = [['sun', 'ראשון'], ['mon', 'שני'], ['tue', 'שלישי'], ['wed', 'רביעי'], ['thu', 'חמישי'], ['fri', 'שישי'], ['sat', 'שבת']];
  grid.replaceChildren();
  const head = document.createElement('div');
  head.className = 'schedule-head';
  head.setAttribute('aria-hidden', 'true');
  head.innerHTML = '<span></span><span class="schedule-head-study">לימודים</span><span class="schedule-head-evening">ערב</span>';
  grid.append(head);
  days.forEach(([key, label]) => {
    const row = document.createElement('label');
    row.className = 'schedule-row';
    const name = document.createElement('span');
    name.className = 'schedule-day';
    name.textContent = label;
    row.append(name);
    ['study', 'evening'].forEach((windowName) => {
      const pair = Array.isArray(hours[key]?.[windowName]) ? hours[key][windowName] : [];
      const slot = document.createElement('span');
      slot.className = `schedule-slot schedule-${windowName}`;
      [0, 1].forEach((index) => {
        const input = document.createElement('input');
        input.type = 'time';
        input.dataset.day = key;
        input.dataset.window = windowName;
        input.dataset.edge = index ? 'end' : 'start';
        input.value = pair[index] || '';
        input.setAttribute('aria-label', `${label} ${windowName === 'study' ? 'לימודים' : 'ערב'} ${index ? 'סיום' : 'התחלה'}`);
        slot.append(input);
      });
      row.append(slot);
    });
    grid.append(row);
  });
}

function scheduleFromForm() {
  const result = {};
  ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat'].forEach((day) => {
    result[day] = {};
    ['study', 'evening'].forEach((windowName) => {
      const start = (document.querySelector(`#schedule-grid input[data-day="${day}"][data-window="${windowName}"][data-edge="start"]`)?.value || '').slice(0, 5);
      const end = (document.querySelector(`#schedule-grid input[data-day="${day}"][data-window="${windowName}"][data-edge="end"]`)?.value || '').slice(0, 5);
      if ((start && !end) || (!start && end)) throw new Error('partial window');
      result[day][windowName] = start && end ? [start, end] : null;
    });
  });
  return result;
}

let lastRenderFingerprint = '';

function revealAuthenticatedShell() {
  document.body.classList.remove('auth-pending', 'auth-required');
  authGate.hidden = true;
  authGate.setAttribute('inert', '');
  authGate.style.pointerEvents = 'none';
  appShell.inert = false;
  syncMobileNav();
}

function dashboardFingerprint(data, health, exceptionCount) {
  const events = Array.isArray(data?.events) ? data.events : [];
  const newest = events[0]?.event_id || '';
  // ponytail: ignore connection.received_at — heartbeats every 2m must not rebuild the whole DOM.
  const connection = safeText(data?.connection?.account?.status) || (health?.verified ? 'ok' : 'down');
  return `${connection}|${health?.verified ? 1 : 0}|${exceptionCount}|${events.length}|${newest}|${Array.isArray(data?.groups) ? data.groups.length : 0}`;
}

function renderDashboard(data, force = false) {
  lastDashboardData = data;
  renderChildPicker(data);
  window.maybeStartOnboarding?.(data);
  const allEvents = Array.isArray(data.events) ? data.events : [];
  const groups = latestGroups([...(Array.isArray(data.groups) ? data.groups : []), ...allEvents]);
  lastGroups = groups;
  activeEvents = allEvents.filter((event) => event.type !== 'group.snapshot');
  lastOffHours = offHoursEvents(activeEvents, schedule());
  const words = trackingWords();
  const connectionFromApi = data.connection && data.connection.type === 'connection.status' ? data.connection : null;
  const connectionEvent = connectionFromApi || activeEvents
    .filter((event) => event.type === 'connection.status')
    .sort((left, right) => new Date(right.received_at || right.timestamp || 0) - new Date(left.received_at || left.timestamp || 0))[0];
  const health = connectionHealth(connectionEvent);
  const exceptions = activeEvents.filter((event) => isException(event, words));
  if (!health.verified) {
    const alertEvent = connectionEvent ? { ...connectionEvent } : { type: 'connection.status', account: { status: '' }, received_at: '', event_id: 'connection-missing' };
    if (!alertEvent.event_id) alertEvent.event_id = `connection:${safeText(alertEvent.account?.status, 'stale')}:${alertEvent.received_at || alertEvent.timestamp || 'none'}`;
    exceptions.unshift(alertEvent);
  }
  document.body.classList.toggle('connection-down', !health.verified);
  const exceptionCount = exceptions.length;
  const fingerprint = `${selectedChildId}|${dashboardFingerprint(data, health, exceptionCount)}|${groupSort}|${alertsCategoryFilter}`;
  // Overlay off first — never leave a transparent login layer blocking taps.
  revealAuthenticatedShell();
  setCount('message', exceptionCount);
  setCount('unresolved', exceptions.filter((event) => matchedWord(event, words)).length);
  setEnvironmentStatus(health.verified ? 'סביבת POC · נתונים חיים מהטלפון המחובר' : `סביבת POC · ${health.label}`);
  renderSyncStatus(connectionEvent);
  document.querySelector('#api-state-detail').textContent = `${groups.size} קבוצות · ${exceptionCount} חריגים · קריאה בלבד`;
  // ponytail: heartbeat polls must not rebuild home/events/groups DOM every 15s.
  if (!force && fingerprint === lastRenderFingerprint) {
    notifyNewCritical([...exceptions, ...lastOffHours]);
    return;
  }
  lastRenderFingerprint = fingerprint;
  notifyNewCritical([...exceptions, ...lastOffHours]);
  renderHome(exceptions, groups, words, connectionEvent);
  renderEvents(exceptions, groups, words);
  renderGroups(groups, activeEvents);
  renderContacts(activeEvents, groups);
  renderInsights(activeEvents, groups, words);
  renderDailyReport(activeEvents, groups, words, connectionEvent);
  renderWords();
  renderSchedule();
}

function requireAuthentication(message = 'יש להתחבר כדי לצפות בנתונים.') {
  clearInterval(liveRefreshTimer);
  csrfToken = '';
  lastRenderFingerprint = '';
  document.body.classList.remove('auth-pending');
  document.body.classList.add('auth-required');
  document.querySelector('#auth-gate-message').textContent = message;
  authGate.hidden = false;
  authGate.removeAttribute('inert');
  authGate.style.pointerEvents = '';
  appShell.inert = true;
  syncMobileNav();
}

async function loadDashboard(notify = false) {
  const request = ++dashboardRequest;
  try {
    const response = await fetchWithTimeout(`/api/watchup/dashboard${childQuery()}`, { credentials: 'same-origin', cache: 'no-store' });
    if (request !== dashboardRequest) return true;
    if (response.status === 401) {
      requireAuthentication();
      return false;
    }
    if (response.status === 403 && selectedChildId) {
      // The selected child is not in this family (or no longer exists): fall back to the family's first child.
      selectedChildId = '';
      return loadDashboard(notify);
    }
    if (response.status === 502 || response.status === 503 || response.status === 504) {
      if (csrfToken || lastDashboardData) {
        setEnvironmentStatus('סביבת POC · השרת לא ענה, המסך נשאר פתוח');
        revealAuthenticatedShell();
        return false;
      }
    }
    if (!response.ok) throw new Error('dashboard unavailable');
    const data = await response.json();
    if (request !== dashboardRequest) return true;
    try {
      renderDashboard(data);
    } catch {
      revealAuthenticatedShell();
      if (notify) announce('המסך נפתח, אבל חלק מהתצוגה נכשל');
      return Boolean(csrfToken);
    }
    if (notify) announce('החיבור לנתונים החיים הצליח');
    return true;
  } catch {
    if (csrfToken) {
      setEnvironmentStatus(lastDashboardData
        ? 'סביבת POC · הרענון נכשל, הנתונים הקודמים נשארו על המסך'
        : 'סביבת POC · השרת לא ענה, נסו שוב בעוד רגע');
      revealAuthenticatedShell();
      return false;
    }
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
  try { localStorage.setItem('watchup-view', view); } catch {}
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
  alertsCategoryFilter = button.dataset.filter;
  applyAlertsCategoryFilter();
}));
const sortTrigger = document.querySelector('#group-sort-trigger');
const sortMenu = document.querySelector('#group-sort-menu');
const sortValue = document.querySelector('#group-sort-value');
function closeGroupSort() {
  if (!sortMenu || !sortTrigger) return;
  sortMenu.hidden = true;
  sortTrigger.setAttribute('aria-expanded', 'false');
}
sortTrigger?.addEventListener('click', (event) => {
  event.stopPropagation();
  const open = sortMenu.hidden;
  sortMenu.hidden = !open;
  sortTrigger.setAttribute('aria-expanded', String(open));
});
sortMenu?.querySelectorAll('[role="option"]').forEach((option) => {
  option.addEventListener('click', () => {
    groupSort = option.dataset.value;
    sortMenu.querySelectorAll('[role="option"]').forEach((item) => {
      item.setAttribute('aria-selected', String(item === option));
    });
    if (sortValue) sortValue.textContent = option.textContent;
    closeGroupSort();
    if (groupSort === 'sender') document.querySelector('[data-people-tab="contacts"]')?.click();
    else document.querySelector('[data-people-tab="groups"]')?.click();
    if (lastDashboardData) renderDashboard(lastDashboardData, true);
  });
});
document.addEventListener('click', (event) => {
  if (!event.target.closest('[data-group-sort]')) closeGroupSort();
});
document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape') closeGroupSort();
});
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
function syncMobileNav() {
  if (!mobileMenu) return;
  closeMobileMenu();
}
function closeMobileMenu() {
  if (!mobileMenu) return;
  mobileMenu.hidden = true;
  mobileMenu.classList.remove('open');
  mobileMenuButton?.setAttribute('aria-expanded', 'false');
  mobileMenuButton?.setAttribute('aria-label', 'פתח תפריט');
}
mobileMenuButton?.addEventListener('click', () => {
  const open = mobileMenu.hidden;
  mobileMenu.hidden = !open;
  mobileMenu.classList.toggle('open', open);
  mobileMenuButton.setAttribute('aria-expanded', String(open));
  mobileMenuButton.setAttribute('aria-label', open ? 'סגור תפריט' : 'פתח תפריט');
});
window.addEventListener('resize', () => {
  if (!window.matchMedia('(max-width: 720px)').matches) closeMobileMenu();
});

document.querySelector('#enable-alerts').addEventListener('click', () => {
  alertsEnabled = true;
  try { localStorage.setItem('watchup-alerts', 'on'); } catch {}
  playCriticalTone();
  document.querySelector('#alert-sound-status').textContent = 'הצליל נבדק וההתראות פעילות במכשיר הזה.';
  if ('Notification' in window && Notification.permission === 'default') Notification.requestPermission();
});
document.addEventListener('pointerdown', () => {
  if (!alertsEnabled) return;
  const AudioContext = window.AudioContext || window.webkitAudioContext;
  if (!AudioContext) return;
  const context = playCriticalTone.context || new AudioContext();
  playCriticalTone.context = context;
  if (context.state === 'suspended') context.resume();
}, { once: true });
if (alertsEnabled) document.querySelector('#alert-sound-status').textContent = 'הצליל פעיל במכשיר הזה. געו במסך פעם אחת אחרי רענון כדי לאפשר צליל.';

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
  const username = document.querySelector('#parent-username').value.trim();
  try {
    const response = await fetchWithTimeout('/api/watchup/session', {
      method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password: passwordInput.value }),
    });
    const result = response.ok ? await response.json() : null;
    if (result?.authenticated) {
      parentUsername = username;
      try { localStorage.setItem('watchup-parent', username); } catch {}
      csrfToken = result.csrf_token;
      apiForm.reset();
      document.querySelector('#parent-username').value = 'eldad';
      // Drop the login overlay before the heavy dashboard fetch/render.
      revealAuthenticatedShell();
      setEnvironmentStatus('סביבת POC · טוען נתונים…');
      if ((await loadDashboard(true)) || csrfToken) startPolling();
    } else if (response.status === 429) showLoginError('בוצעו יותר מדי ניסיונות. המתינו כמה דקות ונסו שוב.');
    else if (response.status === 502 || response.status === 503 || response.status === 504) showLoginError('השרת לא ענה. הסיסמה לא נבדקה. נסו שוב בעוד רגע.');
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
  // ponytail: 5s full rebuild froze taps on mid-range phones. 15s is enough for live POC.
  liveRefreshTimer = setInterval(() => loadDashboard(false), 15000);
}
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible' && csrfToken) loadDashboard(false);
});

document.querySelector('#api-disconnect').addEventListener('click', async () => {
  try {
    const response = await fetch('/api/watchup/session', { method: 'DELETE', credentials: 'same-origin', headers: { 'X-WatchUp-CSRF': csrfToken } });
    if (!response.ok) throw new Error('logout failed');
    requireAuthentication('יצאתם מהמערכת בבטחה.');
    announce('יצאתם מהמערכת');
  } catch { announce('היציאה לא בוצעה'); }
});

document.querySelector('#schedule-form')?.addEventListener('submit', async (event) => {
  event.preventDefault();
  const status = document.querySelector('#schedule-status');
  try {
    const next = scheduleFromForm();
    const response = await fetch(`/api/watchup/schedule${childQuery()}`, {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-WatchUp-CSRF': csrfToken },
      body: JSON.stringify({ schedule: next }),
    });
    if (!response.ok) throw new Error('schedule failed');
    const result = await response.json();
    lastDashboardData.schedule = result.schedule;
    scheduleStamp = '';
    renderDashboard(lastDashboardData);
    status.textContent = 'השעות נשמרו.';
  } catch {
    status.textContent = 'כל חלון צריך שעת התחלה ושעת סיום, או להישאר ריק.';
  }
});

const PAIRING_TEXT = {
  connected: () => 'מחובר. לא נוצר קוד חדש.',
  waiting: (name) => `סרקו את הקוד ב־WhatsApp בטלפון של ${name}: מכשירים מקושרים ← קישור מכשיר.`,
  requested: (name) => `מבקשים קוד חיבור לטלפון של ${name}…`,
  bridge_unavailable: (name) => `שירות החיבור של ${name} לא זמין כרגע. אפשר לבטל ולנסות שוב מאוחר יותר.`,
  timeout: () => 'הקוד פג תוקף לפני הסריקה. אפשר לבקש קוד חדש.',
  not_connected: (name) => `הטלפון של ${name} עדיין לא מחובר. אפשר ליצור קוד חיבור.`,
  no_bridge: (name) => `ל־${name} עדיין לא הוגדר חיבור WhatsApp. אפשר לחבר כשיהיה צורך.`,
  unavailable: () => 'אין קוד פעיל. יצירת קוד חדש דורשת אישור, כדי לא לנתק את הטלפון המחובר.',
};

function renderPairing(payload) {
  const state = PAIRING_TEXT[payload.state] ? payload.state : 'unavailable';
  const image = document.querySelector('#pairing-qr');
  document.querySelector('#pairing-status').textContent = PAIRING_TEXT[state](selectedChildName() || 'הילד');
  image.hidden = !(state === 'waiting' && payload.svg);
  if (image.hidden) image.removeAttribute('src'); else image.src = payload.svg;
  // Request and cancel exist only in Multi-Family; the legacy server answers "unavailable".
  document.querySelector('#pairing-request').hidden = !['not_connected', 'timeout'].includes(state);
  document.querySelector('#pairing-cancel').hidden = !['requested', 'waiting', 'bridge_unavailable'].includes(state);
}

async function pairingCall(method = 'GET') {
  const options = { method, credentials: 'same-origin', cache: 'no-store' };
  if (method !== 'GET') options.headers = { 'X-WatchUp-CSRF': csrfToken };
  const response = await fetch(`/api/watchup/pairing${childQuery()}`, options);
  if (!response.ok && response.status !== 409) throw new Error('pairing unavailable');
  renderPairing(await response.json());
}

async function refreshPairing(method) {
  try { await pairingCall(method); } catch { document.querySelector('#pairing-status').textContent = 'לא ניתן להציג את מצב החיבור כרגע.'; }
}

document.querySelector('#open-pairing')?.addEventListener('click', async () => {
  const dialog = document.querySelector('#pairing-dialog');
  document.querySelector('#pairing-status').textContent = 'בודקים את החיבור…';
  document.querySelector('#pairing-qr').hidden = true;
  document.querySelector('#pairing-request').hidden = true;
  document.querySelector('#pairing-cancel').hidden = true;
  dialog.showModal();
  await refreshPairing('GET');
  clearInterval(pairingTimer);
  // QR codes rotate every ~20s on the bridge; poll only while the window is open.
  pairingTimer = setInterval(() => refreshPairing('GET'), 3000);
});
document.querySelector('#pairing-request')?.addEventListener('click', () => refreshPairing('POST'));
document.querySelector('#pairing-cancel')?.addEventListener('click', () => refreshPairing('DELETE'));
document.querySelector('#pairing-dialog')?.addEventListener('close', () => clearInterval(pairingTimer));
document.querySelector('#pairing-close')?.addEventListener('click', () => document.querySelector('#pairing-dialog')?.close());

document.querySelector('#child-select')?.addEventListener('change', (event) => {
  selectedChildId = event.target.value;
  const name = event.target.selectedOptions[0]?.text || '';
  document.querySelector('.child-switch b').textContent = name;
  document.querySelector('.child-avatars i').textContent = name.charAt(0);
  selectedGroupJid = '';
  scheduleStamp = '';
  lastRenderFingerprint = '';
  alertsPrimed = false;
  loadDashboard(true);
});

document.querySelector('#reset-today')?.addEventListener('click', async () => {
  if (!confirm('למחוק אירועים שלפני היום? היום, מילות המעקב וחיבור WhatsApp נשארים.')) return;
  try {
    const response = await fetch(`/api/watchup/today${childQuery()}`, { method: 'POST', credentials: 'same-origin', headers: { 'X-WatchUp-CSRF': csrfToken } });
    if (!response.ok) throw new Error('reset failed');
    await loadDashboard(false);
    announce('נשארו אירועי היום');
  } catch { announce('האיפוס לא בוצע'); }
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

document.querySelector('#privacy-fab')?.addEventListener('click', () => {
  document.querySelector('#privacy-sheet')?.showModal();
});
document.querySelector('#privacy-sheet-close')?.addEventListener('click', () => {
  document.querySelector('#privacy-sheet')?.close();
});

if ('scrollRestoration' in history) history.scrollRestoration = 'manual';
showView('home', true);
const bootWatchdog = setTimeout(() => {
  if (document.body.classList.contains('auth-pending')) {
    requireAuthentication('ההתחברות ארכה יותר מדי. נסו שוב.');
  }
}, 8000);
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
    revealAuthenticatedShell();
    setEnvironmentStatus('סביבת POC · טוען נתונים…');
    if ((await loadDashboard()) || csrfToken) startPolling();
  } catch {
    requireAuthentication('המערכת אינה זמינה כרגע. הנתונים לא הוצגו.');
  } finally {
    clearTimeout(bootWatchdog);
    if (document.body.classList.contains('auth-pending')) requireAuthentication();
  }
}
restoreSession();
