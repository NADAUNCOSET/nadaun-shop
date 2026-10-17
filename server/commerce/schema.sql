CREATE TABLE IF NOT EXISTS shop_orders (
  id TEXT PRIMARY KEY,
  customer_hash TEXT NOT NULL,
  request_key TEXT NOT NULL,
  fingerprint TEXT NOT NULL,
  state TEXT NOT NULL CHECK(state IN ('REQUESTED','APPROVED','PAYMENT_PENDING','CONFIRMING','PAID','PAYMENT_REVIEW','CANCELED')),
  customer_cipher TEXT NOT NULL,
  lines_json TEXT NOT NULL,
  subtotal INTEGER,
  shipping INTEGER NOT NULL CHECK(shipping >= 0),
  total INTEGER,
  quote_version INTEGER NOT NULL DEFAULT 0,
  quote_expires INTEGER,
  payment_key TEXT UNIQUE,
  payment_provider TEXT,
  payment_auth_cipher TEXT,
  payment_receipt_cipher TEXT,
  paid_at INTEGER,
  payment_mode TEXT CHECK(payment_mode IN ('test','live')),
  confirm_key TEXT NOT NULL UNIQUE,
  fulfillment TEXT NOT NULL DEFAULT 'unfulfilled' CHECK(fulfillment IN ('unfulfilled','processing','shipped')),
  carrier TEXT,
  tracking TEXT,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  version INTEGER NOT NULL DEFAULT 0,
  UNIQUE(customer_hash,request_key)
);
CREATE INDEX IF NOT EXISTS shop_orders_customer ON shop_orders(customer_hash,created_at DESC);
CREATE INDEX IF NOT EXISTS shop_orders_state ON shop_orders(state,created_at DESC);
CREATE INDEX IF NOT EXISTS shop_orders_created ON shop_orders(created_at DESC,id DESC);
CREATE INDEX IF NOT EXISTS shop_orders_paid ON shop_orders(paid_at);
CREATE TABLE IF NOT EXISTS shop_order_events (
  id TEXT PRIMARY KEY, order_id TEXT NOT NULL REFERENCES shop_orders(id),
  actor TEXT NOT NULL, action TEXT NOT NULL, created_at INTEGER NOT NULL, version INTEGER NOT NULL,
  UNIQUE(order_id,version)
);
CREATE TABLE IF NOT EXISTS shop_rate_limits (
  key TEXT PRIMARY KEY, attempts INTEGER NOT NULL, expires_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS shop_rate_limits_expiry ON shop_rate_limits(expires_at);
CREATE TABLE IF NOT EXISTS shop_documents (
  order_id TEXT PRIMARY KEY REFERENCES shop_orders(id),
  kind TEXT NOT NULL CHECK(kind IN ('card_receipt','cash_receipt','tax_invoice')),
  status TEXT NOT NULL CHECK(status IN ('queued','processing','issued','retry','review','voided')),
  result_cipher TEXT NOT NULL,
  attempts INTEGER NOT NULL DEFAULT 0,
  next_attempt INTEGER NOT NULL DEFAULT 0,
  lease_until INTEGER NOT NULL DEFAULT 0,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  version INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS shop_documents_due ON shop_documents(status,next_attempt);
CREATE TABLE IF NOT EXISTS shop_calendar_sync (
  order_id TEXT PRIMARY KEY REFERENCES shop_orders(id),
  event_id TEXT NOT NULL UNIQUE,
  status TEXT NOT NULL CHECK(status IN ('pending','synced','canceled','review','error','ignored')),
  fingerprint TEXT,
  event_url TEXT,
  error_code TEXT,
  order_version INTEGER NOT NULL DEFAULT -1,
  next_attempt INTEGER NOT NULL DEFAULT 0,
  checked_at INTEGER NOT NULL DEFAULT 0,
  lease_owner TEXT,
  lease_until INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS shop_calendar_due ON shop_calendar_sync(next_attempt,checked_at);
CREATE TABLE IF NOT EXISTS shop_calendar_health (
  id TEXT PRIMARY KEY, status TEXT NOT NULL CHECK(status IN ('connected','error')),
  checked_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS shop_admin_drafts (
  id TEXT PRIMARY KEY,
  request_key TEXT NOT NULL,
  request_fingerprint TEXT NOT NULL,
  kind TEXT NOT NULL CHECK(kind IN ('purchase','rental')),
  state TEXT NOT NULL CHECK(state IN ('draft','reviewed','voided')),
  private_cipher TEXT NOT NULL,
  lines_json TEXT NOT NULL,
  subtotal INTEGER CHECK(subtotal IS NULL OR subtotal > 0),
  shipping INTEGER NOT NULL CHECK(shipping >= 0),
  total INTEGER CHECK(total IS NULL OR (total > 0 AND total <= 100000000)),
  created_by TEXT NOT NULL,
  updated_by TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  reviewed_at INTEGER,
  version INTEGER NOT NULL DEFAULT 0 CHECK(version >= 0),
  CHECK((subtotal IS NULL AND total IS NULL) OR (subtotal IS NOT NULL AND total IS NOT NULL AND total = subtotal + shipping)),
  UNIQUE(created_by,request_key)
);
CREATE INDEX IF NOT EXISTS shop_admin_drafts_updated ON shop_admin_drafts(updated_at DESC,id DESC);
CREATE INDEX IF NOT EXISTS shop_admin_drafts_state ON shop_admin_drafts(state,updated_at DESC);
CREATE TABLE IF NOT EXISTS shop_admin_draft_events (
  id TEXT PRIMARY KEY,
  draft_id TEXT NOT NULL REFERENCES shop_admin_drafts(id),
  actor TEXT NOT NULL,
  action TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  version INTEGER NOT NULL,
  UNIQUE(draft_id,version)
);

CREATE TABLE IF NOT EXISTS shop_shipping_sync (
  order_id TEXT PRIMARY KEY REFERENCES shop_orders(id),
  next_attempt INTEGER
);
CREATE INDEX IF NOT EXISTS shop_shipping_due ON shop_shipping_sync(next_attempt);

CREATE TABLE IF NOT EXISTS shop_members (
 id TEXT PRIMARY KEY, email_hash TEXT NOT NULL UNIQUE, owner_hash TEXT NOT NULL UNIQUE,
 profile_cipher TEXT NOT NULL, password_hash TEXT NOT NULL, recovery_hash TEXT NOT NULL,
 terms_version TEXT NOT NULL, consented_at INTEGER NOT NULL, created_at INTEGER NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('active','closed')), closed_at INTEGER
);
CREATE TABLE IF NOT EXISTS shop_member_sessions (
 token_hash TEXT PRIMARY KEY, member_id TEXT NOT NULL REFERENCES shop_members(id),
 expires_at INTEGER NOT NULL, created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS shop_member_sessions_expiry ON shop_member_sessions(expires_at);
CREATE TABLE IF NOT EXISTS shop_points (
 id TEXT PRIMARY KEY, member_id TEXT NOT NULL REFERENCES shop_members(id), amount INTEGER NOT NULL CHECK(amount<>0),
 reason TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('adjustment','purchase','reversal')),
 request_key TEXT NOT NULL UNIQUE, fingerprint TEXT NOT NULL, actor TEXT NOT NULL,
 source_order TEXT REFERENCES shop_orders(id), created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS shop_points_member ON shop_points(member_id,created_at DESC);

CREATE TABLE IF NOT EXISTS shop_social_identities (
 provider TEXT NOT NULL CHECK(provider IN ('kakao','google','naver')),
 subject_hash TEXT NOT NULL, member_id TEXT NOT NULL REFERENCES shop_members(id), created_at INTEGER NOT NULL,
 PRIMARY KEY(provider,subject_hash), UNIQUE(member_id,provider)
);
CREATE TABLE IF NOT EXISTS shop_oauth_attempts (
 state_hash TEXT PRIMARY KEY, provider TEXT NOT NULL, binding_hash TEXT NOT NULL,
 private_cipher TEXT NOT NULL, expires_at INTEGER NOT NULL, created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS shop_oauth_expiry ON shop_oauth_attempts(expires_at);
CREATE TABLE IF NOT EXISTS shop_social_enrollments (
 ticket_hash TEXT PRIMARY KEY, private_cipher TEXT NOT NULL,
 expires_at INTEGER NOT NULL, created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS shop_social_enrollment_expiry ON shop_social_enrollments(expires_at);
