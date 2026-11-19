'use strict';
(() => {
  const panel = document.getElementById('key-houses');
  if (!panel) return;
  const $ = id => document.getElementById('kh-' + id);
  const STORAGE = 'enigma.house-demo.v1';
  const checks = ['pkcs8_recovered', 'pkcs12_recovered', 'wrong_password_rejected_pkcs8', 'wrong_password_rejected_pkcs12'];
  let saved = null, selected = 0, busy = false, log = [];
  function status(text, kind = '') { $('status').textContent = text; $('status').dataset.kind = kind; }
  function record(message) {
    log.push(new Date().toISOString() + '  ' + message);
    if (log.length > 100) log.shift();
    $('log').textContent = log.join('\n');
  }
  function houseSVG(i) {
    const walls = ['#d2bd91', '#9aada1', '#b3997a'][i];
    const roof = ['#705b44', '#455e56', '#6b5146'][i];
    return '<svg viewBox="0 0 300 250" aria-hidden="true"><ellipse cx="151" cy="224" rx="128" ry="18" fill="#071c14" opacity=".5"/><path d="M23 218v-51m-16 29 16-35 16 35m-30-16 14-32 14 32M270 220v-67m-21 39 21-45 21 45m-36-23 15-34 15 34" fill="#456447" stroke="#72805a" stroke-width="2"/><path d="M91 231 124 196h49l43 35" fill="#a3a17b" opacity=".4"/><path d="M69 123 153 49l83 74v91H69z" fill="' + walls + '"/><path d="M200 55h17v50h-17z" fill="#9f8b6a"/><path d="m49 128 104-94 104 94-13 12-91-81-91 81z" fill="' + roof + '" stroke="#d7c49b" stroke-width="2"/><path d="M76 134h155M76 142h155M76 150h155M76 158h155M76 166h155M76 174h155M76 182h155M76 190h155M76 198h155M76 206h155" stroke="#4a4e36" opacity=".18"/><circle cx="153" cy="96" r="14" fill="#344a3a" stroke="#eee0b5" stroke-width="5"/><path d="M139 96h28m-14-14v28" stroke="#eee0b5" stroke-width="2"/><g fill="#e4bf78" stroke="#f0dfb4" stroke-width="4"><path d="M85 143h30v37H85zM190 143h30v37h-30z"/></g><path d="M100 144v34m-14-17h28m91-17v34m-14-17h28" stroke="#58614a" stroke-width="3"/><path d="M131 210v-54a23 23 0 0 1 46 0v54" fill="#0c2119" stroke="#ecdbaf" stroke-width="6"/><path class="kh-door-light" d="M134 208v-51a20 20 0 0 1 40 0v51l27 24h-95z" fill="#ebc370" opacity=".5"/><path class="kh-door" d="M133 210v-53a21 21 0 0 1 42 0v53z" fill="#435346" stroke="#213d30" stroke-width="2"/><circle cx="164" cy="178" r="3" fill="#edd292"/><path d="M127 212h54v7h-54" fill="#e0d0a5"/><g fill="#76906a"><ellipse cx="78" cy="213" rx="20" ry="12"/><ellipse cx="222" cy="213" rx="23" ry="12"/></g><g fill="#e3c275"><circle cx="72" cy="206" r="2"/><circle cx="85" cy="214" r="2"/><circle cx="215" cy="207" r="2"/><circle cx="231" cy="215" r="2"/></g><rect x="140" y="119" width="27" height="12" rx="3" fill="#203b2e"/><text x="153" y="128" text-anchor="middle" font-size="8" font-family="monospace" fill="#e8d3a2">0' + (i + 1) + '</text></svg>';
  }
  const houses = [0, 1, 2].map(i => {
    const button = document.createElement('button'); button.type = 'button'; button.className = 'kh-house';
    button.innerHTML = houseSVG(i) + '<span class="kh-house-label">House 0' + (i + 1) + '</span><span class="kh-house-state">' + (i === 0 ? 'YOUR MATCHING PUBLIC KEY' : 'A DIFFERENT PUBLIC KEY') + '</span>';
    button.setAttribute('aria-pressed', String(i === 0));
    button.setAttribute('aria-label', 'Select House 0' + (i + 1) + (i === 0 ? ', matching public key' : ', different public key'));
    button.addEventListener('click', () => { selected = i; houses.forEach((h, n) => h.setAttribute('aria-pressed', String(n === i))); $('target-heading').textContent = 'Open House 0' + (i + 1); });
    $('houses').append(button); return button;
  });
  function resetDoors() {
    houses.forEach((h, i) => { h.classList.remove('is-open', 'is-rejected'); h.querySelector('.kh-house-state').textContent = i === 0 ? 'YOUR MATCHING PUBLIC KEY' : 'A DIFFERENT PUBLIC KEY'; });
  }
  function updateControls() {
    panel.querySelectorAll('button,input,fieldset').forEach(el => { el.disabled = busy; });
    panel.querySelectorAll('[data-kh-download]').forEach(el => { el.disabled = busy || !saved; });
    $('open').querySelector('button').disabled = busy || !saved;
    $('log-download').disabled = busy || !log.length;
    panel.setAttribute('aria-busy', String(busy));
  }
  function validate(value) {
    if (!value || value.version !== 1 || typeof value.pkcs8 !== 'string' || value.pkcs8.length > 20000 || !value.pkcs8.includes('-----BEGIN ENCRYPTED PRIVATE KEY-----') || typeof value.pkcs12 !== 'string' || value.pkcs12.length > 100000 || !/^[A-Za-z0-9+/]+={0,2}$/.test(value.pkcs12) || typeof value.certificate !== 'string' || value.certificate.length > 20000 || !value.certificate.includes('-----BEGIN CERTIFICATE-----') || !Array.isArray(value.publicKeys) || value.publicKeys.length !== 3 || value.publicKeys.some(k => typeof k !== 'string' || k.length > 10000 || !k.includes('-----BEGIN PUBLIC KEY-----')) || typeof value.fingerprint !== 'string' || !/^[a-f0-9]{64}$/i.test(value.fingerprint) || typeof value.validUntil !== 'string' || !Number.isFinite(Date.parse(value.validUntil)) || !value.checks || checks.some(k => typeof value.checks[k] !== 'boolean')) throw new Error('Invalid saved demo');
    try { if (!atob(value.pkcs12).length) throw new Error(); } catch { throw new Error('Invalid saved bundle'); }
    // Rebuild an allowlisted object. Never persist passwords, decrypted keys or API URLs.
    return {version: 1, pkcs8: value.pkcs8, pkcs12: value.pkcs12, certificate: value.certificate, publicKeys: value.publicKeys.slice(), fingerprint: value.fingerprint, validUntil: value.validUntil, checks: Object.fromEntries(checks.map(k => [k, value.checks[k]]))};
  }
  function showMetadata() {
    $('metadata').replaceChildren(); if (!saved) return;
    for (const [label, text] of [['SHA-256', saved.fingerprint], ['Valid until', saved.validUntil], ['Certificate', 'Self-signed · not trusted identity evidence']]) {
      const dt = document.createElement('dt'), dd = document.createElement('dd'); dt.textContent = label; dd.textContent = text; $('metadata').append(dt, dd);
    }
  }
  function saveBlob(blob, filename) {
    const url = URL.createObjectURL(blob), a = document.createElement('a'); a.href = url; a.download = filename; document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  async function api(payload) {
    const response = await fetch('/api/tasks/packaging/run', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload), signal: AbortSignal.timeout(45000)});
    let data; try { data = await response.json(); } catch { throw new Error('The server returned an unreadable response. Retry after checking the Python server.'); }
    if (!response.ok) {
      if (response.status === 400 && payload.action === 'open') throw new Error('Incorrect password or invalid encrypted package.');
      throw new Error('Python rejected the request (HTTP ' + response.status + '). Check the local server and retry.');
    }
    return data;
  }
  function failure(error, operation) {
    const known = error instanceof Error ? error.message : '';
    const text = /^(Incorrect password|Python rejected|The server returned|Unexpected artifact|An encrypted artifact)/.test(known) ? known : 'Cannot reach the Python service, or the operation timed out. Check the connection and retry.';
    status(text, 'error'); record(operation + ': failed. ' + text);
  }
  $('generate').addEventListener('submit', async event => {
    event.preventDefault(); if (busy) return;
    let password = $('new-password').value; $('new-password').value = '';
    if (password.length < 12 || password.length > 128) { password = ''; status('Use 12–128 characters for the new disposable password.', 'error'); return; }
    busy = true; updateControls(); status('Python is generating and checking both encrypted containers…');
    try {
      const pending = api({password}); password = ''; const result = await pending;
      if (!result.artifacts || !Array.isArray(result.house_public_keys)) throw new Error('The server returned an unreadable response. Restart or update the Python server, then retry.');
      // Encrypted bytes arrive atomically with generation; no worker-local links.
      const next = validate({version: 1, pkcs8: result.artifacts.pkcs8, pkcs12: result.artifacts.pkcs12, certificate: result.artifacts.certificate, publicKeys: result.house_public_keys, fingerprint: result.certificate_sha256, validUntil: result.valid_until, checks: Object.fromEntries(checks.map(k => [k, result[k]]))});
      saved = next; log = []; resetDoors(); showMetadata();
      record('Generated disposable RSA key; copied encrypted PKCS #8, PKCS #12 and certificate bytes. Key contents redacted.');
      checks.forEach(k => record('Python check ' + k + ': ' + saved.checks[k]));
      let persisted = false;
      try { localStorage.setItem(STORAGE, JSON.stringify(saved)); persisted = true; } catch { try { localStorage.removeItem(STORAGE); } catch {} }
      $('storage').textContent = persisted ? 'Saved in this browser. Reload-safe downloads; password not saved.' : 'Browser storage unavailable or full. This key set works only until this page closes. Download copies now.';
      record(persisted ? 'Encrypted artifacts saved to browser storage. Password not saved.' : 'Browser persistence failed; artifacts available in page memory only.');
      status(checks.every(k => saved.checks[k]) ? 'Both containers passed Python’s recovery and wrong-password tests. Select a house and enter your password.' : 'Artifacts received, but a Python packaging check failed. Inspect the test record before relying on this demo.', checks.every(k => saved.checks[k]) ? '' : 'error');
    } catch (error) { failure(error, 'Packaging'); }
    finally { password = ''; busy = false; updateControls(); }
  });
  $('open').addEventListener('submit', async event => {
    event.preventDefault(); if (busy || !saved) return;
    let password = $('test-password').value; $('test-password').value = '';
    const format = panel.querySelector('input[name="kh-format"]:checked').value, target = selected;
    busy = true; updateControls(); houses[target].classList.remove('is-open', 'is-rejected');
    houses[target].querySelector('.kh-house-state').textContent = 'CHECKING WITH PYTHON…';
    status('Loading the encrypted container and verifying a fresh signed challenge…');
    try {
      const pending = api({action: 'open', format, artifact: format === 'pkcs8' ? saved.pkcs8 : saved.pkcs12, password, public_key: saved.publicKeys[target]}); password = ''; const result = await pending;
      if (typeof result.opened !== 'boolean' || result.key_loaded !== true) throw new Error('The server returned an unreadable response. Retry after checking the Python server.');
      const opened = result.opened === true;
      houses[target].classList.toggle('is-open', opened); houses[target].classList.toggle('is-rejected', !opened);
      houses[target].querySelector('.kh-house-state').textContent = opened ? 'OPEN · SIGNATURE VERIFIED' : 'LOCKED · DIFFERENT PUBLIC KEY';
      record('House 0' + (target + 1) + ' / ' + format + ': key_loaded=true; opened=' + opened + (typeof result.certificate_matches === 'boolean' ? '; certificate_matches=' + result.certificate_matches : '') + '. Password and key contents redacted.');
      status(opened ? 'House 0' + (target + 1) + ' opened: Python verified the signature with this house’s public key.' : 'Password accepted, door still locked. This house has a different public key.', opened ? '' : 'error');
    } catch (error) {
      houses[target].classList.add('is-rejected'); houses[target].querySelector('.kh-house-state').textContent = 'LOCKED · CHECK FAILED'; failure(error, 'House 0' + (target + 1) + ' / ' + format);
    } finally { password = ''; busy = false; updateControls(); }
  });
  panel.querySelectorAll('[data-kh-download]').forEach(button => button.addEventListener('click', () => {
    if (busy || !saved) return; const name = button.dataset.khDownload; let blob;
    if (name === 'bundle.p12') { const binary = atob(saved.pkcs12); blob = new Blob([Uint8Array.from(binary, c => c.charCodeAt(0))], {type: 'application/x-pkcs12'}); }
    else blob = new Blob([name === 'private-key.pem' ? saved.pkcs8 : saved.certificate], {type: 'application/x-pem-file'});
    saveBlob(blob, name); record('Downloaded ' + name + ' from saved artifact bytes.'); updateControls();
  }));
  $('log-download').addEventListener('click', () => { if (!busy) saveBlob(new Blob(['ENIGMA / Key packaging lab / redacted evidence\nPasswords, private-key contents and encrypted artifacts omitted.\n\n' + log.join('\n') + '\n'], {type: 'text/plain;charset=utf-8'}), 'enigma-key-house-evidence.txt'); });
  $('clear').addEventListener('click', () => {
    if (busy) return; let removed = true; try { localStorage.removeItem(STORAGE); } catch { removed = false; }
    saved = null; log = []; resetDoors(); showMetadata(); $('generate').reset(); $('open').reset();
    $('storage').textContent = removed ? 'No saved key set in this browser.' : 'Browser storage is inaccessible. Its saved copy could not be confirmed deleted; remove site data in browser settings.';
    record('Cleared in-memory demo and reset all doors. ' + (removed ? 'Removed only ' + STORAGE + ' from browser storage.' : 'Browser storage removal failed.'));
    status(removed ? 'Saved demo cleared. Downloaded copies and server files are not deleted.' : 'Page cleared, but browser storage deletion failed. Remove this site’s stored data before leaving.', removed ? '' : 'error'); updateControls();
  });
  try {
    const raw = localStorage.getItem(STORAGE);
    if (raw) { if (raw.length > 200000) throw new Error('Oversized saved demo'); saved = validate(JSON.parse(raw)); showMetadata(); $('storage').textContent = 'Restored encrypted artifacts from this browser. Enter the password again to test a door.'; record('Restored encrypted artifact bytes and public metadata; no password was stored.'); checks.forEach(k => record('Saved Python packaging check ' + k + ': ' + saved.checks[k])); status('Saved key set restored. All doors start locked; test a password to open one.'); }
  } catch { saved = null; $('storage').textContent = 'Browser storage unavailable or saved demo invalid. Create a fresh set, or clear the saved demo.'; status('Saved demo could not be loaded. No saved artifacts will be used until a fresh set is created.', 'error'); }
  const navigate = id => { panel.hidden = id !== 'packaging'; };
  document.addEventListener('enigma:navigate', event => navigate(event.detail.id));
  navigate(location.hash.slice(1) || document.body.dataset.task); updateControls();
})();
