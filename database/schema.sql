-- Additive ENIGMA portal migration. Existing schemas and data are not removed.
CREATE SCHEMA IF NOT EXISTS enigma_portal;
CREATE TABLE IF NOT EXISTS enigma_portal.schema_versions (
  version integer PRIMARY KEY,
  applied_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS enigma_portal.users (
  id uuid PRIMARY KEY,
  name varchar(100) NOT NULL,
  email varchar(254) NOT NULL UNIQUE,
  password_hash text NOT NULL,
  role varchar(16) NOT NULL DEFAULT 'student' CHECK (role IN ('student','professor','admin')),
  active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS enigma_portal.sessions (
  token_hash char(64) PRIMARY KEY,
  user_id uuid NOT NULL REFERENCES enigma_portal.users(id) ON DELETE CASCADE,
  created_at timestamptz NOT NULL DEFAULT now(),
  last_seen timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL
);
CREATE INDEX IF NOT EXISTS portal_sessions_user ON enigma_portal.sessions(user_id);
CREATE INDEX IF NOT EXISTS portal_sessions_expiry ON enigma_portal.sessions(expires_at);
CREATE TABLE IF NOT EXISTS enigma_portal.courses (
  id uuid PRIMARY KEY,
  code varchar(24) NOT NULL UNIQUE,
  title varchar(160) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS enigma_portal.teaching_assignments (
  user_id uuid NOT NULL REFERENCES enigma_portal.users(id) ON DELETE CASCADE,
  course_id uuid NOT NULL REFERENCES enigma_portal.courses(id) ON DELETE CASCADE,
  PRIMARY KEY (user_id, course_id)
);
CREATE TABLE IF NOT EXISTS enigma_portal.enrollments (
  student_id uuid NOT NULL REFERENCES enigma_portal.users(id) ON DELETE CASCADE,
  course_id uuid NOT NULL REFERENCES enigma_portal.courses(id) ON DELETE CASCADE,
  enrolled_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (student_id, course_id)
);
CREATE TABLE IF NOT EXISTS enigma_portal.grades (
  student_id uuid NOT NULL,
  course_id uuid NOT NULL,
  grade integer NOT NULL CHECK (grade BETWEEN 5 AND 10),
  updated_by uuid NOT NULL REFERENCES enigma_portal.users(id),
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (student_id, course_id),
  FOREIGN KEY (student_id,course_id) REFERENCES enigma_portal.enrollments(student_id,course_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS enigma_portal.audit_events (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  timestamp timestamptz NOT NULL DEFAULT now(),
  actor_id uuid REFERENCES enigma_portal.users(id) ON DELETE SET NULL,
  actor_name varchar(100) NOT NULL,
  action varchar(80) NOT NULL,
  allowed boolean NOT NULL,
  target varchar(254)
);
CREATE INDEX IF NOT EXISTS portal_audit_time ON enigma_portal.audit_events(timestamp DESC);
CREATE TABLE IF NOT EXISTS enigma_portal.login_limits (
  key_hash char(64) PRIMARY KEY,
  failures integer NOT NULL DEFAULT 0,
  window_started timestamptz NOT NULL DEFAULT now(),
  locked_until timestamptz
);
INSERT INTO enigma_portal.schema_versions(version) VALUES(1) ON CONFLICT DO NOTHING;

-- Task 01 is a fictional educational lab: globally persisted controls; short idle-timeout demo defaults OFF.
-- This is additive; apply explicitly alongside deployment, never from a request.
CREATE TABLE IF NOT EXISTS enigma_portal.lab_policy (
  singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
  rules jsonb NOT NULL CHECK (jsonb_typeof(rules) = 'object'),
  revision bigint NOT NULL DEFAULT 1 CHECK (revision >= 1),
  updated_at timestamptz NOT NULL DEFAULT now()
);
INSERT INTO enigma_portal.lab_policy(singleton,rules) VALUES(true,
  '{"student_own_grades_only":true,"block_student_professor_area":true,"block_student_grade_edit":true,"professor_assigned_courses_only":true,"session_inactivity_timeout":false,"audit_professor_only":true}'::jsonb)
ON CONFLICT DO NOTHING;
INSERT INTO enigma_portal.schema_versions(version) VALUES(2) ON CONFLICT DO NOTHING;


-- Version 3: persistent Task 06 software tokens. Also applied additively by the backend.
CREATE TABLE IF NOT EXISTS enigma_portal.software_tokens (
  user_id uuid PRIMARY KEY REFERENCES enigma_portal.users(id) ON DELETE CASCADE,
  public_key text NOT NULL,
  private_key_encrypted text NOT NULL CHECK (private_key_encrypted LIKE '-----BEGIN ENCRYPTED PRIVATE KEY-----%'),
  pin_hash text NOT NULL,
  status varchar(16) NOT NULL DEFAULT 'active' CHECK (status IN ('active','locked','revoked')),
  failures integer NOT NULL DEFAULT 0 CHECK (failures >= 0),
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS enigma_portal.token_pending (
  ticket_hash char(64) PRIMARY KEY,
  user_id uuid NOT NULL REFERENCES enigma_portal.users(id) ON DELETE CASCADE,
  expires_at timestamptz NOT NULL
);
CREATE INDEX IF NOT EXISTS token_pending_user ON enigma_portal.token_pending(user_id);
CREATE TABLE IF NOT EXISTS enigma_portal.token_challenges (
  id uuid PRIMARY KEY,
  user_id uuid NOT NULL REFERENCES enigma_portal.users(id) ON DELETE CASCADE,
  context_hash char(64) NOT NULL,
  nonce varchar(64) NOT NULL,
  expires_at timestamptz NOT NULL
);
CREATE INDEX IF NOT EXISTS token_challenge_context ON enigma_portal.token_challenges(user_id,context_hash);
-- Verified session provenance avoids changing/deleting any pre-existing sessions.
CREATE TABLE IF NOT EXISTS enigma_portal.token_verified_sessions (
  token_hash char(64) PRIMARY KEY REFERENCES enigma_portal.sessions(token_hash) ON DELETE CASCADE
);
INSERT INTO enigma_portal.schema_versions(version) VALUES(3) ON CONFLICT DO NOTHING;


-- Version 4: persisted fictional signed course notices. Also applied lazily by notice routes.

CREATE TABLE IF NOT EXISTS enigma_portal.course_notices (
  id uuid PRIMARY KEY,
  course_id uuid NOT NULL REFERENCES enigma_portal.courses(id),
  teacher_id uuid NOT NULL REFERENCES enigma_portal.users(id),
  request_id uuid NOT NULL,
  request_hash char(64) NOT NULL,
  course_code varchar(24) NOT NULL,
  teacher_name varchar(100) NOT NULL,
  title varchar(160) NOT NULL,
  published_at timestamptz NOT NULL,
  payload jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
  signature text NOT NULL,
  public_key text NOT NULL,
  public_key_fingerprint char(64) NOT NULL,
  algorithm text NOT NULL,
  UNIQUE(teacher_id,request_id)
);
CREATE INDEX IF NOT EXISTS course_notices_course_time ON enigma_portal.course_notices(course_id,published_at DESC,id DESC);

INSERT INTO enigma_portal.schema_versions(version) VALUES(4) ON CONFLICT DO NOTHING;
