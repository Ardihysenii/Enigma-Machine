'use strict';
(() => {
  const $ = (id) => document.getElementById(id);
  const state = { actor: null, csrf: '', configured: false, dashboard: null, administration: null, view: 'overview', epoch: 0, loads: {}, policy: null, dirty: false, policyPending: false, polling: false };
  const roles = { student: 'Student', professor: 'Teacher', admin: 'Administrator' };
  const text = (element, value) => { element.textContent = value == null ? '' : String(value); };
  const node = (tag, value, className) => { const el = document.createElement(tag); if (value != null) text(el, value); if (className) el.className = className; return el; };
  function message(element, value, error = false) { text(element, value); element.classList.toggle('is-error', error); element.classList.toggle('is-success', !error && Boolean(value)); }
  function notice(value, error = false) { message($('global-message'), value, error); $('global-message').hidden = !value; }
  function showTop(view) { ['loading', 'setup', 'auth', 'dashboard'].forEach((name) => { $(`${name}-view`).hidden = name !== view; }); }
  function clearPrivateData() {
    text($('workspace-identity'), 'ACADEMIC WORKSPACE');
    $('teacher-directory').hidden = true; $('teacher-directory-body').replaceChildren(); text($('teacher-directory-state'), ''); $('teacher-student-search').value = ''; $('teacher-management').hidden = true; delete $('teacher-management').dataset.ready; $('teacher-tools').hidden = true; $('teacher-workspace-note').hidden = true;
    ['teacher-enrollment-course', 'teacher-student-id', 'teacher-unassigned-course'].forEach(id => $(id).replaceChildren());
    state.epoch += 1; state.actor = null; state.dashboard = null; state.administration = null; state.dirty = false;
    $('professor-content').hidden = true; text($('professor-result'), '');
    ['overview-summary', 'course-preview', 'course-cards', 'records-body', 'record-summary', 'accounts-body', 'assignment-list', 'enrollment-list', 'audit-body'].forEach((id) => $(id).replaceChildren());
    ['role-user', 'assignment-user', 'assignment-course', 'enrollment-student', 'enrollment-course', 'course-filter'].forEach((id) => $(id).replaceChildren());
    ['actor-name', 'actor-role', 'actor-email', 'records-state', 'admin-state', 'audit-state', 'grade-message'].forEach((id) => text($(id), ''));
    document.querySelectorAll('#dashboard-view .form-message').forEach((el) => message(el, ''));
    $('admin-content').hidden = true;
    ['role-form', 'assignment-form', 'enrollment-form', 'course-form', 'teacher-course-form', 'teacher-enrollment-form', 'teacher-assignment-form'].forEach((id) => $(id).reset());
    $('record-search').value = '';
    text($('overview-title'), 'Your academic workspace.');
    text($('scope-description'), 'Server-enforced permissions determine the records and actions available to you.');
  }
  class ApiError extends Error { constructor(message, status) { super(message); this.status = status; } }
  async function api(path, body) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 9000);
    try {
      const response = await fetch('/api/portal' + path, {
        method: body === undefined ? 'GET' : 'POST', credentials: 'same-origin', cache: 'no-store', signal: controller.signal,
        headers: body === undefined ? { Accept: 'application/json' } : { Accept: 'application/json', 'Content-Type': 'application/json', 'X-CSRF-Token': state.csrf },
        ...(body === undefined ? {} : { body: JSON.stringify(body) })
      });
      let data;
      try { data = await response.json(); }
      catch (error) {
        if (error.name === 'AbortError') throw error;
        throw new ApiError('The server returned an unreadable response. Please try again.', response.status);
      }
      if (!response.ok) {
        if (response.status === 401 && state.actor && !['/signin', '/signup'].includes(path)) {
          clearPrivateData(); showTop('auth'); notice('Your session has ended. Sign in again to continue.', true);
        }
        throw new ApiError(typeof data.error === 'string' ? data.error : 'This request couldn’t be completed.', response.status);
      }
      return data;
    } catch (error) {
      if (error instanceof ApiError) throw error;
      throw new ApiError(error.name === 'AbortError' ? 'The request timed out. Please retry.' : 'The server couldn’t be reached. Check your connection and try again.', 0);
    } finally { clearTimeout(timeout); }
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
        message(form.querySelector('.form-message'), name === 'signin' ? 'Signing in…' : 'Creating your account…');
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
      await refreshPolicy(false);
      if (data.actor) { state.actor = data.actor; await enterDashboard(); } else { showTop('auth'); }
    } catch (error) {
      clearPrivateData(); showTop('setup'); notice(error.message, true);
      text($('setup-view').querySelector('h1'), 'We couldn’t connect to campus.');
      text($('setup-view').querySelector('p'), 'Your session could not be checked. The database may be temporarily unavailable, or the request timed out. No account changes have been made. Retry when the connection is ready.');
    }
  }
  function applyActor(actor) {
    text($('actor-name'), actor.name); text($('actor-email'), actor.email); text($('actor-role'), roles[actor.role] || actor.role);
  }
  async function enterDashboard() {
    state.view = state.actor.role === 'professor' ? 'records' : 'overview'; state.dirty = false; applyActor(state.actor); showTop('dashboard');
    document.querySelectorAll('[data-view]').forEach((button) => { button.hidden = button.dataset.view === 'administration'; });
    switchView(state.view, false); await refreshPolicy(false); await loadDashboard();
  }
  function permitted(view) {
    const caps = state.dashboard && state.dashboard.capabilities;
    return ['overview', 'records', 'courses', 'professor', 'audit'].includes(view) || Boolean(caps && view === 'administration' && caps.administer);
  }
  function switchView(view, load = true) {
    if (!permitted(view)) return;
    state.view = view;
    ['overview', 'records', 'courses', 'professor', 'administration', 'audit'].forEach((name) => { $(`${name}-view`).hidden = name !== view; });
    document.querySelectorAll('[data-view]').forEach((button) => { if (button.dataset.view === view) button.setAttribute('aria-current', 'page'); else button.removeAttribute('aria-current'); });
    if (load && view === 'administration') loadAdministration();
    if (load && view === 'audit') loadAudit();
  }
  document.querySelectorAll('[data-view]').forEach((button) => button.addEventListener('click', () => switchView(button.dataset.view)));
  function startLoad(name) { const id = (state.loads[name] || 0) + 1; state.loads[name] = id; const epoch = state.epoch; return () => state.epoch === epoch && state.loads[name] === id && Boolean(state.actor); }
  async function loadDashboard(background = false, force = false) {
    if (!state.actor || (background && isEditing() && !force)) return;
    if (!background) state.dirty = false;
    const current = startLoad('dashboard');
    if (!background) text($('records-state'), 'Loading academic records…');
    try {
      const data = await api(background ? '/dashboard?poll=1' : '/dashboard'); if (!current()) return;
      if (!data.actor || !Array.isArray(data.rows) || !Array.isArray(data.courses) || !data.capabilities) throw new Error('The server returned incomplete academic records.');
      if (background && isEditing() && !force) { state.policyPending = true; return; }
      applyDashboard(data);

    } catch (error) { if (current()) { clearAcademicData(); message($('records-state'), error.message, true); notice(error.message, true); } }
  }
  function renderRows() {
    const data = state.dashboard; if (!data) return;
    const filter = $('course-filter').value;
    const search = $('record-search').value.trim().toLocaleLowerCase();
    const rows = data.rows.filter((row) => (!filter || String(row.courseId) === filter) && (!search || [row.studentName, row.studentEmail, row.courseCode, row.courseTitle].join(' ').toLocaleLowerCase().includes(search)));
    const canEdit = Boolean(data.capabilities.manageGrades);
    $('grade-action-heading').hidden = !canEdit; $('grade-hint').hidden = !canEdit;
    $('records-body').replaceChildren();
    message($('records-state'), rows.length ? `${rows.length} record${rows.length === 1 ? '' : 's'} · ${canEdit ? 'Grade changes are saved to fictional records.' : 'Read-only access.'}` : search ? 'No records match your search.' : filter ? 'No student records for this course yet.' : state.actor.role === 'student' ? 'No enrolled courses yet. Ask your teacher to enroll you using your account email.' : 'No student records yet. Open Manage courses & class roster above to connect a course and add students.');
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
    state.dirty = false;
    const current = startLoad('administration'); $('admin-content').hidden = true; message($('admin-state'), 'Loading accounts and courses…');
    try {
      const data = await api('/administration'); if (!current()) return;
      if (!['users', 'courses', 'assignments', 'enrollments'].every((key) => Array.isArray(data[key]))) throw new Error('The server returned incomplete administration data.');
      state.administration = data;
      const active = data.users.filter((user) => user.active);
      fillSelect($('role-user'), active.map((u) => [u.id, `${u.name} · ${u.email} (${roles[u.role] || u.role})`]), 'Choose an account');
      fillSelect($('assignment-user'), active.filter((u) => u.role === 'professor').map((u) => [u.id, `${u.name} · ${u.email}`]), 'Choose a teacher');
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
  [['teacher-course-form', '/courses', 'Course created. Add a student, then enter their grade below.'], ['teacher-enrollment-form', '/teaching/enrollments', 'Student added. Their grade row is available below.'], ['teacher-assignment-form', '/teaching/assignments', 'Course connected. Existing enrolled students and grades are shown below.']].forEach(([id, path, success]) => {
    $(id).addEventListener('submit', async (event) => {
      event.preventDefault(); const form = event.currentTarget;
      if (form.dataset.busy || !form.reportValidity()) return;
      const body = Object.fromEntries(new FormData(form)); const epoch = state.epoch;
      await busyForm(form, async () => {
        try { await api(path, body); if (epoch !== state.epoch) return; form.reset(); state.dirty = false; await loadDashboard(); $('teacher-management').open = true; notice(success); message(form.querySelector('.form-message'), success); }
        catch (error) { if (epoch === state.epoch) message(form.querySelector('.form-message'), error.message, true); }
      });
    });
  });
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
    if (!state.actor) return;
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
    } catch (error) { if (current()) message($('audit-state'), (error.status ? 'HTTP ' + error.status + ' · ' : '') + error.message, true); }
  }
  $('role-user').addEventListener('change', () => { const user = state.administration && state.administration.users.find((u) => String(u.id) === $('role-user').value); if (user) $('role-value').value = user.role; });
  $('course-filter').addEventListener('change', renderRows);
  $('refresh-records').addEventListener('click', () => loadDashboard());
  $('refresh-overview').addEventListener('click', () => loadDashboard());
  $('record-search').addEventListener('input', renderRows);
  $('refresh-administration').addEventListener('click', loadAdministration);
  $('refresh-audit').addEventListener('click', loadAudit);
  $('retry-session').addEventListener('click', loadSession);
  $('signout').addEventListener('click', async () => {
    const button = $('signout'); if (button.disabled) return; button.disabled = true;
    try { await api('/signout', {}); clearPrivateData(); state.csrf = ''; showTop('loading'); await loadSession(); notice('You’ve signed out.'); }
    catch (error) { notice(error.message, true); }
    finally { button.disabled = false; }
  });

  const controlNames = {
    student_own_grades_only: 'Students: own grades only',
    block_student_professor_area: 'Teacher area restriction',
    block_student_grade_edit: 'Student grade-edit restriction',
    professor_assigned_courses_only: 'Assigned-course scope',
    session_inactivity_timeout: 'Optional idle-timeout demo (30 seconds)',
    audit_professor_only: 'Access-history restriction'
  };
  function clearAcademicData() {
    state.dashboard = null; state.administration = null;
    $('teacher-directory').hidden = true; $('teacher-directory-body').replaceChildren(); text($('teacher-directory-state'), ''); $('teacher-student-search').value = ''; $('teacher-management').hidden = true; delete $('teacher-management').dataset.ready; $('teacher-tools').hidden = true; $('teacher-workspace-note').hidden = true; ['teacher-enrollment-course', 'teacher-student-id', 'teacher-unassigned-course'].forEach(id => $(id).replaceChildren());
    ['overview-summary', 'course-preview', 'course-cards', 'records-body', 'record-summary', 'accounts-body', 'assignment-list', 'enrollment-list', 'audit-body'].forEach((id) => $(id).replaceChildren());
    $('admin-content').hidden = true; $('professor-content').hidden = true;
    ['role-user', 'assignment-user', 'assignment-course', 'enrollment-student', 'enrollment-course'].forEach((id) => $(id).replaceChildren());
    document.querySelectorAll('[data-view="administration"]').forEach((el) => { el.hidden = true; });
  }
  function applyDashboard(data) {
    const changed = state.actor && (state.actor.role !== data.actor.role || String(state.actor.id) !== String(data.actor.id));
    if (changed) {
      clearAcademicData(); state.epoch += 1; state.dirty = false;
      ['role-form', 'assignment-form', 'enrollment-form', 'course-form', 'teacher-course-form', 'teacher-enrollment-form', 'teacher-assignment-form'].forEach((id) => $(id).reset());
      text($('professor-result'), '');
      notice('Your account permissions changed. This workspace now reflects your current role.');
    }
    if (data.policy) applyPolicy(data.policy);
    state.dashboard = data; state.actor = data.actor; applyActor(data.actor);
    const caps = data.capabilities;
    const isTeacher = data.actor.role === 'professor';
    $('teacher-directory').hidden = !isTeacher;
    $('teacher-tools').hidden = !isTeacher;
    $('teacher-management').hidden = !isTeacher;
    if (isTeacher && !$('teacher-management').dataset.ready) { $('teacher-management').open = true; $('teacher-management').dataset.ready = 'true'; }
    $('teacher-workspace-note').hidden = !isTeacher;
    text($('workspace-identity'), isTeacher ? 'TEACHER WORKSPACE' : data.actor.role === 'student' ? 'STUDENT WORKSPACE' : 'ADMINISTRATION');
    document.querySelectorAll('.workspace-nav [data-view="professor"]').forEach(el => { el.hidden = data.actor.role !== 'student'; });
    document.querySelectorAll('.workspace-nav [data-view="records"]').forEach(el => { el.lastChild.textContent = isTeacher ? 'Gradebook' : 'My grades'; });
    const oldStudent = $('teacher-student-id').value;
    fillSelect($('teacher-student-id'), (data.teachingStudents || []).filter(u => u.active !== false).map(u => [u.id, u.name + ' · ' + u.email]), 'Select a database student');
    if ((data.teachingStudents || []).some(u => String(u.id) === oldStudent)) $('teacher-student-id').value = oldStudent;
    const oldUnassigned = $('teacher-unassigned-course').value;
    fillSelect($('teacher-unassigned-course'), (data.unassignedCourses || []).map(c => [c.id, c.code + ' · ' + c.title]), 'Select an unassigned course');
    if ((data.unassignedCourses || []).some(c => String(c.id) === oldUnassigned)) $('teacher-unassigned-course').value = oldUnassigned;
    text($('teacher-workspace-note'), (data.teachingCourses || []).length ? 'This gradebook shows students enrolled in your assigned courses. Add a database student above to enter their first grade. Saved changes appear in that student’s account. The assigned-course security switch controls whether other courses can be viewed or edited.' : 'You have no assigned courses yet. Connect an unassigned existing course or create a new one above. We do not silently grant access to another teacher’s classes.');
    const selectedTeachingCourse = $('teacher-enrollment-course').value;
    fillSelect($('teacher-enrollment-course'), (data.teachingCourses || []).map((c) => [c.id, c.code + ' · ' + c.title]), 'Choose your course');
    if ((data.teachingCourses || []).some((c) => String(c.id) === selectedTeachingCourse)) $('teacher-enrollment-course').value = selectedTeachingCourse;
    document.querySelectorAll('[data-view="administration"]').forEach((el) => { el.hidden = !caps.administer; });
    if (!caps.administer) {
      state.administration = null; $('admin-content').hidden = true;
      ['accounts-body', 'assignment-list', 'enrollment-list', 'role-user', 'assignment-user', 'assignment-course', 'enrollment-student', 'enrollment-course'].forEach((id) => $(id).replaceChildren());
    }
    if (!caps.readAudit) $('audit-body').replaceChildren();
    if (!permitted(state.view)) switchView('overview', false);
    text($('records-title'), isTeacher ? 'Teacher gradebook.' : data.actor.role === 'student' ? 'My grades.' : 'Academic grades.');
    text($('records-description'), isTeacher ? 'Select students, enter new grades, or update saved grades. Every change is checked and saved by the server.' : caps.manageGrades ? 'The laboratory grade-edit restriction is OFF. Permitted changes save to fictional records.' : 'Your enrolled courses and saved results. Read-only while the grade-edit protection is ON.');
    text($('overview-title'), isTeacher ? 'Teacher dashboard.' : data.actor.role === 'student' ? 'Student dashboard.' : 'Administrator dashboard.');
    text($('overview-description'), 'A focused view of the courses and recorded results available to your account.');
    text($('courses-description'), data.actor.role === 'student' ? 'Your enrolled courses, as returned by the server.' : data.actor.role === 'professor' ? 'Courses available under your current teaching permissions.' : 'The course catalog available to your administrator account.');
    text($('scope-description'), data.actor.role === 'student' ? 'Student scope is controlled by Task 01. Turning protections off can expose additional fictional records or enable grade editing. The server decides every request.' : 'Your current role and the active security controls determine course visibility and editing permissions.');
    const previous = $('course-filter').value;
    fillSelect($('course-filter'), data.courses.map((c) => [c.id, c.code + ' · ' + c.title]), 'All courses', false);
    if (data.courses.some((c) => String(c.id) === previous)) $('course-filter').value = previous;
    const graded = data.rows.filter((row) => typeof row.grade === 'number');
    $('overview-summary').replaceChildren();
    [['Available courses', data.courses.length], ['Recorded grades', graded.length], ['Awaiting a grade', data.rows.length - graded.length]].forEach(([label, count]) => {
      const item = node('div', null, 'summary-item'); item.append(node('span', label), node('strong', count)); $('overview-summary').append(item);
    });
    renderCourses(); renderRows(); renderStudentDirectory(); renderAccess();
  }
  function renderStudentDirectory() {
    const data = state.dashboard;
    const body = $('teacher-directory-body'); body.replaceChildren();
    if (!data || data.actor.role !== 'professor') return;
    const search = $('teacher-student-search').value.trim().toLocaleLowerCase();
    const all = data.teachingStudents || [];
    const students = all.filter(u => !search || (u.name + ' ' + u.email).toLocaleLowerCase().includes(search));
    text($('teacher-directory-state'), all.length ? students.length + ' of ' + all.length + ' student accounts' : 'No student accounts exist yet. Create a Student account to start; no demo students are invented.');
    if (all.length && !students.length) text($('teacher-directory-state'), 'No students match your search.');
    students.forEach(user => {
      const rows = data.rows.filter(row => String(row.studentId) === String(user.id));
      const tr = node('tr'); const identity = node('td'); identity.append(node('span', user.name), node('small', user.email));
      tr.append(identity, node('td', user.active === false ? 'Inactive' : 'Active'), node('td', rows.length ? rows.map(row => row.courseCode + ': ' + (row.grade == null ? 'Not yet graded' : row.grade)).join(', ') : 'No enrollment in visible courses'));
      const actions = node('td');
      const enroll = node('button', 'Enroll in course', 'button secondary'); enroll.type = 'button'; enroll.disabled = user.active === false;
      enroll.addEventListener('click', () => {
        $('teacher-management').open = true; $('teacher-student-id').value = String(user.id);
        $('teacher-enrollment-form').scrollIntoView({ block: 'center', behavior: 'smooth' });
        $('teacher-enrollment-course').focus();
        if (!(data.teachingCourses || []).length) notice('Connect an unassigned course or create your course first, then enroll this student.');
      });
      actions.append(enroll);
      if (rows.length) {
        const grades = node('button', 'View grades', 'button secondary'); grades.type = 'button';
        grades.addEventListener('click', () => { $('record-search').value = user.email; $('course-filter').value = ''; renderRows(); $('records-table-title').scrollIntoView({ block: 'center' }); });
        actions.append(grades);
      }
      tr.append(actions); body.append(tr);
    });
  }
  $('teacher-student-search').addEventListener('input', renderStudentDirectory);
  function renderCourses() {
    const data = state.dashboard;
    $('course-cards').replaceChildren(); $('course-preview').replaceChildren();
    if (!data.courses.length) {
      const empty = state.actor.role === 'student' ? 'No enrolled courses yet. Ask your teacher to enroll you using your account email.' : 'No courses are available to your account yet.';
      $('course-cards').append(node('p', empty, 'empty-state'));
      $('course-preview').append(node('p', empty, 'empty-state')); return;
    }
    data.courses.forEach((course, index) => {
      const rows = data.rows.filter((row) => String(row.courseId) === String(course.id));
      const graded = rows.filter((row) => row.grade != null).length;
      const card = node('article', null, 'course-card');
      const code = node('span', course.code, 'course-monogram');
      card.append(code, node('h2', course.title), node('p', rows.length + ' accessible record' + (rows.length === 1 ? '' : 's') + ' · ' + graded + ' graded'));
      const button = node('button', 'View course grades →', 'button secondary'); button.type = 'button';
      button.addEventListener('click', () => { $('course-filter').value = String(course.id); $('record-search').value = ''; renderRows(); switchView('records', false); });
      card.append(button); $('course-cards').append(card);
      if (index < 3) {
        const preview = node('div', null, 'preview-course'); const detail = node('div');
        detail.append(node('h3', course.title), node('p', rows.length + ' accessible records · ' + graded + ' graded'));
        preview.append(node('span', course.code, 'course-monogram'), detail); $('course-preview').append(preview);
      }
    });
  }
  function renderAccess() {
    const student = state.actor?.role === 'student';
    const locked = student && state.policy?.rules?.block_student_professor_area !== false;
    text($('professor-access'), locked ? 'Teacher access is restricted.' : 'Request your available teaching workspace.');
    text($('professor-description'), locked ? 'Your student role is blocked by the active professor-area rule. Test it below to see the server response, not a simulated result.' : student ? 'The professor-area restriction is off. Access is still subject to the current own-grade and grade-edit controls.' : 'Request the professor endpoint with your real account permissions.');
    text($('test-professor'), locked ? 'Test restricted access →' : 'Request teacher access →');
    text($('audit-access'), state.dashboard?.capabilities.readAudit ? (state.actor.role === 'professor' ? 'Campus activity: student signups, sign-ins, enrollments and grade changes. The latest 100 server-recorded events are shown.' : 'Your current permissions allow access history. Only server-returned events are shown.') : 'Access history is restricted for your role. Refresh history to test the boundary and see the server’s response.');
  }
  function applyPolicy(data) {
    if (!data || !data.rules) return;
    const changed = state.policy && String(state.policy.revision) !== String(data.revision);
    state.policy = data;
    text($('policy-count'), data.active_count + ' / ' + data.total_controls + ' security controls active');
    $('policy-controls').replaceChildren();
    Object.entries(controlNames).forEach(([key, label]) => {
      const enabled = data.rules[key] === true;
      const item = node('div', null, 'policy-control' + (enabled ? ' enabled' : ''));
      item.append(node('span', label), node('strong', enabled ? 'ON' : 'OFF')); $('policy-controls').append(item);
    });
    if (changed) {
      state.loads.dashboard = (state.loads.dashboard || 0) + 1;
      state.policyPending = true; state.dirty = false; state.dashboard = null;
      ['records-body', 'overview-summary', 'course-preview', 'course-cards', 'audit-body'].forEach(id => $(id).replaceChildren());
      $('grade-action-heading').hidden = true; $('grade-hint').hidden = true;
      text($('records-state'), 'Security policy changed. Reloading authorized records…');
      $('professor-content').hidden = true; text($('professor-result'), 'Policy changed. Request access again to test the current rules.');
      $('audit-body').replaceChildren();
    }
    if (state.actor) renderAccess();
    text($('policy-state'), state.policyPending && isEditing() ? 'Policy changed. Finish your edit, then save or refresh records to load the updated permissions.' : 'Controls are managed in Task 01. All permission decisions are enforced by the server.');
  }
  function isEditing() {
    return state.dirty || Boolean(document.activeElement?.closest('#dashboard-view form')) || Boolean(document.querySelector('#dashboard-view form[data-busy]'));
  }
  async function refreshPolicy(withDashboard = true) {
    if (document.hidden || state.polling) return;
    state.polling = true;
    try {
      const data = await api('/policy'); applyPolicy(data);
      // A non-touching session check detects expiry/revocation even when edits defer record refresh.
      if (withDashboard && state.actor && isEditing()) {
        const session = await api('/session');
        if (!session.actor || session.actor.role !== state.actor.role || String(session.actor.id) !== String(state.actor.id)) {
          clearPrivateData(); state.csrf = session.csrfToken || state.csrf; showTop('auth');
          notice('Your session or account permissions changed. Sign in again to continue.', true); return;
        }
        if (session.csrfToken) state.csrf = session.csrfToken;
      }
      if (withDashboard && state.actor && (!isEditing() || state.policyPending)) {
        await loadDashboard(true, state.policyPending); state.policyPending = false;
      }
    } catch (error) { message($('policy-state'), 'Policy refresh unavailable: ' + error.message, true); }
    finally { state.polling = false; }
  }
  $('test-professor').addEventListener('click', async () => {
    const button = $('test-professor'); if (button.disabled || !state.actor) return;
    const current = startLoad('professor'); button.disabled = true; $('professor-content').hidden = true;
    message($('professor-result'), 'Requesting access from the server…');
    try {
      const data = await api('/professor'); if (!current()) return;
      if (!data.actor || !Array.isArray(data.rows) || !Array.isArray(data.courses) || !data.capabilities) throw new Error('The server returned incomplete professor data.');
      applyDashboard(data); $('professor-content').hidden = false;
      message($('professor-result'), 'HTTP 200 · Access granted by the server.');
    } catch (error) { if (current()) message($('professor-result'), (error.status ? 'HTTP ' + error.status + ' · ' : '') + error.message, true); }
    finally { button.disabled = false; }
  });
  document.querySelectorAll('#dashboard-view form').forEach((form) => {
    form.addEventListener('input', () => { state.dirty = true; });
    form.addEventListener('change', () => { state.dirty = true; });
  });
  // Grade forms are created dynamically. Delegation keeps background refresh from discarding an edit.
  $('records-body').addEventListener('input', () => { state.dirty = true; });
  const policyChannel = typeof BroadcastChannel === 'function' ? new BroadcastChannel('enigma-college-policy') : null;
  policyChannel?.addEventListener('message', () => { void refreshPolicy(); });
  window.addEventListener('storage', (event) => { if (event.key === 'enigma-college-policy-changed') void refreshPolicy(); });
  document.addEventListener('visibilitychange', () => { if (!document.hidden) void refreshPolicy(); });
  window.addEventListener('focus', () => { void refreshPolicy(); });
  setInterval(() => { if (!document.hidden) void refreshPolicy(); }, 3000);

  let activityAt = 0, lastActivitySent = 0, activityPending = false;
  ['pointerdown', 'keydown', 'input', 'scroll'].forEach(type => document.addEventListener(type, event => {
    if (event.isTrusted && state.actor && !document.hidden) activityAt = Date.now();
  }, { passive: true }));
  setInterval(async () => {
    if (!state.actor || document.hidden || activityPending || activityAt <= lastActivitySent) return;
    const sent = activityAt; activityPending = true;
    try { await api('/activity', {}); lastActivitySent = sent; }
    catch (error) { if (error.status !== 401) message($('policy-state'), 'Activity sync unavailable; your draft has not been submitted.', true); }
    finally { activityPending = false; }
  }, 8000);
  loadSession();
})();
