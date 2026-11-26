const API_ROOT = '/api';
const screen = document.querySelector('#screen');
const dialog = document.querySelector('#dialog');
const dialogContent = document.querySelector('#dialog-content');
const toastNode = document.querySelector('#toast');
const connectionNode = document.querySelector('#connection');

const state = {
  current: 'home',
  councilTab: 'councils',
  candidateQuery: '',
  installPrompt: null,
};

const titles = {
  home: 'Обзор',
  councils: 'Советы',
  candidates: 'Соискатели',
  dissertations: 'Дела',
  meetings: 'Заседания',
};

const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
}[char]));

function showToast(message, isError = false) {
  toastNode.textContent = message;
  toastNode.classList.toggle('error', isError);
  toastNode.classList.add('show');
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => toastNode.classList.remove('show'), 3000);
}

function setConnection(online) {
  connectionNode.classList.toggle('online', online);
  connectionNode.classList.toggle('offline', !online);
  connectionNode.querySelector('span').textContent = online ? 'Сервер доступен' : 'Нет связи с сервером';
}

async function api(path, options = {}) {
  const response = await fetch(`${API_ROOT}${path}`, {
    ...options,
    headers: { ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...options.headers },
  });
  setConnection(true);
  if (response.status === 204) return null;
  const text = await response.text();
  const body = text ? JSON.parse(text) : null;
  if (!response.ok) {
    const detail = body?.detail;
    throw new Error(Array.isArray(detail) ? detail.map(item => item.msg).join(', ') : detail || `Ошибка ${response.status}`);
  }
  return body;
}

const loading = `<div class="loading">Загружаем данные…</div>`;
const empty = message => `<div class="empty">${esc(message)}</div>`;
const errorBox = error => `<div class="error-box"><strong>Не удалось загрузить раздел</strong><div>${esc(error.message)}</div><button class="button secondary" data-action="retry">Попробовать ещё раз</button></div>`;

function statusPill(value) {
  const labels = {
    active: ['Действующий', 'teal'], planned: ['Запланировано', 'gold'], held: ['Состоялось', 'teal'],
    submitted: ['Подано', 'gold'], scheduled: ['Назначено', 'teal'], defended: ['Защищено', 'teal'],
    rejected: ['Отклонено', 'red'], granted: ['Присуждено', 'teal'], denied: ['Отказано', 'red'],
  };
  const [label, color] = labels[value] || [value || '—', ''];
  return `<span class="pill ${color}">${esc(label)}</span>`;
}

function dateParts(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return { day: '—', month: '—', rest: esc(value) };
  return {
    day: date.toLocaleDateString('ru-RU', { day: '2-digit' }),
    month: date.toLocaleDateString('ru-RU', { month: 'short' }).replace('.', ''),
    rest: date.toLocaleString('ru-RU', { dateStyle: 'medium', timeStyle: 'short' }),
  };
}

function updateNavigation() {
  document.querySelectorAll('.nav-item').forEach(button => {
    button.classList.toggle('active', button.dataset.screen === state.current);
  });
}

async function render() {
  updateNavigation();
  screen.innerHTML = loading;
  try {
    if (state.current === 'home') return await renderHome();
    if (state.current === 'councils') return await renderCouncils();
    if (state.current === 'candidates') return await renderCandidates();
    if (state.current === 'dissertations') return await renderDissertations();
    if (state.current === 'meetings') return await renderMeetings();
  } catch (error) {
    setConnection(false);
    screen.innerHTML = errorBox(error);
  }
}

async function renderHome() {
  const [councils, candidates, dissertations, meetings] = await Promise.all([
    api('/councils'), api('/candidates'), api('/dissertations'), api('/meetings'),
  ]);
  const upcoming = [...meetings].sort((a, b) => new Date(a.meeting_date) - new Date(b.meeting_date)).find(item => item.status === 'planned');
  const upcomingDate = upcoming ? dateParts(upcoming.meeting_date) : null;
  screen.innerHTML = `
    <section class="hero">
      <p class="eyebrow">АРМ · мобильная версия</p>
      <p class="hero-date">${esc(new Date().toLocaleDateString('ru-RU', { weekday: 'long', day: 'numeric', month: 'long' }))}</p>
      <h1>Работа совета —<br>в одном месте</h1>
      <p>Состав, соискатели, диссертационные дела и заседания доступны с телефона.</p>
    </section>
    <section class="stats-grid" aria-label="Сводка системы">
      ${statCard('Советы', councils.length, '♙', 'в системе')}
      ${statCard('Соискатели', candidates.length, '◎', 'зарегистрировано')}
      ${statCard('Диссертационные дела', dissertations.length, '▤', 'в работе')}
      ${statCard('Заседания', meetings.length, '▦', 'всего')}
    </section>
    <div class="section-heading"><h2>Ближайшее заседание</h2><span class="muted">по плану системы</span></div>
    ${upcoming ? `<article class="record-card"><div class="record-main"><div class="record-leading"><div class="meeting-date"><strong>${upcomingDate.day}</strong><span>${upcomingDate.month}</span></div><div><p class="record-title">${esc(upcomingDate.rest)}</p><p class="record-subtitle">${esc(upcoming.status === 'planned' ? 'Ожидает проведения' : upcoming.status)}</p></div></div>${statusPill(upcoming.status)}</div><div class="card-actions"><button class="button ghost" data-action="open-meeting" data-id="${upcoming.meeting_id}">Открыть заседание</button></div></article>` : empty('Запланированных заседаний пока нет.')}
    <div class="notice"><span>ⓘ</span><span>Демо-версия подключается к локальному API. Для работы с данными сервер должен быть запущен.</span></div>`;
}

