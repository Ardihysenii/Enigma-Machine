'use strict';
(() => {
  const panel = document.getElementById('college-policy-panel');
  const status = document.getElementById('college-policy-status');
  const button = document.getElementById('apply-college-policy');
  const names = ['student_own_grades_only', 'block_student_professor_area', 'block_student_grade_edit', 'professor_assigned_courses_only', 'session_inactivity_timeout', 'audit_professor_only'];
  let dirty = false, loaded = false, pending = false, refreshing = false, csrf = '';
  const channel = typeof BroadcastChannel === 'function' ? new BroadcastChannel('enigma-college-policy') : null;
  function notify() {
    channel?.postMessage({ type: 'policy-changed' });
    try { localStorage.setItem('enigma-college-policy-changed', String(Date.now())); } catch (_) {}
  }
  async function api(path, body) {
    const response = await fetch(`/api/portal${path}`, {
      method: body === undefined ? 'GET' : 'POST', credentials: 'same-origin', cache: 'no-store',
      headers: body === undefined ? { Accept: 'application/json' } : { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }), signal: AbortSignal.timeout(10000)
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'The college server could not complete this request.');
    return data;
  }
  function summary(data) { return `${data.active_count} / ${data.total_controls} controls active on the signed-in college portal. Changes affect all fictional accounts.`; }
  async function refresh() {
    if (panel.hidden || pending || refreshing) return;
    refreshing = true;
    try {
      const data = await api('/policy');
      if (!dirty) for (const key of names) document.getElementById(key).checked = data.rules[key];
      loaded = true; button.disabled = false;
      status.textContent = summary(data) + (dirty ? ' You have unapplied changes.' : '');
    } catch (error) {
      loaded = false; button.disabled = true;
      status.textContent = `${error.message} Click Reload active rules to retry.`;
    } finally { refreshing = false; }
  }
  function changed() { dirty = true; status.textContent = 'Not applied yet. Click Apply security rules to update the college portal.'; }
  function navigate() { panel.hidden = location.hash !== '#analysis'; if (!panel.hidden) void refresh(); }
  for (const key of names) document.getElementById(key).addEventListener('change', changed);
  for (const [id, value] of [['enable-all-controls', true], ['disable-all-controls', false]]) {
    document.getElementById(id).addEventListener('click', () => {
      if (pending) return;
      for (const key of names) document.getElementById(key).checked = value;
      changed();
    });
  }
  document.getElementById('college-policy-form').addEventListener('submit', async (event) => {
    event.preventDefault(); if (pending || !loaded) return;
    pending = true; button.disabled = true;
    for (const key of names) document.getElementById(key).disabled = true;
    status.textContent = 'Applying the controls to saved fictional college records…';
    try {
      // Refresh the CSRF token immediately before writing; another tab may have signed in.
      const session = await api('/session');
      if (!session.configured || !session.csrfToken) throw new Error('The college database is not ready.');
      csrf = session.csrfToken;
      const rules = Object.fromEntries(names.map((key) => [key, document.getElementById(key).checked]));
      const data = await api('/policy', { rules });
      dirty = false; notify(); status.textContent = summary(data) + ' The dashboard refreshes automatically.';
      for (const key of names) document.getElementById(key).checked = data.rules[key];
    } catch (error) { dirty = true; status.textContent = `Apply was not confirmed: ${error.message} Reload the active rules before testing.`; }
    finally {
      pending = false; button.disabled = !loaded;
      for (const key of names) document.getElementById(key).disabled = false;
    }
  });
  document.getElementById('reload-college-policy').addEventListener('click', () => { if (!pending) { dirty = false; void refresh(); } });
  window.addEventListener('hashchange', navigate);
  window.addEventListener('focus', () => void refresh());
  channel?.addEventListener('message', () => void refresh());
  window.addEventListener('storage', (event) => { if (event.key === 'enigma-college-policy-changed') void refresh(); });
  setInterval(() => { if (!document.hidden) void refresh(); }, 3000);
  navigate();
})();
