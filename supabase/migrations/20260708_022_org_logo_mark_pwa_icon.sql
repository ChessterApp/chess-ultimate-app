-- Migration: Two-tier org branding — small-icon "logo mark" + PWA icon.
-- Source: .ralphy/logo-mark-brief.md
--
-- A single `logo_url` currently feeds ~10 render sites from 24px (mobile
-- navbar) up to 1200px (OG image). Detailed circular badges turn to mush at
-- small sizes and JPEG logos break in dark mode. These columns let an org
-- supply a simplified square mark for small render sites and a dedicated
-- maskable PWA icon, both falling back to `logo_url` when null.
--
-- Adds (both nullable, orgs without them fall back to logo_url):
--   * organizations.logo_mark_url TEXT — simplified square mark for ≤48px sites
--   * organizations.pwa_icon_url  TEXT — maskable 512 PWA/manifest icon
--
-- Also seeds Chess Empire (52b5682c-8c60-4b66-bd19-6ff2d17214eb) with the
-- pre-uploaded assets in the `org-branding` public bucket.
--
-- Idempotent.

ALTER TABLE organizations
  ADD COLUMN IF NOT EXISTS logo_mark_url TEXT,
  ADD COLUMN IF NOT EXISTS pwa_icon_url TEXT;

UPDATE organizations
SET
  logo_mark_url = 'https://qtzujwiqzbgyhdgulvcd.supabase.co/storage/v1/object/public/org-branding/52b5682c-8c60-4b66-bd19-6ff2d17214eb/logo-mark.png',
  pwa_icon_url = 'https://qtzujwiqzbgyhdgulvcd.supabase.co/storage/v1/object/public/org-branding/52b5682c-8c60-4b66-bd19-6ff2d17214eb/icon-maskable-512.png'
WHERE id = '52b5682c-8c60-4b66-bd19-6ff2d17214eb';

-- ROLLBACK:
-- ALTER TABLE organizations
--   DROP COLUMN IF EXISTS pwa_icon_url,
--   DROP COLUMN IF EXISTS logo_mark_url;