function statCard(label, value, icon, note) {
  return `<article class="stat-card"><div class="stat-top"><span>${esc(label)}</span><span class="stat-icon">${icon}</span></div><div class="stat-value">${value}</div><div class="stat-note">${esc(note)}</div></article>`;
}

async function renderCouncils() {
  const [councils, members] = await Promise.all([api('/councils'), api('/members')]);
  const list = state.councilTab === 'councils' ? councils : members;
  screen.innerHTML = `
    <p class="eyebrow">Структура</p><div class="toolbar"><h1>Советы</h1><span class="pill">${list.length} записей</span></div>
    <div class="section-tabs"><button class="section-tab ${state.councilTab === 'councils' ? 'active' : ''}" data-action="council-tab" data-tab="councils">Советы · ${councils.length}</button><button class="section-tab ${state.councilTab === 'members' ? 'active' : ''}" data-action="council-tab" data-tab="members">Члены · ${members.length}</button></div>
    <div class="card-list">${list.length ? list.map(item => state.councilTab === 'councils' ? `
      <article class="record-card"><div class="record-main"><div><p class="record-title">${esc(item.name)}</p><p class="record-subtitle">${esc(item.number)} · ${esc(item.department)}</p></div>${statusPill(item.status)}</div><div class="card-actions"><button class="button ghost" data-action="show-council-members" data-id="${item.council_id}">Показать состав</button></div></article>` : `
      <article class="record-card"><div class="record-main"><div><p class="record-title">${esc(item.full_name)}</p><p class="record-subtitle">${esc(item.academic_title || 'Член совета')}</p></div><span class="pill teal">${item.degree === 'doctor' ? 'Доктор наук' : 'Кандидат наук'}</span></div></article>`).join('') : empty('В этом разделе пока нет записей.')}</div>`;
}

async function renderCandidates() {
  const [candidates, specialties] = await Promise.all([api('/candidates'), api('/specialties')]);
  const query = state.candidateQuery.trim().toLocaleLowerCase('ru');
  const filtered = candidates.filter(item => `${item.full_name} ${item.contact_info || ''}`.toLocaleLowerCase('ru').includes(query));
  screen.innerHTML = `
    <p class="eyebrow">Люди и заявки</p>
    <div class="toolbar"><h1>Соискатели</h1><button class="button" data-action="add-candidate">＋ Добавить</button></div>
    <label class="search"><input id="candidate-search" type="search" placeholder="Поиск по имени или контакту" value="${esc(state.candidateQuery)}" autocomplete="off"></label>
    <div class="card-list">${filtered.length ? filtered.map(item => `
      <article class="record-card"><div class="record-main"><div><p class="record-title">${esc(item.full_name)}</p><p class="record-subtitle">${esc(specialtyName(specialties, item.specialty_id))}</p></div><span class="pill">${item.degree_sought === 'doctor' ? 'Доктор наук' : 'Кандидат наук'}</span></div>
        ${item.contact_info ? `<div class="record-meta"><span class="record-subtitle">${esc(item.contact_info)}</span></div>` : ''}
        <div class="card-actions"><button class="button ghost" data-action="edit-candidate" data-id="${item.candidate_id}">Изменить</button><button class="button ghost danger" data-action="delete-candidate" data-id="${item.candidate_id}">Удалить</button></div></article>`).join('') : empty(query ? 'Ничего не найдено. Попробуйте другой запрос.' : 'Соискателей пока нет.')}</div>`;
}

