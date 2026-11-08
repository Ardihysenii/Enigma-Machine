# ENIGMA — local cryptography laboratory

The six task areas are implemented and connected to the existing dashboard, with Task 01 using a live college security-control panel. The sidebar, page structure, cards, colors and responsive layout are retained. Task-specific inputs have been added inside the existing workspace form.

## Start on Windows

1. Close any older ENIGMA server console with Ctrl+C. Python does not reload these changes automatically.
2. Double-click **Start ENIGMA.cmd** and keep its window open.
3. Open http://127.0.0.1:5000 and refresh the page.

Or run from this directory:

```powershell
.\.venv\Scripts\python.exe app.py
```

For a new installation:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

The application is deliberately loopback-only, debug off. Flask's development server is not a production service. If the browser says **Older server**, stop the previous console and relaunch. A successful syntax check or test run does not itself start the updated server.

## Operations

### 1. Security requirements — six direct college controls

Task 01 now contains only the live security panel. The old written-analysis form and its result/requirements cards are hidden for Task 01; Tasks 02–06 retain their workspaces. Previously saved analysis JSON is not deleted, and the legacy analysis API remains compatible.

Open **Start ENIGMA College.cmd** for the connected app at http://127.0.0.1:5002/#analysis and its separate college page at http://127.0.0.1:5002/college. Both pages must use the same origin and browser session. Choose switches and click **Apply security rules**; Select all/Deselect all only prepares the switches. Cross-tab signals trigger fresh server reads, with two-second polling as fallback.

The six independently switchable Python controls are:

1. **Own grades:** students read only their own records; explicit other-student/all requests return 403. Also prevents editing another student's records.
2. **Professor area:** students cannot access the professor page or its data endpoint.
3. **Grade integrity:** students cannot change any grade. With this rule off, a selected student can change fictional grades unless the own-grades rule blocks that target.
4. **Assigned courses:** professors can read/edit only their assigned course. Profesori Demo has Siguria e informacionit; Profesorja e Programimit has Programim. Applies to both grade-read endpoints and writes.
5. **Inactivity expiry:** selected identity expires after 30 seconds without explicit college resource operations. Status/policy polling does not renew it. Expired read/write/audit operations return 401; press Hyr / kyçu përsëri to reselect the identity. The deadline is enforced on the server; the display shows a countdown. This short duration is a lab demonstration, not a production recommendation.
6. **Audit access:** only a selected professor can read the college audit endpoint. With it off, a selected student can also read audit. Attempts are recorded locally, including denied edits/access and expiry. Latest 100 events per session are retained; audit files are not tamper-proof.

The college has Grades, Professor area, Change grade, and Audit tabs. Identity selection logs in immediately and is deliberately operator-controlled, not real password authentication. Grade changes are real changes to isolated in-memory fictional records; they reset on server restart/runtime expiry. Grades accept integers 5–10 only. Policy and audit persist locally; known legacy two-rule policies migrate while retaining their settings and leaving the four new rules off. All six switches on means 6/6 active—not a security certification. Use fictional data only.

### 2. Classical cipher
Choose Caesar or Vigenere, Encrypt or Decrypt, enter a key and message. Caesar takes an integer (negative and wrapped shifts supported); Vigenere takes A-Z letters. ASCII letters become uppercase. Other characters, including spaces, punctuation and non-ASCII letters, stay unchanged and do not advance the key.

Results include plaintext, ciphertext, inverse round trip, recovery check, and per-letter modulo-26 calculations. Recovery is against the normalized uppercase-ASCII input, not the original letter case. These ciphers are educational only.

### 3. RSA
Run a short-message round trip with a fresh disposable RSA-2048 key and OAEP/SHA-256. The maximum is **190 UTF-8 bytes**, not 190 characters. Outputs include ciphertext, recovered text, exact recovery and an actual wrong-key rejection check. Private keys are neither saved nor returned. This is not arbitrary-file encryption or an independently persistent encrypt/decrypt key vault.

### 4. Signatures
Run RSA-PSS/SHA-256 signing with a fresh disposable key. The original document verifies; an altered document and an unrelated public key are actually checked and rejected. The signature and document hash are displayed, not the private key. Signing is not encryption, and matching a key does not independently establish identity.

### 5. Protected keys and certificates
Enter a **disposable** laboratory password of 12–128 characters in the designated password field. Run to generate a fresh key, encrypted PKCS #8 PEM, password-protected PKCS #12 bundle and a seven-day self-signed test certificate. Download links appear in the response panel.

Python reloads both protected formats with the supplied password, checks key/certificate recovery, and tests wrong-password rejection. No unencrypted private-key artifact is written. Passwords are not saved or returned; the form clears the password on submission. Keep your disposable password locally if you want to reopen the files. Download links require the originating browser session and expire when the server restarts or its in-memory session expires. Encrypted artifacts remain on disk until you remove them.

