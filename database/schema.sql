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
