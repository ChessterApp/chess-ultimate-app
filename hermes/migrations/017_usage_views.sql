-- Migration 017: aggregated usage views for the cost dashboard
-- token_usage is written per call (coach turns, voice turns, lesson tutor,
-- memory writer, playbook, vision). The dashboard needs it by day / user /
-- surface / model without scanning the raw table in Python (analytics_db.py
-- stops at 100k rows). Views only — no data change; idempotent.

CREATE OR REPLACE VIEW token_usage_daily AS
SELECT
    (created_at AT TIME ZONE 'UTC')::date          AS day,
    surface,
    model,
    COUNT(*)                                       AS calls,
    COUNT(DISTINCT user_id)                        AS users,
    SUM(prompt_tokens)                             AS prompt_tokens,
    SUM(COALESCE(cached_tokens, 0))                AS cached_tokens,
    SUM(completion_tokens)                         AS completion_tokens,
    SUM(estimated_cost_usd)                        AS cost_usd
FROM token_usage
GROUP BY 1, 2, 3;

CREATE OR REPLACE VIEW token_usage_daily_by_user AS
SELECT
    (created_at AT TIME ZONE 'UTC')::date          AS day,
    user_id,
    surface,
    COUNT(*)                                       AS calls,
    SUM(prompt_tokens)                             AS prompt_tokens,
    SUM(COALESCE(cached_tokens, 0))                AS cached_tokens,
    SUM(completion_tokens)                         AS completion_tokens,
    SUM(estimated_cost_usd)                        AS cost_usd
FROM token_usage
GROUP BY 1, 2, 3;

-- Month-to-date spend per user: the number a per-user budget or a tariff
-- ledger will compare against.
CREATE OR REPLACE VIEW token_usage_month_by_user AS
SELECT
    date_trunc('month', created_at AT TIME ZONE 'UTC')::date AS month,
    user_id,
    COUNT(*)                                       AS calls,
    SUM(total_tokens)                              AS total_tokens,
    SUM(estimated_cost_usd)                        AS cost_usd,
    SUM(CASE WHEN surface = 'voice' THEN COALESCE(duration_ms, 0) ELSE 0 END) / 60000.0
                                                   AS voice_minutes
FROM token_usage
GROUP BY 1, 2;

-- Prompt-cache effectiveness per model per day (cached share of prompt tokens).
CREATE OR REPLACE VIEW token_usage_cache_rate AS
SELECT
    (created_at AT TIME ZONE 'UTC')::date          AS day,
    model,
    SUM(prompt_tokens)                             AS prompt_tokens,
    SUM(COALESCE(cached_tokens, 0))                AS cached_tokens,
    CASE WHEN SUM(prompt_tokens) > 0
         THEN ROUND(100.0 * SUM(COALESCE(cached_tokens, 0)) / SUM(prompt_tokens), 1)
         ELSE 0 END                                AS cached_pct
FROM token_usage
GROUP BY 1, 2;