async function renderDissertations() {
  const [items, candidates, councils, specialties] = await Promise.all([
    api('/dissertations'), api('/candidates'), api('/councils'), api('/specialties'),
  ]);
  const sorted = [...items].sort((a, b) => new Date(b.submitted_at) - new Date(a.submitted_at));
  screen.innerHTML = `
    <p class="eyebrow">Диссертационный совет</p>
    <div class="toolbar"><h1>Диссертационные дела</h1><button class="button" data-action="add-dissertation">＋ Новое</button></div>
    <div class="card-list">${sorted.length ? sorted.map(item => `
      <article class="record-card"><div class="record-main"><div><p class="record-title">${esc(item.topic)}</p><p class="record-subtitle">${esc(candidateName(candidates, item.candidate_id))}</p></div>${statusPill(item.status)}</div>
        <div class="record-meta"><span class="pill">${esc(specialtyName(specialties, item.specialty_id))}</span><span class="record-subtitle">${esc(councilName(councils, item.council_id))}</span></div>
        <div class="divider"></div><p class="record-subtitle">Подано ${esc(new Date(item.submitted_at).toLocaleDateString('ru-RU'))}</p></article>`).join('') : empty('Диссертационных дел пока нет.')}</div>`;
}

async function renderMeetings() {
  const [meetings, councils] = await Promise.all([api('/meetings'), api('/councils')]);
  const sorted = [...meetings].sort((a, b) => new Date(b.meeting_date) - new Date(a.meeting_date));
  screen.innerHTML = `
    <p class="eyebrow">Организационная работа</p><div class="toolbar"><h1>Заседания</h1><span class="pill">${meetings.length} всего</span></div>
    <div class="card-list">${sorted.length ? sorted.map(item => {
      const parts = dateParts(item.meeting_date);
      return `<article class="record-card"><div class="record-main"><div class="record-leading"><div class="meeting-date"><strong>${parts.day}</strong><span>${parts.month}</span></div><div><p class="record-title">${esc(councilName(councils, item.council_id))}</p><p class="record-subtitle">${esc(parts.rest)}</p></div></div>${statusPill(item.status)}</div>
        <div class="card-actions"><button class="button ghost" data-action="quorum" data-id="${item.meeting_id}">Проверить кворум</button>${item.status === 'planned' ? `<button class="button ghost" data-action="attendance" data-id="${item.meeting_id}" data-council="${item.council_id}">Отметить явку</button>` : ''}</div>
        <div id="quorum-${item.meeting_id}"></div></article>`;
    }).join('') : empty('Заседаний пока нет.')}</div>
    <div class="notice"><span>ⓘ</span><span>Кворум проверяется по составу совета, явке и профильным докторам наук.</span></div>`;
}

function specialtyName(rows, id) { return rows.find(item => item.specialty_id === id)?.name || 'Специальность не указана'; }
function candidateName(rows, id) { return rows.find(item => item.candidate_id === id)?.full_name || `Соискатель №${id}`; }
function councilName(rows, id) { const item = rows.find(row => row.council_id === id); return item ? `${item.number} · ${item.name}` : `Совет №${id}`; }

function openDialog(title, subtitle, body, formId) {
  dialogContent.innerHTML = `<div class="dialog-inner"><div class="dialog-header"><div><p class="eyebrow">${esc(title)}</p><h2>${esc(subtitle)}</h2></div><button class="icon-button" type="button" data-action="close-dialog" aria-label="Закрыть">×</button></div>${body}</div>`;
  dialog.showModal();
  if (formId) dialogContent.querySelector(`#${formId} input, #${formId} select`)?.focus();
}

function candidateForm(item, specialties) {
  const editing = Boolean(item);
  const specialtyOptions = specialties.map(row => `<option value="${row.specialty_id}" ${item?.specialty_id === row.specialty_id ? 'selected' : ''}>${esc(row.code)} — ${esc(row.name)}</option>`).join('');
  openDialog(editing ? 'Карточка соискателя' : 'Новая запись', editing ? 'Изменить соискателя' : 'Добавить соискателя', `
    <form id="candidate-form" data-id="${item?.candidate_id || ''}">
      <div class="field"><label for="candidate-name">ФИО *</label><input id="candidate-name" name="full_name" minlength="3" maxlength="200" required value="${esc(item?.full_name || '')}" placeholder="Например, Иванов Иван Иванович"></div>
      <div class="form-grid"><div class="field"><label for="candidate-degree">Искомая степень</label><select id="candidate-degree" name="degree_sought"><option value="candidate" ${!item || item.degree_sought === 'candidate' ? 'selected' : ''}>Кандидат наук</option><option value="doctor" ${item?.degree_sought === 'doctor' ? 'selected' : ''}>Доктор наук</option></select></div>
      <div class="field"><label for="candidate-specialty">Специальность *</label><select id="candidate-specialty" name="specialty_id" required>${specialtyOptions}</select></div></div>
      <div class="field"><label for="candidate-contact">Контакт</label><input id="candidate-contact" name="contact_info" maxlength="240" value="${esc(item?.contact_info || '')}" placeholder="Телефон или электронная почта"></div>
      <p class="error-text" id="form-error" hidden></p><div class="dialog-actions"><button class="button secondary" type="button" data-action="close-dialog">Отмена</button><button class="button" type="submit">${editing ? 'Сохранить' : 'Добавить'}</button></div>
    </form>`, 'candidate-form');
}

