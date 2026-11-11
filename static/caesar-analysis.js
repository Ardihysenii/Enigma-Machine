'use strict';
(() => {
  const get = id => document.getElementById(id);
  const form = get('task-form');
  if (!form) return;
  let controller = null, revision = 0;
  const button = document.createElement('button');
  button.id = 'find-caesar-key'; button.type = 'button'; button.className = 'secondary';
  button.textContent = 'Find the key'; button.hidden = true;
  button.setAttribute('aria-controls', 'caesar-key-results');
  button.title = 'Try all 26 Caesar keys. Paste encrypted English text in the message field.';
  form.querySelector('.form-actions').append(button);
  const panel = document.createElement('section');
  panel.id = 'caesar-key-results'; panel.className = 'caesar-key-results'; panel.hidden = true;
  panel.setAttribute('aria-label', 'Caesar key search results');
  form.after(panel);
  const element = (tag, text, cls) => {
    const el = document.createElement(tag); if (text != null) el.textContent = text;
    if (cls) el.className = cls; return el;
  };
  const eligible = () => document.body.dataset.task === 'classical' && get('cipher').value === 'caesar';
  function invalidate() {
    revision++; controller?.abort(); controller = null;
    button.disabled = false; button.textContent = 'Find the key';
    panel.hidden = true; panel.replaceChildren(); panel.removeAttribute('aria-busy');
  }
  function sync() { button.hidden = !eligible(); }
  function status(text) {
    panel.hidden = false; panel.replaceChildren();
    const p = element('p', text); p.setAttribute('role', 'status'); panel.append(p);
  }
  function useKey(key) {
    if (!eligible() || get('run-button').disabled) return;
    get('operation').value = 'decrypt'; get('key').value = String(key);
    get('key').dispatchEvent(new Event('input', { bubbles: true }));
    // Use the existing, tested decryption path and per-letter explanation.
    form.requestSubmit();
  }
  function candidate(row, best = false) {
    const card = element('article', null, best ? 'caesar-candidate best' : 'caesar-candidate');
    const head = element('div', null, 'caesar-candidate-heading');
    head.append(element('h3', (best ? 'Suggested key: ' : 'Key: ') + row.key));
    const use = element('button', 'Decrypt with key ' + row.key, 'secondary'); use.type = 'button';
    use.addEventListener('click', () => useKey(row.key)); head.append(use);
    card.append(head, element('pre', row.plaintext)); return card;
  }
  button.addEventListener('click', async () => {
    if (!eligible() || button.disabled || get('run-button').disabled) return;
    const message = get('message').value;
    invalidate();
    if (!/[a-z]/i.test(message)) { status('Paste encrypted text containing at least one A–Z letter.'); return; }
    const version = revision; const request = new AbortController(); controller = request;
    button.disabled = true; button.textContent = 'Trying all 26 keys…';
    status('Checking every Caesar shift and comparing English-language patterns…');
    panel.setAttribute('aria-busy', 'true');
    const timeout = setTimeout(() => request.abort(), 10000);
    try {
      const response = await fetch('/api/tasks/classical/run', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message, cipher: 'caesar', operation: 'find_key' }), signal: request.signal
      });
      const data = await response.json();
      if (version !== revision || !eligible()) return;
      if (!response.ok) throw new Error(data.error || 'The key search could not be completed.');
      const rows = data.candidates;
      if (data.mode !== 'find_key' || !Array.isArray(rows) || rows.length !== 26 ||
          new Set(rows.map(r => r.key)).size !== 26 || rows.some(r => !Number.isInteger(r.key) || r.key < 0 || r.key > 25 || typeof r.plaintext !== 'string')) {
        throw new Error('The search returned incomplete results. Please try again.');
      }
      panel.replaceChildren();
      const heading = element('h2', data.confidence === 'likely' ? 'Most likely English result' : 'Possible result — check the alternatives');
      heading.tabIndex = -1;
      const note = element('p', data.warning, 'caesar-confidence'); note.setAttribute('role', 'status');
      panel.append(heading, note, candidate(rows[0], true));
      const details = element('details'); details.append(element('summary', 'Compare all 26 possible keys'));
      rows.forEach(row => details.append(candidate(row)));
      panel.append(details, element('p', data.explanation, 'caesar-method'));
      heading.focus({ preventScroll: true });
      panel.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    } catch (error) {
      if (version === revision && eligible()) status(request.signal.aborted ? 'The search timed out. Try again.' : (error.message || 'Could not reach the server. Try again.'));
    } finally {
      clearTimeout(timeout);
      if (version === revision) { controller = null; button.disabled = false; button.textContent = 'Find the key'; panel.removeAttribute('aria-busy'); }
    }
  });
  form.addEventListener('input', invalidate);
  form.addEventListener('change', () => { invalidate(); sync(); });
  form.addEventListener('submit', invalidate, true);
  get('clear-button').addEventListener('click', () => { invalidate(); sync(); });
  document.addEventListener('enigma:navigate', () => { invalidate(); queueMicrotask(sync); });
  window.addEventListener('hashchange', () => { invalidate(); sync(); });
  sync();
})();
