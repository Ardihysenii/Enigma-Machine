# November 10, 2026 portal and design checks

- Full regression suite: **67 tests passed**, including existing cryptography, cipher presentation, college policy and hosting tests.
- New PostgreSQL tests used a unique temporary schema in Neon, removed after testing. Covered signup restricted to students, password/session token hashing, signin/signout and replay of revoked tokens, CSRF enforcement, admin role assignment and session revocation, two-course professor restrictions, own-student visibility, grade validation, audit permissions, expiry, and isolation from Task 01 switches.
- Actual enigma_portal migration applied separately; starter administrator signin and administration access verified through the local Flask application connected to Neon. No integration-test students/grades were added to the actual portal schema.
- JavaScript syntax checks passed for portal.js, app.js and college.js. Desktop/mobile static render review completed for the new account page and lab overview/cipher layout. Static render fixtures do not constitute browser end-to-end interaction tests.
- No Vercel deployment/status checks performed. User confirmed the Production database variable was saved. Hosted account flow not yet verified.
- Earlier check records follow.

# ENIGMA verification — 8 November 2026

## Executed locally

- `.venv\Scripts\python.exe -m unittest discover -s tests -v`: **34 tests passed**, 19.474 seconds, exit code 0 on final run. Output saved under `.logs/functional-tests.txt` (ignored by version control). PowerShell labels unittest's stderr progress stream as NativeCommandError text; the Python process itself exited successfully with `OK`.
- `node --check static/app.js`: exit code 0.
- `.venv\Scripts\python.exe -m py_compile app.py services.py`: exit code 0.
- Installed `cryptography==46.0.3` in the project's existing `.venv`; dependency recorded in requirements.txt.

## Functional coverage

- Analysis required fields, three-threat validation, save/update/load, browser-session isolation, restoration after clearing runtime state.
- Known Caesar/Vigenere vectors, negative/wrapped shifts, non-ASCII/punctuation policy, inverse recovery metadata and key/operation validation.
- Actual RSA-OAEP round trips, wrong-key rejection, ciphertext size and 190-byte UTF-8 boundary.
- Actual RSA-PSS/SHA-256 verification: original valid, altered document invalid, wrong public key invalid; independent signature/hash checks.
- Protected PKCS #8 and PKCS #12 independently reloaded with the supplied password; matching key/certificate; wrong-password rejection; session-isolated and expired downloads; password not written to returned JSON/artifacts.
- Regression fixed: internal wrong-password test now uses ASCII-safe encoded bytes, avoiding a library error on invalid UTF-8.
- Token enrollment/PIN validation, identity/PIN rejection, valid signed challenge, altered/wrong-key rejection, one-use challenge/expiry/replacement, five-failure lockout, audit persistence/isolation and credential exclusion.
- Infrastructure routes, headers, trusted hosts, loopback and origin restrictions, malformed/type/size validation and invalid Unicode rejection.

Tests use temporary storage, not actual laboratory credentials or existing user records. Restart behavior is simulated by clearing the server's runtime state while retaining the browser cookie; a separate-interpreter restart was not independently exercised by this suite.

## Browser smoke checks

Verified on the local loopback server at a 1536x816 desktop viewport:
- Existing navigation and workspace structure retained.
- Caesar HELLO with key 3 returned KHOOR through the form.
- RSA and signature controls returned library-generated results.
- Structured analysis save and load requests both returned HTTP 200.
- Packaging controls produced three download links: encrypted private-key PEM, PKCS #12 and test certificate. The password field was cleared on submission. Artifact contents/download access were validated independently in automated tests.
- Token enrollment, fresh challenge and authentication produced authenticated=true, signature_verified=true, and three real audit events in the rendered response panel.

Some browser rendered-page reads failed intermittently; the authentication result was confirmed by reading the rendered response element directly. Negative authentication cases were covered by automated tests, not each repeated manually in the browser. No mobile-device test was executed.

## Preserved scope / remaining work

No redesign: sidebar, grid, cards, colors and breakpoints retained. New fields are inside the existing form; CSS was extended only to apply existing form appearance to text/password inputs. Placeholder status copy was updated to reflect implemented operations.

Local laboratory only. Authentication is software simulation, not a hardware smart card or PKCS #11 integration. Certificates are self-signed test certificates. Analysis/audit JSON are not encrypted or tamper-proof. Token credentials/private keys do not survive server restart; encrypted artifacts do. One current analysis is stored per browser session, not a version history.

Report, screenshots, contribution records and other submission documents are not created. No Git repository exists in this folder; no commit/push or deployment was performed. Restart any old server using Start ENIGMA.cmd before using the updated Python implementation.


## Task 01 college dashboard connection — 8 November 2026

- Registered the existing college blueprint and shared the active app state/lock through Flask extensions to avoid a second app import when launched as a script.
- Added Task 01 policy panel, rule switches, apply/reload controls, and separate dashboard link. Main dashboard layout retained.
- Full suite: **45 tests passed**, 22.084 seconds, exit 0, including 11 new college tests. JavaScript syntax checks for app.js, college.js and policy.js returned no errors.
- New tests cover unprotected access, own-grades restrictions, professor API/page denials, professor access, independent controls, disabling controls, policy persistence/session isolation, audit evidence, invalid input, corrupt policy fail-closed and logout.
- Separate live HTTP verification against the updated server on port 5002: college page 200; student initially saw 6 rows and professor API 200; after applying both rules student saw only 2 own rows, other-student grades 403, professor API 403 and professor page 403; professor identity retained API 200. Ten audit events were present. Verification used its own cookie session, then disabled both rules and logged out in that test session.
- Browser tabs opened, but rendered-page inspection repeatedly failed with “could not be opened for reading”. Visual appearance and end-to-end UI clicks were therefore **not confirmed** in this run. HTTP and automated checks do not substitute for visual review.
- Ports 5000/5001 responded with older/unconnected apps during this run. Updated instance launched explicitly from this folder on port 5002. Standard launcher remains port 5000; stop old instances before using it.