async function openCandidateForm(candidateId = null) {
  try {
    const [specialties, item] = await Promise.all([
      api('/specialties'), candidateId ? api(`/candidates/${candidateId}`) : Promise.resolve(null),
    ]);
    if (!specialties.length) return showToast('Сначала добавьте специальность в справочник', true);
    candidateForm(item, specialties);
  } catch (error) { showToast(error.message, true); }
}

async function openDissertationForm() {
  try {
    const [candidates, councils, specialties] = await Promise.all([api('/candidates'), api('/councils'), api('/specialties')]);
    if (!candidates.length || !councils.length || !specialties.length) return showToast('Нужны соискатель, совет и специальность', true);
    openDialog('Новое дело', 'Зарегистрировать диссертацию', `
      <form id="dissertation-form">
        <div class="field"><label for="dissertation-topic">Тема диссертации *</label><textarea id="dissertation-topic" name="topic" minlength="8" maxlength="500" required placeholder="Полная формулировка темы"></textarea></div>
        <div class="field"><label for="dissertation-candidate">Соискатель *</label><select id="dissertation-candidate" name="candidate_id" required>${candidates.map(x => `<option value="${x.candidate_id}">${esc(x.full_name)}</option>`).join('')}</select></div>
        <div class="field"><label for="dissertation-council">Совет *</label><select id="dissertation-council" name="council_id" required>${councils.map(x => `<option value="${x.council_id}">${esc(x.number)} — ${esc(x.name)}</option>`).join('')}</select></div>
        <div class="field"><label for="dissertation-specialty">Специальность *</label><select id="dissertation-specialty" name="specialty_id" required>${specialties.map(x => `<option value="${x.specialty_id}">${esc(x.code)} — ${esc(x.name)}</option>`).join('')}</select></div>
        <div class="field"><label for="dissertation-date">Дата подачи</label><input id="dissertation-date" name="submitted_at" type="date" value="${new Date().toISOString().slice(0, 10)}" required></div>
        <p class="error-text" id="form-error" hidden></p><div class="dialog-actions"><button class="button secondary" type="button" data-action="close-dialog">Отмена</button><button class="button" type="submit">Зарегистрировать</button></div>
      </form>`, 'dissertation-form');
  } catch (error) { showToast(error.message, true); }
}

async function openAttendanceForm(meetingId, councilId) {
  try {
    const members = await api(`/councils/${councilId}/members`);
    if (!members.length) return showToast('В составе совета нет участников', true);
    openDialog('Заседание', 'Отметить присутствующих', `
      <form id="attendance-form" data-id="${meetingId}">
        <p class="lede">Отметьте членов совета, которые присутствуют на заседании.</p>
        <div class="attendance-list">${members.map(member => `<label class="check-row"><input type="checkbox" name="member_id" value="${member.member_id}"><span>${esc(member.full_name)} <span class="muted">· ${member.degree === 'doctor' ? 'доктор наук' : 'кандидат наук'}</span></span></label>`).join('')}</div>
        <p class="error-text" id="form-error" hidden></p><div class="dialog-actions"><button class="button secondary" type="button" data-action="close-dialog">Отмена</button><button class="button" type="submit">Сохранить явку</button></div>
      </form>`);
  } catch (error) { showToast(error.message, true); }
}

async function showQuorum(meetingId) {
  const target = document.querySelector(`#quorum-${meetingId}`);
  if (!target) return;
  target.innerHTML = `<div class="loading">Проверяем состав и явку…</div>`;
  try {
    const result = await api(`/meetings/${meetingId}/quorum`);
    target.innerHTML = `<div class="quorum-box ${result.quorum_met ? 'pass' : 'fail'}"><strong>${result.quorum_met ? 'Кворум есть' : 'Кворума нет'}</strong><p>Присутствуют ${result.present_count} из ${result.council_size}; требуется ${result.required_count}. Профильных докторов: ${result.profile_doctors_present} из 3.</p>${result.reasons?.length ? `<p>${esc(result.reasons.join('. '))}</p>` : ''}</div>`;
  } catch (error) { target.innerHTML = `<div class="error-box">${esc(error.message)}</div>`; }
}

