'use strict';
(() => {
  const overview = document.getElementById('overview');
  if (!overview) return;
  const preference = matchMedia('(prefers-reduced-motion: reduce)');
  const motion = document.getElementById('ov-motion');
  const reveal = document.getElementById('ov-reveal');
  const message = document.getElementById('ov-message');
  const caption = document.getElementById('ov-caption');
  const status = document.getElementById('ov-status');
  const plain = 'EVERY MESSAGE HAS A STORY';
  const encrypted = plain.replace(/[A-Z]/g, c => String.fromCharCode((c.charCodeAt(0) - 65 + 3) % 26 + 65));
  let paused = preference.matches;
  let decoded = false;
  let timer;
  function setMotion() {
    overview.classList.toggle('ov-paused', paused);
    motion.textContent = paused ? 'Resume motion' : 'Pause motion';
    motion.setAttribute('aria-pressed', String(paused));
  }
  function finish() {
    clearInterval(timer);
    message.textContent = decoded ? plain : encrypted;
    reveal.disabled = false;
  }
  motion.addEventListener('click', () => { paused = !paused; setMotion(); finish(); });
  preference.addEventListener('change', () => { paused = preference.matches; setMotion(); finish(); });
  reveal.addEventListener('click', () => {
    decoded = !decoded;
    const target = decoded ? plain : encrypted;
    reveal.textContent = decoded ? 'Reset signal ↺' : 'Reveal the message →';
    caption.textContent = decoded ? 'A shift of −3 reveals the message. Explore the full Python cipher workspace below.' : 'Caesar / shift +3 · A small browser-only preview, not a Python operation.';
    status.textContent = decoded ? 'Decoded message: ' + plain : 'Ciphertext restored.';
    if (paused || preference.matches) { finish(); return; }
    let step = 0;
    reveal.disabled = true;
    clearInterval(timer);
    timer = setInterval(() => {
      step++;
      message.textContent = [...target].map((c, i) => c === ' ' || i < step ? c : String.fromCharCode(65 + Math.floor(Math.random() * 26))).join('');
      if (step >= target.length) finish();
    }, 32);
  });
  function syncVisibility() {
    overview.classList.toggle('ov-paused', paused || document.hidden || overview.hidden);
    if (document.hidden || overview.hidden) finish();
  }
  document.addEventListener('visibilitychange', syncVisibility);
  document.addEventListener('enigma:navigate', syncVisibility);
  const sections = overview.querySelectorAll('.heading-row,.notice,.stats,.ov-signal,.task-card,.info-card');
  const observer = new IntersectionObserver(entries => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        if (!paused && !preference.matches) entry.target.classList.add('ov-enter');
        observer.unobserve(entry.target);
      }
    });
  }, {threshold: .08});
  sections.forEach((section, index) => {
    section.style.setProperty('--ov-delay', `${Math.min(index % 3 * 80, 160)}ms`);
    observer.observe(section);
  });
  message.textContent = encrypted;
  setMotion();
  syncVisibility();
})();
