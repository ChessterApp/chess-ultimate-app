'use client';

import React, { useState } from 'react';
import { Dialog } from '@mui/material';
import { useTranslations } from 'next-intl';

interface CoachDialogProps {
  open: boolean;
  title: string;
  message?: string;
  confirmLabel: string;
  /** Red confirm button for irreversible actions (delete, resign). */
  danger?: boolean;
  /** Prompt mode: show a text field seeded with this value; onConfirm receives it. */
  initialValue?: string;
  inputLabel?: string;
  onConfirm: (value: string) => void;
  onCancel: () => void;
}

/**
 * The coach's confirm / prompt dialog, in place of window.confirm/prompt.
 * MUI's Dialog supplies the focus trap, Esc-to-cancel and the portal; a form
 * makes Enter confirm. Focus starts on the field (prompt) or the confirm button.
 */
export default function CoachDialog(props: CoachDialogProps) {
  return (
    <Dialog
      open={props.open}
      onClose={props.onCancel}
      maxWidth="xs"
      fullWidth
      aria-labelledby="coach-dialog-title"
      PaperProps={{ sx: { backgroundColor: 'transparent', backgroundImage: 'none', boxShadow: 'none' } }}
      slotProps={{ backdrop: { sx: { backgroundColor: 'rgba(0, 0, 0, 0.6)' } } }}
    >
      {/* The Dialog unmounts its content when closed, so each open starts from initialValue. */}
      <DialogForm {...props} />
    </Dialog>
  );
}

function DialogForm({
  title,
  message,
  confirmLabel,
  danger = false,
  initialValue,
  inputLabel,
  onConfirm,
  onCancel,
}: CoachDialogProps) {
  const t = useTranslations('coach');
  const isPrompt = initialValue !== undefined;
  const [value, setValue] = useState(initialValue ?? '');

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onConfirm(value);
      }}
      className="rounded-xl border border-white/10 bg-[#1b1b1f] p-5 shadow-xl"
    >
      <h2 id="coach-dialog-title" className="text-base font-semibold text-white">
        {title}
      </h2>
      {message && <p className="mt-1.5 text-sm text-gray-400">{message}</p>}
      {isPrompt && (
        <input
          autoFocus
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onFocus={(e) => e.currentTarget.select()}
          aria-label={inputLabel ?? title}
          // 16px on phones: iOS Safari zooms into smaller fields.
          className="mt-3 w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-base sm:text-sm text-gray-100 focus:outline-none focus:border-blue-500/50"
        />
      )}
      <div className="mt-5 flex justify-end gap-2">
        <button
          type="button"
          onClick={onCancel}
          className="min-h-11 rounded-lg px-4 text-sm text-gray-300 bg-white/5 hover:bg-white/10 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-400"
        >
          {t('cancel')}
        </button>
        <button
          type="submit"
          autoFocus={!isPrompt}
          className={`min-h-11 rounded-lg px-4 text-sm font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-400 ${
            danger
              ? 'bg-red-500/20 text-red-300 hover:bg-red-500/30'
              : 'bg-blue-600/40 text-white hover:bg-blue-600/60'
          }`}
        >
          {confirmLabel}
        </button>
      </div>
    </form>
  );
}
