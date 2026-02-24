CREATE TABLE IF NOT EXISTS subscriptions (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  clerk_user_id text NOT NULL,
  whop_user_id text,
  whop_membership_id text UNIQUE,
  plan_id text NOT NULL,
  plan_type text,
  status text NOT NULL DEFAULT 'inactive',
  trial_start timestamptz,
  trial_end timestamptz,
  current_period_start timestamptz,
  current_period_end timestamptz,
  canceled_at timestamptz,
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_subscriptions_clerk ON subscriptions(clerk_user_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_whop ON subscriptions(whop_membership_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_subscriptions_clerk_unique ON subscriptions(clerk_user_id);

CREATE TABLE IF NOT EXISTS subscription_events (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  subscription_id uuid REFERENCES subscriptions(id),
  event_type text NOT NULL,
  event_data jsonb,
  created_at timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_sub_events_sub ON subscription_events(subscription_id);
