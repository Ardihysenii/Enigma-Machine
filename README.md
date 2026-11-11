# ENIGMA — local cryptography laboratory

## Unified college portal and Task 01

`/college` is the only college dashboard. It provides signup/signin with fictional accounts. Signup offers Student or Teacher (stored internally as professor); administrator registration is never public. This is deliberately an unverified teacher self-registration lab, not a real college access model. Sign-in uses the saved account role, not a client-selected privilege. Old `/college/demo` and professor pages redirect to `/college`; the identity-switching APIs return HTTP 410 and cannot change records.

Task 01 now controls this same signed-in portal. Its six switches are shared across all accounts and stored in PostgreSQL. The five access-control protections default to ON; the optional 30-second idle-timeout demonstration defaults to OFF. Existing saved policies are not silently overwritten by schema setup. Turning a switch off intentionally permits the corresponding insecure behavior on saved fictional grades. Anyone operating the lab panel can change this demonstration policy; this is deliberately not a production access model. Never use real student data.

The six controls restrict student reads to their own records, block student professor-area access, block student grade edits, restrict professors to assigned courses, enforce a 30-second inactivity timeout, and restrict audit access to professors/admins. The own-record rule independently limits student edits even when grade editing is enabled. Background policy/dashboard polling does not refresh activity. Sessions persist for 30 days and renew on real authenticated activity. Typing, clicking and scrolling send throttled CSRF-protected activity updates; background polling never renews a session. With the explicit idle-timeout demo ON, 30 seconds of genuine inactivity still expires the session. Expired or revoked tokens are never restored. Sign-in, CSRF, role changes and administrator management cannot be disabled by Task 01.

Accounts, enrollments, grades, policy and audit persist in the `enigma_portal` schema. New students have no invented courses or grades: a teacher can create a course (automatically assigned to them), enroll an existing student by account email in their own course, and save grades from Grades. Administrators can also create courses, enroll students and assign teachers. Existing courses still need an explicit assignment before a newly registered teacher can manage their roster. Teachers can select an existing unassigned course themselves; another teacher’s assignments are never silently claimed. The portal includes Overview, Grades, Courses, Professor area, Access history and administrator views. Grade changes accept integers 5–10. Grade changes with controls off are real persisted changes to fictional data, not a visual simulation.

### Setup and updates

Set `ENIGMA_DATABASE_URL` server-side to the Neon PostgreSQL connection string. Never commit its value. Install requirements and run `python scripts/setup_portal.py` to apply additive migrations, including the shared policy table, without resetting accounts or grades. For first-administrator setup, add `--admin-email admin@example.test --credentials-file C:\private\enigma-admin.txt` using a new private path outside the repository. Existing administrators are not reset.

Run `python -m unittest discover -s tests -v`; set `ENIGMA_TEST_DATABASE_URL` for integration checks in a unique disposable schema. Test schemas are removed after testing; tests must never use the real portal schema.

On Windows, use **Start ENIGMA.cmd**, or create a virtual environment, install `requirements.txt` and run `python app.py`. Local service is loopback-only with debug disabled. Stop and restart an older server after code changes. **Start ENIGMA College.cmd** offers the same app on port 5002.

Task 06 remains a separate disposable software smart-card simulation. Email verification and password recovery are not implemented. Crypto-lab files and keys keep the temporary/local-storage limitations described below. All six controls being active is a demonstration state, not a security certification.

## Operations

### 1. Security requirements

Open `/#analysis`, prepare switches, then click **Apply security rules**. Select all/Deselect all only prepares a selection. Open `/college`, sign in and test the same grade operation before and after changing its control. Policy updates synchronize across tabs with polling as a fallback. A control is proven by an actual request and recorded before/after result, not its checkbox state. For normal use, leave the timeout demo OFF and the other five protections ON.

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

### Teacher and student workspaces
Teachers land directly on their gradebook. The gradebook provides existing database student selection, assigned-course enrollment, add/update grade rows, new course creation and explicit connection to unassigned existing courses. Students land on their own dashboard, receive no teacher directory, and read grade rows filtered by the active security policy. Turning an access-control switch off intentionally demonstrates its corresponding insecure behavior on fictional records. Policy changes invalidate stale displayed records and reload current authorization even during an edit.