### Follow-up: identity selection and live synchronization
User-reported access issue reproduced as a misleading identity selector: signed-in professor retained all-grade access while the selector showed Arta. Updated selector to log in on change and mirror active identity; successful data responses name the actor and role. Task 01 sends BroadcastChannel/storage invalidation notices after confirmed policy writes; college re-fetches server state, with 2-second polling fallback and existing focus/visibility refresh. Added script version query strings. Browser confirmed Arta login, all-grade access with rules off, automatic own-grade filtering after rules enabled without reloading college, and professor-area HTTP 403. Left Arta signed in and both rules enabled for demonstration. Earlier browser-inspection limitation was resolved through targeted queries/actions. Added Start ENIGMA College.cmd for port 5002.


## Expanded Task 01 — six security controls

- User approved four additions: block student grade edits, professor assigned-course scope, 30-second inactivity expiry, and professor-only college audit. Existing two rules retained.
- Old analysis form generation removed and generic workspace/next-step cards hidden only on Task 01. Existing saved analysis JSON and legacy API retained; 02–06 workspaces untouched.
- Backend tests: **54 passed**, 20.675 seconds, TEST_EXIT=0. Includes 20 college tests. app.js, college.js and policy.js syntax checks returned no errors.
- Nine added regression cases cover real grade mutations/denials, own-grade write boundary, assigned-course reads and writes, audit restrictions, timeout despite polling, renewal by explicit activity, grade validation/all-six mode, legacy-policy migration and grade-session isolation.
- Browser checks: six switches visible; old workspace hidden. Student changed fictional grade 9 to 10 with edit control off; after applying all six, the same UI returned HTTP 403 for grade editing and audit. Live cross-tab panel showed 6/6 controls.
- Grade data is per-session and in-memory, not permanent college records. Policies/audit persist, identity selection remains a simulation.

- Live-server isolated-session verification: student edit 200 before protection, 403 after; student audit 403; professor assigned rows 3; wrong-course edit 403; correct-course edit 200; professor audit 200. After 31.2 seconds with repeated status polling, resource request returned 401 and session_expired=true.
- Further browser confirmation: professor wrong-course grade edit returned 403, professor audit returned 200; student view restored with own-grade scope. Task 02–06 regression coverage passed in the automated suite; the additional targeted browser form query was inconclusive. All six rules left on in user demo session; inactivity expiry is expected after 30 seconds.


## Campus redesign and five-student roster — 8 November 2026

- Replaced current student names with Ardi, Arditi, Donarti, Albi, Enes. Added s004/s005 to backend roster, grade records, read validation and grade-edit validation; all selectors updated. Professors unchanged.
- Redesigned only the college dashboard: navy navigation rail, white/blue cards, academic header, profile/identity card, security checklist, local initial avatars and refined grade table. Main ENIGMA dashboard design unchanged.
- Three summary metrics are computed from currently returned grade rows only; cleared for denied/expired/logged-out/error states and audit view.
- Final regression run: **55 tests passed**, 14.201 seconds. JavaScript syntax check returned no errors. Initial two runs exposed outdated test expectations (six grade rows vs ten, and accidental rule-count expectation); test assertions corrected, not backend authorization weakened. New test validates all five names plus Albi/Enes read/edit/own-grade restrictions.
- Live server restarted on port 5002. Status API confirmed five named students and two professors. Browser confirmed Enes login, all five names in selectors/table, 10 visible records, 2 courses and average 8.9 in unrestricted view. Desktop screenshot reviewed at 1536x816. Mobile CSS included; no physical/mobile viewport test performed.


## Single-course / single-professor editorial redesign — 8 November 2026

- User explicitly chose removal of Programming and second professor rather than a consolidated multi-course table. Removed course and p002 from backend and interface. Five students now have one row each; professor p001 renamed Profesori. Cross-course demonstration limitation was explained and noted in UI.
- Replaced the blue sidebar design with graphite/ivory/champagne horizontal navigation, editorial serif headings, thin gold accents, consolidated dark metrics strip and square-edged working panels. Main ENIGMA visual design unchanged.
- Final automated run: **55 tests passed**, 20.503 seconds, TEST_EXIT=0. JavaScript syntax check passed. Single-course test verifies five unique student rows, one course, six identities, rejection of removed course (400), rejection of removed professor login (400), and authorized professor edits. Existing access/expiry/audit tests retained.
- Live status confirmed five students, one professor and only Siguria e informacionit. Browser confirmed Ardi login, one row per student, metric values 5 students / 1 course / average 8.6; desktop screenshot reviewed at 1536x816. No mobile viewport test executed.
- Server restarted on port 5002; existing policy/audit JSON retained. In-memory grade edits reset on restart as documented. Historical audit events may still reference the removed course/account; history was not deleted.
