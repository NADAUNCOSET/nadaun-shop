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
CREATE TABLE IF NOT EXISTS shop_order_events (
  id TEXT PRIMARY KEY, order_id TEXT NOT NULL REFERENCES shop_orders(id),
  actor TEXT NOT NULL, action TEXT NOT NULL, created_at INTEGER NOT NULL, version INTEGER NOT NULL,
  UNIQUE(order_id,version)
);
CREATE TABLE IF NOT EXISTS shop_rate_limits (
  key TEXT PRIMARY KEY, attempts INTEGER NOT NULL, expires_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS shop_rate_limits_expiry ON shop_rate_limits(expires_at);