The certificate is laboratory-only, not a trusted CA-issued identity. PKCS #1, #8, #11 and #12 distinctions appear in the result. PKCS #11 hardware integration is not implemented.

### 6. Simulated token authentication
1. Choose **Enroll**, enter a fictional identity and a disposable 4–12 digit PIN, and run. One simulated token may be enrolled per active session.
2. Choose **Issue fresh challenge** and run. Challenges expire after 60 seconds.
3. Choose **Authenticate**, enter the same fictional identity and PIN, and run. PIN fields clear on every submission, so re-enter when needed.
4. To test failures, request a new challenge, then use a wrong identity/PIN or select the altered-challenge/wrong-public-key test.
5. Choose **View session audit records** to inspect recorded outcomes.

Each challenge is consumed on every authentication attempt, preventing replay. Five consecutive failed identity/PIN or signature checks lock the simulated token. Restart resets enrollment/lockout because the private key and PIN hash exist only in server memory. Inactive in-memory sessions expire after one hour. Audit records contain timestamps, event types and results, not PINs or private keys; only the latest 100 are retained per session and saved locally.

This is a software simulation: no secure element, real smart card, hardware PIN boundary, trusted identity provider, tamper-proof audit storage or production authorization system is provided.

## Safety and storage

- Use fictional content and disposable credentials only. Never enter real passwords, PINs, private keys, student records or other personal data.
- Established `cryptography` library operations are used for RSA, signatures and serialization.
- Private key/PIN objects stay on the server. Credential input fields are password-masked and cleared after submission. Request bodies and credentials are not deliberately logged.
- `lab-material/` is excluded by `.gitignore` and contains the local session secret, plaintext fictional analyses/audit records and encrypted key artifacts. Do not submit or share that directory. It is not an OS-encrypted vault; anyone with access to the Windows account/files may inspect it.
- Loopback-only request validation, trusted hosts, same-origin POST checks, strict/HTTP-only session cookies, CSP and no-store responses reduce common browser risks. They do not make a local laboratory a production security product.
- When finished, stop Python and remove unneeded laboratory artifacts locally. Deleting all `lab-material/` files resets saved analyses, audit records and browser associations as well as artifacts.

## Checks

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
node --check static/app.js
```

See `CHECKS.md` for actual verification results. The report, screenshots, contribution records and other submission documents are not generated by the application. Functional tests cover the implemented behavior; they are not a security certification.


## College dashboard design and roster

The college page uses a graphite, ivory and champagne editorial design with horizontal navigation, serif headings and a consolidated metrics strip. The main ENIGMA design is unchanged.

There are exactly six selectable identities: Ardi (s001), Arditi (s002), Donarti (s003), Albi (s004), Enes (s005), and Profesori (p001). Programming and p002 have been removed from active data and selectors. Each student has one fictional grade for Siguria e informacionit, so the unrestricted table shows five unique students once each; own-grade view shows one. This simplification was explicitly approved by the user after explaining the loss of a second-course comparison.

Metrics are derived only from grade rows returned for the current view, not hidden or unauthorized records. They clear on denial, logout, expiry or connection failure. Avatars use local initials. Responsive CSS is included, with no external fonts or image services.


## Vercel: public fictional-data demo

Vercel automatically detects `app.py` and exposes the Flask app. When `VERCEL=1`,
ENIGMA uses the platform temporary directory (`/tmp/enigma-lab`), permits remote
requests only on the exact platform-provided deployment/production hostnames,
and uses HTTPS-only session cookies. Same-origin POST validation, CSP, input
limits, per-browser separation and local-mode loopback restrictions remain.
For a custom domain set `ENIGMA_PUBLIC_HOST` to the bare hostname.

Recommended: set `ENIGMA_SECRET_KEY` to a randomly generated secret of at least
32 characters in Vercel Environment Variables, then redeploy. Never commit it.
Without it, a fresh cryptographically random key is used per process: cold
starts/instance changes invalidate browser sessions. Even with a stable secret,
state is still **temporary and instance-local**, not shared durable storage.

This deployment is a disposable learning demo, NOT a real college portal. All
identities are freely selectable. Grades, policy, audits, token enrollment,
challenges and download registrations may reset or differ across instances.
A token challenge may be lost between requests; re-enroll/retry or use the local
application for a consistent full presentation. Downloads may become unavailable.
Do not enter real data or credentials. Durable cross-instance behavior requires
an external state store and a deliberate security design; `/tmp` does not supply it.

Local launchers retain their original on-disk storage and loopback-only behavior.
