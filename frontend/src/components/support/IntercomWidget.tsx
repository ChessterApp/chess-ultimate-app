'use client';

import { useEffect } from 'react';
import { buildBootSettings, type IntercomContext } from '@/lib/intercom';

declare global {
  interface Window {
    Intercom?: (...args: unknown[]) => void;
    intercomSettings?: Record<string, unknown>;
    attachEvent?: (event: string, listener: () => void) => void;
  }
}

interface Props extends IntercomContext {
  appId?: string;
}

/**
 * Mount the Intercom widget for paying tiers (PRD §11.3 #5).
 *
 * The widget is gated by `buildBootSettings()` — non-paying tiers, missing
 * app id, or missing context all short-circuit to a no-op render. We never
 * inject the snippet for free tiers, so Starter customers don't see the
 * launcher at all.
 */
export function IntercomWidget(props: Props) {
  const appId = props.appId || process.env.NEXT_PUBLIC_INTERCOM_APP_ID;

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const settings = buildBootSettings({ ...props, appId });
    if (!settings) return;

    // Standard Intercom loader (minified). Inlined so we don't depend on a
    // separate package — Intercom's snippet is stable + their CSP-clean
    // loader pattern.
    const w = window;
    const ic = w.Intercom;
    w.intercomSettings = settings as unknown as Record<string, unknown>;
    if (typeof ic === 'function') {
      ic('reattach_activator');
      ic('update', settings);
    } else {
      const d = document;
      const i: ((...args: unknown[]) => void) & { q?: unknown[]; c?: (a: unknown) => void } =
        function (...args: unknown[]) {
          i.c?.(args);
        };
      i.q = [];
      i.c = function (a: unknown) {
        i.q!.push(a);
      };
      w.Intercom = i;
      const l = () => {
        const s = d.createElement('script');
        s.type = 'text/javascript';
        s.async = true;
        s.src = `https://widget.intercom.io/widget/${settings.app_id}`;
        const x = d.getElementsByTagName('script')[0];
        x.parentNode?.insertBefore(s, x);
      };
      if (document.readyState === 'complete') {
        l();
      } else {
        w.addEventListener('load', l, false);
      }
    }
    return () => {
      // Best-effort shutdown on unmount (e.g. when org switches)
      if (typeof w.Intercom === 'function') {
        try {
          w.Intercom('shutdown');
        } catch {
          // ignore
        }
      }
    };
  }, [appId, props.tier, props.orgId, props.userId, props]);

  return null;
}
