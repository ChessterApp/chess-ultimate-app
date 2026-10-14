/** Shared look of the rich cards under an assistant answer (coach theme tokens only). */

export const cardShell =
  'animate-fade-in rounded-xl border border-(--coach-border) bg-(--coach-surface-2) p-3 text-(--coach-text)';

/** The card's one action: a 44px pill in the accent's outline. */
export const cardAction =
  'inline-flex min-h-11 items-center gap-1.5 rounded-full border border-(--coach-accent)/60 px-4 text-[13.5px] font-medium text-(--coach-accent-text) transition-colors hover:bg-(--coach-accent-soft) active:bg-(--coach-accent)/30 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-(--coach-accent) disabled:opacity-40 disabled:hover:bg-transparent';

export const cardTitle = 'text-[11px] font-semibold uppercase tracking-wide text-(--coach-muted)';
