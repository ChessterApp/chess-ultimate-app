'use client';

import React from 'react';
import { Dialog, DialogTitle, DialogContent, DialogActions, Button } from '@mui/material';
import { purpleTheme } from '@/theme/theme';

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  message: string;
  confirmText?: string;
  cancelText?: string;
  onConfirm: () => void;
  onCancel: () => void;
  variant?: 'danger' | 'warning' | 'info';
}

const ConfirmDialog: React.FC<ConfirmDialogProps> = ({
  open,
  title,
  message,
  confirmText = 'Confirm',
  cancelText = 'Cancel',
  onConfirm,
  onCancel,
  variant = 'danger',
}) => {
  const getVariantStyles = () => {
    switch (variant) {
      case 'danger':
        return {
          iconBg: 'bg-red-500/20',
          iconColor: 'text-red-400',
          confirmBg: 'from-red-600 to-red-800 hover:from-red-500 hover:to-red-700',
          confirmShadow: 'shadow-red-900/50 hover:shadow-red-600/50',
        };
      case 'warning':
        return {
          iconBg: 'bg-amber-500/20',
          iconColor: 'text-amber-400',
          confirmBg: 'from-amber-600 to-amber-800 hover:from-amber-500 hover:to-amber-700',
          confirmShadow: 'shadow-amber-900/50 hover:shadow-amber-600/50',
        };
      case 'info':
      default:
        return {
          iconBg: 'bg-purple-500/20',
          iconColor: 'text-purple-400',
          confirmBg: 'from-purple-600 to-purple-800 hover:from-purple-500 hover:to-purple-700',
          confirmShadow: 'shadow-purple-900/50 hover:shadow-purple-600/50',
        };
    }
  };

  const styles = getVariantStyles();

  const getIcon = () => {
    switch (variant) {
      case 'danger':
        return (
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
          </svg>
        );
      case 'warning':
        return (
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
        );
      case 'info':
      default:
        return (
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        );
    }
  };

  return (
    <Dialog
      open={open}
      onClose={onCancel}
      maxWidth="xs"
      fullWidth
      PaperProps={{
        sx: {
          backgroundColor: 'transparent',
          backgroundImage: 'none',
          boxShadow: 'none',
          overflow: 'visible',
        },
      }}
      slotProps={{
        backdrop: {
          sx: {
            backgroundColor: 'rgba(0, 0, 0, 0.7)',
            backdropFilter: 'blur(4px)',
          },
        },
      }}
    >
      <div className="bg-gradient-to-b from-purple-950/95 to-slate-900/95 backdrop-blur-xl border-2 border-purple-500/30 rounded-2xl shadow-2xl shadow-purple-900/50 overflow-hidden">
        {/* Header */}
        <div className="p-6 pb-4">
          <div className="flex items-start space-x-4">
            {/* Icon */}
            <div className={`flex-shrink-0 w-12 h-12 rounded-xl ${styles.iconBg} flex items-center justify-center`}>
              <span className={styles.iconColor}>{getIcon()}</span>
            </div>

            {/* Title and Message */}
            <div className="flex-1 min-w-0">
              <h3 className="text-lg font-semibold text-white mb-1">
                {title}
              </h3>
              <p className="text-sm text-slate-300 leading-relaxed">
                {message}
              </p>
            </div>
          </div>
        </div>

        {/* Actions */}
        <div className="px-6 pb-6 flex items-center justify-end space-x-3">
          <button
            onClick={onCancel}
            className="px-5 py-2.5 rounded-lg bg-slate-800/50 hover:bg-slate-700/60 text-slate-300 hover:text-white text-sm font-medium transition-all duration-200 border border-purple-500/20 hover:border-purple-500/40"
          >
            {cancelText}
          </button>
          <button
            onClick={onConfirm}
            className={`px-5 py-2.5 rounded-lg bg-gradient-to-r ${styles.confirmBg} text-white text-sm font-medium transition-all duration-200 shadow-lg ${styles.confirmShadow} hover:scale-[1.02]`}
          >
            {confirmText}
          </button>
        </div>
      </div>
    </Dialog>
  );
};

export default ConfirmDialog;
