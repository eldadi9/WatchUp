(() => {
  const T = {
    step: 'שלב {x} מתוך 4', s1: 'אישור משפחה', s1t: 'המשפחה שלכם: {family_name}', s2: 'הילדים',
    name: 'שם', age: 'גיל', wa: 'יש לו/לה WhatsApp כרגע', on: 'מחובר', off: 'לא מחובר', add: 'הוספת ילד/ה',
    errName: 'צריך שם באורך 1 עד 40 תווים.', errAge: 'צריך גיל בין 1 ל־18.', errSave: 'השמירה לא הצליחה. נסו שוב.',
    s3: 'מילות מעקב ושעות חריגות', words: 'מילות מעקב (מילה או ביטוי בכל שורה)', study: 'שעות לימודים (א׳–ה׳)',
    evening: 'שעות ערב (א׳–ה׳)', start: 'התחלה', end: 'סיום', note: 'אפשר לדייק שעות לכל יום בנפרד בהגדרות.',
    s4: 'סיכום', yes: 'כן', no: 'לא', wcount: '{n} מילות מעקב', noHours: 'בלי שעות חריגות',
    missing: 'חסר גיל עבור: {names}', back: 'חזרה', next: 'המשך', finish: 'סיום וכניסה ל־WatchUp',
  };
  const WEEKDAYS = ['sun', 'mon', 'tue', 'wed', 'thu'];
  const el = (id) => document.getElementById(id);
  let rows = []; // {id, name, age, wa, connected, words, study, evening, schedule, nameIn, ageIn, waIn, wordsIn, ranges}
  let familyName = '';
  let completed = false;
  let step = 1;
  let started = false;

  function mk(tag, text, cls) {
    const n = document.createElement(tag);
    if (text != null) n.textContent = text;
    if (cls) n.className = cls;
    return n;
  }
  function labeled(label, input) {
    const l = mk('label');
    l.append(mk('span', label), input);
    return l;
  }
  function status(msg) { el('onboarding-status').textContent = msg || ''; }
  function post(path, body) {
    return fetch(path.startsWith('/') ? path : `/api/watchup/${path}`, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-WatchUp-CSRF': csrfToken },
      body: JSON.stringify(body),
    });
  }
  const pair = (s) => (Array.isArray(s) && s.length === 2 ? s : null);

  function toRow(c) {
    const sun = c.schedule?.sun || {};
    return {
      id: c.child_id || '', name: c.name || '', age: c.age ?? '', wa: !!c.has_whatsapp,
      connected: typeof c.connected === 'boolean' ? c.connected : null,
      words: Array.isArray(c.tracking_words) ? c.tracking_words : [],
      schedule: c.schedule || {}, study: pair(sun.study), evening: pair(sun.evening),
    };
  }

  function renderStep1(body) {
    body.append(mk('p', T.s1t.replace('{family_name}', familyName)));
  }

  function renderStep2(body) {
    const list = mk('div');
    const addRow = (r) => {
      const row = mk('div', null, 'ob-row');
      r.nameIn = Object.assign(mk('input'), { type: 'text', maxLength: 40, value: r.name });
      r.nameIn.dir = 'auto';
      r.ageIn = Object.assign(mk('input'), { type: 'number', min: 1, max: 18, value: r.age });
      r.waIn = Object.assign(mk('input'), { type: 'checkbox', checked: r.wa });
      const conn = mk('small', r.connected === null ? '' : r.connected ? T.on : T.off);
      row.append(labeled(T.name, r.nameIn), labeled(T.age, r.ageIn), labeled(T.wa, r.waIn), conn);
      if (!r.id) {
        const rm = mk('button', 'הסרה', 'secondary');
        rm.type = 'button';
        rm.addEventListener('click', () => { rows = rows.filter((x) => x !== r); row.remove(); });
        row.append(rm);
      }
      list.append(row);
    };
    rows.forEach(addRow);
    const add = mk('button', T.add, 'secondary');
    add.type = 'button';
    add.addEventListener('click', () => {
      const r = { id: '', name: '', age: '', wa: false, connected: null, words: [], schedule: {}, study: null, evening: null };
      rows.push(r);
      addRow(r);
    });
    body.append(list, add);
  }

  function rangeInputs(label, value) {
    const wrap = mk('div', null, 'ob-hours');
    const a = Object.assign(mk('input'), { type: 'time', value: value?.[0] || '' });
    const b = Object.assign(mk('input'), { type: 'time', value: value?.[1] || '' });
    wrap.append(mk('span', label), labeled(T.start, a), labeled(T.end, b));
    return { wrap, a, b };
  }

  function renderStep3(body) {
    rows.forEach((r) => {
      const box = mk('section');
      box.append(mk('h3', r.name));
      r.wordsIn = Object.assign(mk('textarea'), { value: r.words.join('\n') });
      r.wordsIn.dir = 'auto';
      r.studyIn = rangeInputs(T.study, r.study);
      r.eveningIn = rangeInputs(T.evening, r.evening);
      box.append(labeled(T.words, r.wordsIn), r.studyIn.wrap, r.eveningIn.wrap);
      body.append(box);
    });
    body.append(mk('p', T.note, 'settings-note'));
  }

  const readPair = (x) => (x.a.value && x.b.value ? [x.a.value, x.b.value] : null);
  function readStep3() {
    rows.forEach((r) => {
      r.words = r.wordsIn.value.split('\n').map((w) => w.trim()).filter(Boolean).slice(0, 30).map((w) => w.slice(0, 40));
      r.study = readPair(r.studyIn);
      r.evening = readPair(r.eveningIn);
    });
  }

  function renderStep4(body) {
    rows.forEach((r) => {
      const hours = [r.study && `${r.study[0]}–${r.study[1]}`, r.evening && `${r.evening[0]}–${r.evening[1]}`].filter(Boolean);
      const box = mk('section');
      box.append(
        mk('h3', r.name),
        mk('p', `${T.age}: ${r.age} · WhatsApp: ${r.wa ? T.yes : T.no} · ${r.connected ? T.on : T.off}`),
        mk('p', T.wcount.replace('{n}', r.words.length)),
        mk('p', hours.length ? hours.join(' · ') : T.noHours),
      );
      body.append(box);
    });
  }

  function render() {
    const body = el('onboarding-body');
    body.replaceChildren();
    [renderStep1, renderStep2, renderStep3, renderStep4][step - 1](body);
    el('onboarding-title').textContent = 'הגדרת המשפחה';
    el('onboarding-step').textContent = `${T.step.replace('{x}', step)} · ${[T.s1, T.s2, T.s3, T.s4][step - 1]}`;
    el('onboarding-back').hidden = step === 1;
    el('onboarding-next').textContent = step === 4 ? T.finish : T.next;
    const close = el('onboarding-close');
    close.hidden = !completed;
    close.textContent = 'סגירה';
    el('onboarding-back').textContent = T.back;
    status('');
  }

  function readStep2() {
    rows.forEach((r) => {
      r.name = r.nameIn.value.trim();
      r.age = r.ageIn.value;
      r.wa = r.waIn.checked;
    });
  }

  async function saveStep2() {
    readStep2();
    for (const r of rows) {
      if (!r.name || r.name.length > 40) return status(T.errName), false;
      const age = Number(r.age);
      if (!Number.isInteger(age) || age < 1 || age > 18) return status(T.errAge), false;
    }
    for (const r of rows) {
      const res = await post(r.id ? `/api/watchup/children?child_id=${encodeURIComponent(r.id)}` : '/api/watchup/children',
        { display_name: r.name, age: Number(r.age), has_whatsapp: r.wa });
      if (!res.ok) return status(T.errSave), false;
      const child = await res.json();
      r.id = child.child_id || r.id;
      if (typeof child.connected === 'boolean') r.connected = child.connected;
    }
    return true;
  }

  async function saveStep3() {
    readStep3();
    for (const r of rows) {
      const q = `?child_id=${encodeURIComponent(r.id)}`;
      const schedule = {};
      ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat'].forEach((d) => {
        schedule[d] = WEEKDAYS.includes(d) ? { study: r.study, evening: r.evening } : (r.schedule[d] || { study: null, evening: null });
      });
      const a = await post(`tracking-words${q}`, { words: r.words });
      const b = await post(`schedule${q}`, { schedule });
      if (!a.ok || !b.ok) return status(T.errSave), false;
    }
    return true;
  }

  async function finish() {
    const res = await post('onboarding', {});
    if (res.ok) {
      completed = true;
      el('onboarding-dialog').close();
      lastRenderFingerprint = '';
      scheduleStamp = '';
      loadDashboard();
      return;
    }
    if (res.status === 409) {
      const missing = (await res.json().catch(() => ({}))).missing || [];
      const names = rows.filter((r) => missing.includes(r.id)).map((r) => r.name).join(', ');
      step = 2;
      render();
      status(T.missing.replace('{names}', names));
      return;
    }
    status(T.errSave);
  }

  let saving = false;
  const lock = (on) => ['back', 'next'].forEach((k) => { el(`onboarding-${k}`).disabled = on; });
  async function next() {
    if (saving) return;
    saving = true;
    lock(true);
    if (step >= 2) status('שומרים…');
    try {
      if (step === 4) return await finish();
      if (step === 2 && !(await saveStep2())) return;
      if (step === 3 && !(await saveStep3())) return;
      step += 1;
      render();
    } catch {
      status(T.errSave);
    } finally {
      saving = false;
      lock(false);
    }
  }

  async function openOnboarding() {
    let data;
    try {
      const res = await fetch('/api/watchup/onboarding', { credentials: 'same-origin' });
      if (!res.ok) return;
      data = await res.json();
    } catch { return; }
    completed = !!data.completed;
    familyName = data.family_name || '';
    rows = (data.children || []).map(toRow);
    step = 1;
    render();
    const d = el('onboarding-dialog');
    if (!d.open) d.showModal();
  }

  function maybeStartOnboarding(data) {
    if (data?.onboarding_completed !== false || started || el('onboarding-dialog').open) return;
    started = true;
    openOnboarding();
  }

  const dlg = el('onboarding-dialog');
  dlg.addEventListener('cancel', (e) => { if (!completed) e.preventDefault(); });
  el('onboarding-next').addEventListener('click', next);
  el('onboarding-back').addEventListener('click', () => { if (step > 1) { step -= 1; render(); } });
  el('onboarding-close').addEventListener('click', () => dlg.close());
  el('open-onboarding')?.addEventListener('click', openOnboarding);
  window.maybeStartOnboarding = maybeStartOnboarding;
  window.openOnboarding = openOnboarding;
  if (typeof lastDashboardData !== 'undefined' && lastDashboardData) maybeStartOnboarding(lastDashboardData);
})();
