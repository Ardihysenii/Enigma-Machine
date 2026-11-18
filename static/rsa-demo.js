/* Disposable RSA teaching keys only; no account/token integration or persistent storage. */
(() => {
  'use strict';
  const el = id => document.getElementById('rsa-' + id);
  const section = el('demo');
  if (!section) return;
  const algorithm = {name:'RSA-OAEP', modulusLength:2048, publicExponent:new Uint8Array([1,0,1]), hash:'SHA-256'};
  const encoder = new TextEncoder();
  let keys = null, ciphertext = null, original = '', busy = false, epoch = 0, pythonController = null;
  const active = () => document.body.dataset.task === 'rsa';
  const bytes = () => encoder.encode(el('message').value);
  const base64 = buffer => btoa(String.fromCharCode(...new Uint8Array(buffer)));
  function status(text, error = false) {
    el('status').textContent = text; el('status').className = error ? 'rsa-error' : '';
  }
  function controls() {
    const supported = Boolean(globalThis.crypto?.subtle);
    el('generate').disabled = busy || !supported;
    el('generate').textContent = keys ? 'Generate new keys' : '1. Generate Bob’s keys';
    el('encrypt').disabled = busy || !keys || !bytes().length || bytes().length > 190;
    el('decrypt').disabled = busy || !ciphertext;
    el('wrong').disabled = busy || !ciphertext;
    el('python').disabled = busy;
    el('byte-count').textContent = bytes().length + ' / 190 UTF-8 bytes';
    el('byte-count').className = bytes().length > 190 ? 'rsa-error' : 'muted';
    el('key-state').textContent = keys ? 'Bob’s key pair is ready · RSA-2048' : 'No keys yet';
  }
  function clearMessage() {
    ciphertext = null; original = '';
    el('ciphertext').value = '';
    el('recovered').textContent = 'Waiting for an encrypted message.';
    el('match').textContent = ''; el('match').className = '';
    el('wrong-result').textContent = 'Send a message to test the wrong key.';
    el('wrong-result').className = '';
    el('technical-output').textContent = 'No browser operation yet.';
    el('python-output').textContent = 'The Python result will appear here.';
  }
  function invalidate() {
    epoch += 1; busy = false;
    pythonController?.abort(); pythonController = null;
  }
  function reset() {
    invalidate(); keys = null; clearMessage();
    el('public').textContent = 'Generate keys first.';
    status('Start by generating Bob’s disposable key pair.'); controls();
  }
  async function operation(action) {
    if (busy || !active()) return;
    busy = true; const version = epoch; controls();
    const current = () => version === epoch && active();
    try { await action(current); }
    catch (error) {
      if (current()) status(error.message || 'The operation failed. Reset the demo and try again.', true);
    } finally { if (current()) { busy = false; controls(); } }
  }
  el('generate').addEventListener('click', () => operation(async current => {
    keys = null; clearMessage(); el('public').textContent = 'Generating…';
    status('Generating a fresh disposable key pair…');
    const pair = await crypto.subtle.generateKey(algorithm, false, ['encrypt','decrypt']);
    const publicBytes = await crypto.subtle.exportKey('spki', pair.publicKey);
    if (!current()) return;
    keys = pair;
    const encoded = base64(publicBytes);
    el('public').textContent = '-----BEGIN PUBLIC KEY-----\n' + encoded.match(/.{1,64}/g).join('\n') + '\n-----END PUBLIC KEY-----';
    status('Keys ready. Alice can now encrypt a message using Bob’s public key.');
  }));
  el('encrypt').addEventListener('click', () => operation(async current => {
    if (!keys) throw Error('Generate Bob’s keys first.');
    const message = el('message').value, input = encoder.encode(message);
    if (!input.length || input.length > 190) throw Error('Enter a message between 1 and 190 UTF-8 bytes.');
    clearMessage(); status('Alice is encrypting with Bob’s public key…');
    const encrypted = await crypto.subtle.encrypt({name:'RSA-OAEP'}, keys.publicKey, input);
    if (!current()) return;
    ciphertext = encrypted; original = message;
    el('ciphertext').value = base64(encrypted);
    el('recovered').textContent = 'Encrypted message received. Click “Decrypt as Bob” to open it.';
    el('technical-output').textContent = JSON.stringify({algorithm:'RSA-2048 / OAEP / SHA-256', engine:'Browser Web Crypto', ciphertext_base64:base64(encrypted), max_message_bytes:190, decrypted:false}, null, 2);
    status('Message sent. Try the unrelated key, then let Bob decrypt it.');
  }));
  el('wrong').addEventListener('click', () => operation(async current => {
    if (!ciphertext) throw Error('Encrypt a message first.');
    const captured = ciphertext;
    status('Testing a different private key against the intercepted message…');
    const unrelated = await crypto.subtle.generateKey(algorithm, false, ['encrypt','decrypt']);
    if (!current()) return;
    try {
      await crypto.subtle.decrypt({name:'RSA-OAEP'}, unrelated.privateKey, captured);
    } catch (error) {
      if (!current()) return;
      if (error.name !== 'OperationError') throw error;
      el('wrong-result').textContent = 'Rejected: this private key doesn’t match Bob’s public key. The message stays unreadable.';
      el('wrong-result').className = 'rsa-success';
      status('The unrelated private key failed. Bob can still use his matching private key.'); return;
    }
    throw Error('Unexpected result: the unrelated key decrypted the message. Reset the demo.');
  }));
  el('decrypt').addEventListener('click', () => operation(async current => {
    if (!keys || !ciphertext) throw Error('Encrypt a message first.');
    status('Bob is decrypting with his matching private key…');
    const recoveredBytes = await crypto.subtle.decrypt({name:'RSA-OAEP'}, keys.privateKey, ciphertext);
    if (!current()) return;
    const recovered = new TextDecoder('utf-8', {fatal:true}).decode(recoveredBytes);
    const matches = recovered === original;
    el('recovered').textContent = recovered;
    el('match').textContent = matches ? 'Exact match: Bob recovered Alice’s original message.' : 'Warning: the recovered message does not match.';
    el('match').className = matches ? 'rsa-success' : 'rsa-error';
    el('technical-output').textContent = JSON.stringify({algorithm:'RSA-2048 / OAEP / SHA-256', engine:'Browser Web Crypto', ciphertext_base64:base64(ciphertext), recovered, recovery_matches:matches}, null, 2);
    status(matches ? 'Bob read the message. The public key encrypted; the private key decrypted.' : 'Recovery mismatch.', !matches);
  }));
  el('python').addEventListener('click', () => operation(async current => {
    const input = bytes();
    if (!input.length || input.length > 190) throw Error('Enter a message between 1 and 190 UTF-8 bytes.');
    const controller = new AbortController(); pythonController = controller;
    const timer = setTimeout(() => controller.abort(), 15000);
    el('python-output').textContent = 'Running the separate Python self-test…';
    try {
      const response = await fetch('/api/tasks/rsa/run', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({message:el('message').value}), signal:controller.signal});
      const data = await response.json();
      if (!current()) return;
      if (!response.ok) throw Error(data.error || 'Python self-test failed.');
      el('python-output').textContent = JSON.stringify(data, null, 2);
      status('Python self-test complete. It uses its own keys, separate from Bob’s browser demo.');
    } catch (error) {
      if (current()) el('python-output').textContent = 'No result. Check the connection and try again.';
      throw error;
    } finally { clearTimeout(timer); if (pythonController === controller) pythonController = null; }
  }));
  el('reset').addEventListener('click', reset);
  el('message').addEventListener('input', () => {
    invalidate(); clearMessage(); controls();
    status(keys ? 'Message changed. Encrypt it again to send a fresh ciphertext.' : 'Generate Bob’s keys first.');
  });
  function navigate() {
    section.hidden = !active();
    if (!active()) reset();
    else {
      controls();
      if (!globalThis.crypto?.subtle) status('This browser needs HTTPS or localhost for Web Crypto. The Python self-test is still available below.', true);
    }
  }
  document.addEventListener('enigma:navigate', navigate);
  reset(); navigate();
})();