async function handleClick(event) {
  const nav = event.target.closest('[data-screen]');
  if (nav) { state.current = nav.dataset.screen; state.candidateQuery = ''; return render(); }
  const button = event.target.closest('[data-action]');
  if (!button) return;
  const { action, id } = button.dataset;
  if (action === 'close-dialog') return dialog.close();
  if (action === 'retry') return render();
  if (action === 'council-tab') { state.councilTab = button.dataset.tab; return renderCouncils(); }
  if (action === 'add-candidate') return openCandidateForm();
  if (action === 'edit-candidate') return openCandidateForm(id);
  if (action === 'add-dissertation') return openDissertationForm();
  if (action === 'quorum') return showQuorum(id);
  if (action === 'attendance') return openAttendanceForm(id, button.dataset.council);
  if (action === 'show-council-members') {
    state.current = 'councils'; state.councilTab = 'members'; return render();
  }
  if (action === 'open-meeting') { state.current = 'meetings'; await render(); return showQuorum(id); }
  if (action === 'delete-candidate') {
    if (!confirm('Удалить карточку соискателя?')) return;
    try { await api(`/candidates/${id}`, { method: 'DELETE' }); showToast('Карточка удалена'); await renderCandidates(); }
    catch (error) { showToast(error.message, true); }
  }
}

async function handleSubmit(event) {
  const form = event.target;
  if (form.id === 'candidate-form') {
    event.preventDefault();
    const values = new FormData(form);
    const payload = {
      full_name: String(values.get('full_name')).trim(),
      degree_sought: values.get('degree_sought'),
      specialty_id: Number(values.get('specialty_id')),
      contact_info: String(values.get('contact_info') || '').trim() || null,
    };
    try {
      await api(form.dataset.id ? `/candidates/${form.dataset.id}` : '/candidates', {
        method: form.dataset.id ? 'PUT' : 'POST', body: JSON.stringify(payload),
      });
      dialog.close(); showToast(form.dataset.id ? 'Изменения сохранены' : 'Соискатель добавлен'); await renderCandidates();
    } catch (error) { setFormError(error.message); }
  }
  if (form.id === 'dissertation-form') {
    event.preventDefault();
    const values = new FormData(form);
    const payload = {
      topic: String(values.get('topic')).trim(),
      candidate_id: Number(values.get('candidate_id')),
      council_id: Number(values.get('council_id')),
      specialty_id: Number(values.get('specialty_id')),
      submitted_at: values.get('submitted_at'),
    };
    try {
      await api('/dissertations', { method: 'POST', body: JSON.stringify(payload) });
      dialog.close(); showToast('Диссертационное дело создано'); state.current = 'dissertations'; await render();
    } catch (error) { setFormError(error.message); }
  }
  if (form.id === 'attendance-form') {
    event.preventDefault();
    const presentMemberIds = [...form.querySelectorAll('input[name="member_id"]:checked')].map(input => Number(input.value));
    try {
      const result = await api(`/meetings/${form.dataset.id}/attendance`, { method: 'PUT', body: JSON.stringify({ present_member_ids: presentMemberIds }) });
      dialog.close(); await renderMeetings();
      showToast(result.quorum_met ? 'Явка сохранена · кворум есть' : 'Явка сохранена · кворума нет');
      await showQuorum(form.dataset.id);
    } catch (error) { setFormError(error.message); }
  }
}

function setFormError(message) {
  const node = document.querySelector('#form-error');
  if (!node) return showToast(message, true);
  node.textContent = message;
  node.hidden = false;
}

document.addEventListener('click', event => { handleClick(event); });
document.addEventListener('submit', event => { handleSubmit(event); });
screen.addEventListener('input', event => {
  if (event.target.id !== 'candidate-search') return;
  state.candidateQuery = event.target.value;
  const cursor = event.target.selectionStart;
  renderCandidates().then(() => {
    const input = document.querySelector('#candidate-search');
    input?.focus(); input?.setSelectionRange(cursor, cursor);
  });
});
dialog.addEventListener('click', event => { if (event.target === dialog) dialog.close(); });

window.addEventListener('beforeinstallprompt', event => {
  event.preventDefault();
  state.installPrompt = event;
});

if ('serviceWorker' in navigator) navigator.serviceWorker.register('./sw.js').catch(() => {});
render();
