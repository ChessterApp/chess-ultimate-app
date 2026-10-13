/**
 * Parsed `?step=` value for the onboarding wizard.
 *  - a positive integer → that step (still clamped by the caller)
 *  - `complete`         → legacy Whop return URL; send to /upgrade/success
 *  - missing            → fresh start (step 1)
 *  - anything else      → `resume`: never reset to step 1, resume at the
 *                         earliest step the saved answers justify
 */
export type StepParam = number | 'complete' | 'resume';

export function parseStepParam(raw: string | null): StepParam {
  if (raw === null || raw === '') return 1;
  if (raw === 'complete') return 'complete';
  if (!/^\d+$/.test(raw)) return 'resume';
  const n = parseInt(raw, 10);
  return n >= 1 ? n : 'resume';
}
