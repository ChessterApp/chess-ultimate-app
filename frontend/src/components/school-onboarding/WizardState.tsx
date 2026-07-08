'use client';

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react';

// PRD §6.2 — pre-payment wizard state.
// Single client-side reducer with localStorage caching + server-side
// autosave via /api/onboarding/save. Resume happens by reading from
// /api/onboarding/resume on shell mount; localStorage is a backup for
// users who close the tab before the server save lands.

export type WizardStep =
  | 'account'
  | 'school'
  | 'plan'
  | 'payment'
  | 'brand'
  | 'invite'
  | 'done';

export const WIZARD_STEPS: WizardStep[] = [
  'account',
  'school',
  'plan',
  'payment',
  'brand',
  'invite',
  'done',
];

export interface WizardPayload {
  // step 1
  full_name?: string;
  phone?: string;
  email?: string;
  // step 2
  school_name?: string;
  slug?: string;
  logo_url?: string;
  logo_mark_url?: string;
  school_kind?: 'offline' | 'online' | 'solo' | 'tournament';
  // step 3
  tier?: 'starter' | 'growth' | 'pro' | 'enterprise';
  billing_cycle?: 'monthly' | 'annual';
  student_count_estimate?: number;
  // step 3 — enterprise self-serve (PRD §11.3 #1)
  sso_enabled?: boolean;
  // step 4
  payment_status?: 'pending' | 'paid';
  organization_id?: string;
  // step 5
  primary_color?: string;
  secondary_color?: string;
  accent_color?: string;
  favicon_url?: string;
  hero_headline?: string;
  custom_css?: string;
  custom_domain?: string;
  // step 6
  invites?: Array<{ email: string; first_name?: string; last_name?: string; role: string }>;
}

interface WizardContextValue {
  step: WizardStep;
  payload: WizardPayload;
  loaded: boolean;
  setStep: (s: WizardStep) => void;
  update: (patch: Partial<WizardPayload>) => void;
  save: () => Promise<void>;
}

const WizardContext = createContext<WizardContextValue | null>(null);

const LS_KEY = 'chesster.school-onboarding.v1';

interface PersistedShape {
  step: WizardStep;
  payload: WizardPayload;
}

function loadLocal(): PersistedShape | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(LS_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as PersistedShape;
  } catch {
    return null;
  }
}

function saveLocal(p: PersistedShape) {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(LS_KEY, JSON.stringify(p));
  } catch {
    // quota / private-mode — swallow
  }
}

export function WizardProvider({ children }: { children: ReactNode }) {
  const [step, setStepInternal] = useState<WizardStep>('account');
  const [payload, setPayload] = useState<WizardPayload>({});
  const [loaded, setLoaded] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const save = useCallback(async () => {
    try {
      await fetch('/api/onboarding/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ step, payload, email: payload.email }),
      });
    } catch {
      // network/auth — localStorage backup remains
    }
  }, [step, payload]);

  // Hydrate on mount: server first (authoritative), then localStorage
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const local = loadLocal();
      if (local) {
        setStepInternal(local.step);
        setPayload(local.payload);
      }
      try {
        const res = await fetch('/api/onboarding/resume');
        if (res.ok && !cancelled) {
          const body = await res.json();
          if (body.pending) {
            setStepInternal(body.pending.step as WizardStep);
            setPayload((body.pending.payload as WizardPayload) || {});
          }
        }
      } catch {
        // ignore — keep localStorage state
      }
      if (!cancelled) setLoaded(true);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // Persist + debounced server save on every change
  useEffect(() => {
    if (!loaded) return;
    saveLocal({ step, payload });
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      void save();
    }, 600);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [step, payload, loaded, save]);

  const setStep = useCallback((s: WizardStep) => setStepInternal(s), []);
  const update = useCallback(
    (patch: Partial<WizardPayload>) => setPayload(p => ({ ...p, ...patch })),
    [],
  );

  return (
    <WizardContext.Provider value={{ step, payload, loaded, setStep, update, save }}>
      {children}
    </WizardContext.Provider>
  );
}

export function useWizard(): WizardContextValue {
  const ctx = useContext(WizardContext);
  if (!ctx) throw new Error('useWizard must be used inside WizardProvider');
  return ctx;
}

export function slugify(input: string): string {
  return input
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9-]+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 30);
}
