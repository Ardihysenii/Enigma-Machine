# Guided signed course notices

Open College → Signed notices, or the lab’s Digital Signatures section. Both use the same noticeboard.

## Present the demonstration

1. Sign in as a fictional teacher assigned to a course. Choose that course, write a fictional notice and use a made-up signature/doodle. Sign & publish saves a new original for enrolled students. No existing notice is modified.
2. Sign in as a student enrolled in that course and open Signed notices. Choose the notice. It starts “Not checked yet”; readable text is not proof of a valid signature.
3. Verify the signed original. The server checks its stored signature against its stored public key using RSA-2048/PSS/SHA-256 with a 32-byte salt.
4. Change 10:00 to 12:00 in the temporary copy, or change its drawing, then verify that copy. The same signature fails because the content changed. No test edits are saved.
5. Test an unrelated public key: real signature verification fails. Restore the original copy, verify again, and it succeeds.

Expandable presenter hints explain each step. The technical evidence includes the original content, signature and public key, not private keys or credentials.

## Security and trust boundary

Only professors assigned to the course can publish. Professors read assigned-course notices; students read and verify enrolled-course notices. Administrators and anonymous visitors cannot use these routes. These rules ignore the educational grade-policy switches. Existing session and CSRF checks protect the endpoints. Verification reads the authoritative stored signature/key; readers cannot supply replacements. Client test copies contain only modified text/drawing, never metadata overrides.

The signature binds the notice ID, course ID/code, teacher account ID/name, title, publication timestamp, exact document and drawing through a domain-separated canonical JSON envelope. A fresh disposable key pair is generated for each newly published notice. The private key is never serialized or stored and its reference is discarded after signing; Python cannot guarantee physical RAM zeroization. Public keys and signatures remain to verify saved notices across refreshes/workers.

A valid signature establishes integrity and a key relationship, not independent real-world identity. The portal records the authenticated publisher as application provenance. Account compromise, database-owner replacement of the entire notice/key, or misleading self-registered teacher identities are outside this educational trust model. No certificate authority or official/legal identity signature is implemented. Signing does not encrypt the notice. Use fictional data only.

Published originals have no update/delete API. This is application immutability, not a database-admin-proof audit log. Retrying the same publish request ID with identical normalized content returns the original notice; changed content under the same ID is rejected. The UI retains the request ID across network-error retries. The list shows the newest 100 matching notices; Refresh notices loads new publications.

## Setup and tests

Notice routes add only schema version 4: course_notices, its index, and a version marker, under the existing configured PostgreSQL search_path. Setup uses a transaction advisory lock and recheck, never a process cache. Existing accounts, tokens, grades and courses are not altered. The application database role needs CREATE on its portal schema for automatic setup. An operator who forbids runtime DDL can apply the additive version-4 block in database/schema.sql instead. Notice setup is not called from every portal request.

Run the existing Python suite and Node frontend tests, including tests/test_course_notices.py and tests/course_notices.cjs. A real PostgreSQL persistence/locking test is opt-in via ENIGMA_NOTICE_TEST_DSN and must point only to an explicitly disposable database, never the production Neon connection. Mock API tests do not prove live database privileges or full browser interaction.
