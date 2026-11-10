'use strict';
(() => {
  const $ = (id) => document.getElementById(id);
  const state = { actor: null, csrf: '', configured: false, dashboard: null, administration: null, view: 'records', epoch: 0, loads: {} };
  const roles = { student: 'Student', professor: 'Professor', admin: 'Administrator' };
  const text = (element, value) => { element.textContent = value == null ? '' : String(value); };
  const node = (tag, value, className) => { const el = document.createElement(tag); if (value != null) text(el, value); if (className) el.className = className; return el; };
  function message(element, value, error = false) { text(element, value); element.classList.toggle('is-error', error); element.classList.toggle('is-success', !error && Boolean(value)); }
  function notice(value, error = false) { message($('global-message'), value, error); $('global-message').hidden = !value; }
  function showTop(view) { ['loading', 'setup', 'auth', 'dashboard'].forEach((name) => { $(`${name}-view`).hidden = name !== view; }); }
  function clearPrivateData() {
    state.epoch += 1; state.actor = null; state.dashboard = null; state.administration = null;
    ['records-body', 'record-summary', 'accounts-body', 'assignment-list', 'enrollment-list', 'audit-body'].forEach((id) => $(id).replaceChildren());
    ['role-user', 'assignment-user', 'assignment-course', 'enrollment-student', 'enrollment-course', 'course-filter'].forEach((id) => $(id).replaceChildren());
    ['actor-name', 'actor-role', 'actor-email', 'records-state', 'admin-state', 'audit-state', 'grade-message'].forEach((id) => text($(id), ''));
    document.querySelectorAll('#dashboard-view .form-message').forEach((el) => message(el, ''));
    $('admin-content').hidden = true;
  }
  class ApiError extends Error { constructor(message, status) { super(message); this.status = status; } }
  async function api(path, body) {
    let response;
    try {
      response = await fetch(`/api/portal${path}`, { method: body === undefined ? 'GET' : 'POST', credentials: 'same-origin', cache: 'no-store', headers: body === undefined ? { Accept: 'application/json' } : { Accept: 'application/json', 'Content-Type': 'application/json', 'X-CSRF-Token': state.csrf }, ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
    } catch (_) { throw new ApiError('The server couldn’t be reached. Check your connection and try again.', 0); }
    let data;
    try { data = await response.json(); } catch (_) { throw new ApiError('The server returned an unreadable response. Please try again.', response.status); }
    if (!response.ok) {
      if (response.status === 401 && state.actor && !['/signin', '/signup'].includes(path)) {
        clearPrivateData(); showTop('auth'); notice('Your session has ended. Sign in again to continue.', true);
      }
      throw new ApiError(typeof data.error === 'string' ? data.error : 'This request couldn’t be completed.', response.status);
    }
    return data;
  }
  function authTab(name, focus = false) {
    ['signin', 'signup'].forEach((value) => {
      const active = name === value;
      $(`${value}-panel`).hidden = !active;
      $(`${value}-tab`).setAttribute('aria-selected', String(active));
      $(`${value}-tab`).tabIndex = active ? 0 : -1;
    });
    if (focus) $(`${name}-tab`).focus();
  }
  ['signin', 'signup'].forEach((name) => {
    const tab = $(`${name}-tab`);
    tab.addEventListener('click', () => authTab(name));
    tab.addEventListener('keydown', (event) => {
      if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) {
        event.preventDefault(); authTab(event.key === 'Home' ? 'signin' : event.key === 'End' ? 'signup' : name === 'signin' ? 'signup' : 'signin', true);
      }
    });
    $(`${name}-form`).addEventListener('submit', async (event) => {
      event.preventDefault();
      const form = event.currentTarget;
      if (form.dataset.busy || !form.reportValidity()) return;
      const values = Object.fromEntries(new FormData(form));
      values.email = values.email.trim(); if (values.name) values.name = values.name.trim();
      await busyForm(form, async () => {
        message(form.querySelector('.form-message'), name === 'signin' ? 'Signing in…' : 'Creating your student account…');
        try {
          const data = await api(`/${name}`, values);
          if (!data.actor || !data.csrfToken) throw new ApiError('The server returned an incomplete session. Please try again.', 502);
          clearPrivateData(); state.actor = data.actor; state.csrf = data.csrfToken; form.reset();
          message(form.querySelector('.form-message'), ''); notice(''); await enterDashboard();
        } catch (error) {
          message(form.querySelector('.form-message'), name === 'signin' && [400, 401, 403].includes(error.status) ? 'Sign-in failed. Check your email and password, then try again.' : error.message, true);
        }
      });
    });
  });
  async function busyForm(form, action) {
    form.dataset.busy = 'true'; form.setAttribute('aria-busy', 'true');
    const controls = Array.from(form.querySelectorAll('button,input,select')); const disabled = controls.map((el) => el.disabled);
    controls.forEach((el) => { el.disabled = true; });
    try { await action(); } finally { controls.forEach((el, i) => { el.disabled = disabled[i]; }); delete form.dataset.busy; form.removeAttribute('aria-busy'); }
  }
  async function loadSession() {
    showTop('loading'); notice('');
    text($('loading-view').querySelector('p'), 'Checking your session…');
    text($('setup-view').querySelector('h1'), 'The portal isn’t connected yet.');
    text($('setup-view').querySelector('p'), 'Account access needs a configured database. Sign-in and account creation will be available once the server setup is complete.');
    try {
      const data = await api('/session');
      clearPrivateData(); state.csrf = data.csrfToken || ''; state.configured = data.configured === true;
      if (!state.configured) { showTop('setup'); return; }
      if (!state.csrf) throw new Error('A secure session could not be started. Please try again.');
      if (data.actor) { state.actor = data.actor; await enterDashboard(); } else { showTop('auth'); }
    } catch (error) { showTop('loading'); notice(error.message, true); text($('loading-view').querySelector('p'), 'Session check failed. Use “Check connection again” below to retry.'); $('setup-view').hidden = false; $('setup-view').querySelector('h1').textContent = 'We couldn’t check the connection.'; $('setup-view').querySelector('p').textContent = 'No account changes have been made. Try the connection again, or return to the lab.'; }
  }
  function applyActor(actor) {
    text($('actor-name'), actor.name); text($('actor-email'), actor.email); text($('actor-role'), roles[actor.role] || actor.role);
  }
  async function enterDashboard() {
    state.view = 'records'; applyActor(state.actor); showTop('dashboard');
    document.querySelectorAll('[data-view]').forEach((button) => { button.hidden = button.dataset.view !== 'records'; });
    switchView('records', false); await loadDashboard();
  }
  function permitted(view) {
    const caps = state.dashboard && state.dashboard.capabilities;
    return view === 'records' || Boolean(caps && (view === 'administration' ? caps.administer : caps.readAudit));
  }
  function switchView(view, load = true) {
    if (!permitted(view)) return;
    state.view = view;
    ['records', 'administration', 'audit'].forEach((name) => { $(`${name}-view`).hidden = name !== view; });
    document.querySelectorAll('[data-view]').forEach((button) => { if (button.dataset.view === view) button.setAttribute('aria-current', 'page'); else button.removeAttribute('aria-current'); });
    if (load && view === 'administration') loadAdministration();
    if (load && view === 'audit') loadAudit();
  }
  document.querySelectorAll('[data-view]').forEach((button) => button.addEventListener('click', () => switchView(button.dataset.view)));
  function startLoad(name) { const id = (state.loads[name] || 0) + 1; state.loads[name] = id; const epoch = state.epoch; return () => state.epoch === epoch && state.loads[name] === id && Boolean(state.actor); }
  async function loadDashboard() {
    const current = startLoad('dashboard');
    text($('records-state'), 'Loading academic records…'); $('records-body').replaceChildren(); $('record-summary').replaceChildren();
    try {
      const data = await api('/dashboard'); if (!current()) return;
      if (!data.actor || !Array.isArray(data.rows) || !Array.isArray(data.courses) || !data.capabilities) throw new Error('The server returned incomplete academic records.');
      state.dashboard = data; state.actor = data.actor; applyActor(data.actor);
      const caps = data.capabilities;
      document.querySelector('[data-view="administration"]').hidden = !caps.administer;
      document.querySelector('[data-view="audit"]').hidden = !caps.readAudit;
      if (!permitted(state.view)) switchView('records', false);
      text($('records-title'), data.actor.role === 'student' ? 'Your records.' : 'Academic records.');
      text($('records-description'), data.actor.role === 'student' ? 'Your enrolled courses and recorded grades, in one place.' : caps.manageGrades ? 'Review course records and save grades where your account has permission.' : 'Review the academic records available to your account.');
      const previous = $('course-filter').value; fillSelect($('course-filter'), data.courses.map((c) => [c.id, `${c.code} · ${c.title}`]), 'All courses', false); if (data.courses.some((c) => String(c.id) === previous)) $('course-filter').value = previous;
      const graded = data.rows.filter((row) => typeof row.grade === 'number');
      [['Courses', data.courses.length], ['Recorded grades', graded.length], ['Awaiting a grade', data.rows.length - graded.length]].forEach(([label, count]) => { const item = node('div', null, 'summary-item'); item.append(node('span', label), node('strong', count)); $('record-summary').append(item); });
      renderRows();
    } catch (error) { if (current()) { state.dashboard = null; message($('records-state'), error.message, true); } }
  }
  function renderRows() {
    const data = state.dashboard; if (!data) return;
    const filter = $('course-filter').value; const rows = data.rows.filter((row) => !filter || String(row.courseId) === filter);
    const canEdit = Boolean(data.capabilities.manageGrades);
    $('grade-action-heading').hidden = !canEdit; $('grade-hint').hidden = !canEdit;
    $('records-body').replaceChildren();
    message($('records-state'), rows.length ? '' : filter ? 'No student records for this course yet.' : state.actor.role === 'student' ? 'No enrolled courses yet. Ask your administrator to enroll you in a course.' : 'No student course records are available. Enrollment is managed by an administrator.');
    rows.forEach((row) => {
      const tr = node('tr'); const student = node('td'); student.append(node('span', row.studentName), node('small', row.studentEmail));
      const course = node('td'); course.append(node('span', row.courseCode), node('small', row.courseTitle));
      const grade = node('td', row.grade == null ? 'Not yet graded' : row.grade, row.grade == null ? 'ungraded' : 'grade-number'); tr.append(student, course, grade);
      if (canEdit) {
        const cell = node('td'); const form = node('form', null, 'grade-form'); const input = node('input'); input.type = 'number'; input.min = '5'; input.max = '10'; input.step = '1'; input.required = true; input.setAttribute('aria-label', `Grade for ${row.studentName} in ${row.courseCode}, from 5 to 10`); if (row.grade != null) input.value = row.grade;
        const save = node('button', 'Save', 'button secondary'); save.type = 'submit'; form.append(input, save); cell.append(form); tr.append(cell);
        form.addEventListener('submit', async (event) => {
          event.preventDefault(); if (form.dataset.busy || !form.reportValidity()) return;
          const value = Number(input.value); if (!Number.isInteger(value) || value < 5 || value > 10) return;
          const epoch = state.epoch;
          await busyForm(form, async () => { message($('grade-message'), 'Saving grade…'); try { await api('/grades', { studentId: row.studentId, courseId: row.courseId, grade: value }); if (epoch !== state.epoch) return; message($('grade-message'), 'Grade saved.'); await loadDashboard(); } catch (error) { if (epoch === state.epoch) message($('grade-message'), error.message, true); } });
        });
      }
      $('records-body').append(tr);
    });
  }
  function fillSelect(select, values, placeholder, required = true) {
    select.replaceChildren(); const empty = node('option', placeholder); empty.value = ''; empty.disabled = required; empty.selected = true; select.append(empty);
    values.forEach(([value, label]) => { const option = node('option', label); option.value = String(value); select.append(option); });
  }
  async function loadAdministration() {
    if (!permitted('administration')) return;
    const current = startLoad('administration'); $('admin-content').hidden = true; message($('admin-state'), 'Loading accounts and courses…');
    try {
      const data = await api('/administration'); if (!current()) return;
      if (!['users', 'courses', 'assignments', 'enrollments'].every((key) => Array.isArray(data[key]))) throw new Error('The server returned incomplete administration data.');
      state.administration = data;
      const active = data.users.filter((user) => user.active);
      fillSelect($('role-user'), active.map((u) => [u.id, `${u.name} · ${u.email} (${roles[u.role] || u.role})`]), 'Choose an account');
      fillSelect($('assignment-user'), active.filter((u) => u.role === 'professor').map((u) => [u.id, `${u.name} · ${u.email}`]), 'Choose a professor');
      fillSelect($('enrollment-student'), active.filter((u) => u.role === 'student').map((u) => [u.id, `${u.name} · ${u.email}`]), 'Choose a student');
      ['assignment-course', 'enrollment-course'].forEach((id) => fillSelect($(id), data.courses.map((c) => [c.id, `${c.code} · ${c.title}`]), 'Choose a course'));
      $('accounts-body').replaceChildren();
      data.users.forEach((user) => { const tr = node('tr'); [user.name, user.email, roles[user.role] || user.role, user.active ? 'Active' : 'Inactive'].forEach((value) => tr.append(node('td', value))); $('accounts-body').append(tr); });
      const userName = (id) => { const user = data.users.find((u) => String(u.id) === String(id)); return user ? `${user.name} (${user.email})` : `Account ${id}`; };
      const courseName = (id) => { const course = data.courses.find((c) => String(c.id) === String(id)); return course ? `${course.code} · ${course.title}` : `Course ${id}`; };
      [['assignment-list', data.assignments, 'userId', 'No teaching assignments yet.'], ['enrollment-list', data.enrollments, 'studentId', 'No student enrollments yet.']].forEach(([id, entries, userKey, empty]) => { $(id).replaceChildren(); if (!entries.length) $(id).append(node('li', empty, 'muted')); entries.forEach((entry) => $(id).append(node('li', `${userName(entry[userKey])} → ${courseName(entry.courseId)}`))); });
      message($('admin-state'), data.users.length ? '' : 'No accounts returned by the server.'); $('admin-content').hidden = false;
    } catch (error) { if (current()) message($('admin-state'), error.message, true); }
  }
  const adminActions = [
    ['role-form', '/roles', 'Role updated.'], ['assignment-form', '/assignments', 'Teaching assignment saved.'], ['enrollment-form', '/enrollments', 'Student enrolled.'], ['course-form', '/courses', 'Course created.']
  ];
  adminActions.forEach(([id, path, success]) => {
    $(id).addEventListener('submit', async (event) => {
      event.preventDefault(); const form = event.currentTarget;
      if (form.dataset.busy || !form.reportValidity()) return;
      const body = Object.fromEntries(new FormData(form)); Object.keys(body).forEach((key) => { body[key] = body[key].trim(); });
      if (path === '/roles' && String(body.userId) === String(state.actor.id) && body.role !== 'admin') { message(form.querySelector('.form-message'), 'You can’t demote your own administrator account.', true); return; }
      const epoch = state.epoch;
      await busyForm(form, async () => {
        const status = form.querySelector('.form-message'); message(status, 'Saving…');
        try { await api(path, body); if (epoch !== state.epoch) return; form.reset(); message(status, success); await Promise.all([loadAdministration(), loadDashboard()]); }
        catch (error) { if (epoch === state.epoch) message(status, error.message, true); }
      });
    });
  });
  async function loadAudit() {
    if (!permitted('audit')) return;
    const current = startLoad('audit'); $('audit-body').replaceChildren(); message($('audit-state'), 'Loading access history…');
    try {
      const data = await api('/audit'); if (!current()) return;
      if (!Array.isArray(data.events)) throw new Error('The server returned incomplete access history.');
      message($('audit-state'), data.events.length ? '' : 'No activity is available yet.');
      data.events.forEach((event) => {
        const tr = node('tr'); const when = new Date(event.timestamp); const time = node('td');
        if (!Number.isNaN(when.getTime())) { const el = node('time', when.toLocaleString()); el.dateTime = when.toISOString(); time.append(el); } else text(time, event.timestamp || 'Not recorded');
        tr.append(time); [event.actorName || 'Not recorded', event.action, event.allowed === true ? 'Allowed' : event.allowed === false ? 'Denied' : 'Not recorded', event.target || '—'].forEach((value) => tr.append(node('td', typeof value === 'object' ? JSON.stringify(value) : value))); $('audit-body').append(tr);
      });
    } catch (error) { if (current()) message($('audit-state'), error.message, true); }
  }
  $('role-user').addEventListener('change', () => { const user = state.administration && state.administration.users.find((u) => String(u.id) === $('role-user').value); if (user) $('role-value').value = user.role; });
  $('course-filter').addEventListener('change', renderRows);
  $('refresh-records').addEventListener('click', loadDashboard);
  $('refresh-administration').addEventListener('click', loadAdministration);
  $('refresh-audit').addEventListener('click', loadAudit);
  $('retry-session').addEventListener('click', loadSession);
  $('signout').addEventListener('click', async () => {
    const button = $('signout'); if (button.disabled) return; button.disabled = true;
    try { await api('/signout', {}); clearPrivateData(); state.csrf = ''; showTop('loading'); await loadSession(); notice('You’ve signed out.'); }
    catch (error) { notice(error.message, true); }
    finally { button.disabled = false; }
  });
  loadSession();
})();
