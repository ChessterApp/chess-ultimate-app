/**
 * AddGameModal — Modal with 2 input methods for adding games:
 * 1. Upload Scoresheet — reuse ScoresheetScanner for OCR
 * 2. Import PGN — paste PGN text
 *
 * When boardHasMoves is true, the modal shows a preview of moves from the main board
 * and uses those as the PGN source by default.
 */

'use client';

import React, { useState, useCallback, useEffect } from 'react';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  Box,
  Typography,
  TextField,
  Button,
  Chip,
  IconButton,
  Alert,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  CircularProgress,
} from '@mui/material';
import { Close, CameraAlt, Description } from '@mui/icons-material';
import { useTranslations } from 'next-intl';
import { Chess } from 'chess.js';

type InputMethod = 'scoresheet' | 'pgn';

interface GameFormData {
  title: string;
  white: string;
  black: string;
  whiteElo: string;
  blackElo: string;
  result: string;
  date: string;
  event: string;
  notes: string;
}

interface AddGameModalProps {
  open: boolean;
  onClose: () => void;
  onSave: (pgn: string, metadata?: Partial<{
    title: string;
    white: string;
    black: string;
    white_elo: number;
    black_elo: number;
    result: string;
    date: string;
    event: string;
    notes: string;
    source: string;
  }>) => Promise<boolean>;
  boardPgn?: string;
  boardHasMoves?: boolean;
  onBoardReset?: () => void;
}

const INITIAL_FORM: GameFormData = {
  title: '',
  white: '',
  black: '',
  whiteElo: '',
  blackElo: '',
  result: '*',
  date: '',
  event: '',
  notes: '',
};

export default function AddGameModal({ open, onClose, onSave, boardPgn, boardHasMoves, onBoardReset }: AddGameModalProps) {
  const t = useTranslations('debut');
  const [method, setMethod] = useState<InputMethod>('pgn');
  const [form, setForm] = useState<GameFormData>(INITIAL_FORM);
  const [pgn, setPgn] = useState('');
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  // Track whether user explicitly overrode board moves with a method input
  const [boardOverridden, setBoardOverridden] = useState(false);
  // Show replace warning dialog
  const [showReplaceWarning, setShowReplaceWarning] = useState(false);
  const [pendingMethod, setPendingMethod] = useState<InputMethod | null>(null);

  // Scoresheet state
  const [scoresheetPgn, setScoresheetPgn] = useState('');

  const useBoardPgn = boardHasMoves && !boardOverridden;

  const resetState = useCallback(() => {
    setMethod('pgn');
    setForm(INITIAL_FORM);
    setPgn('');
    setError('');
    setSaving(false);
    setScoresheetPgn('');
    setBoardOverridden(false);
    setShowReplaceWarning(false);
    setPendingMethod(null);
  }, []);

  const handleClose = useCallback(() => {
    resetState();
    onClose();
  }, [resetState, onClose]);

  // Populate form from PGN headers
  const populateFormFromPgn = useCallback((pgnText: string) => {
    const headers: Record<string, string> = {};
    const lines = pgnText.split('\n');
    for (const line of lines) {
      const match = line.match(/\[(\w+)\s+"(.*)"\]/);
      if (match) headers[match[1]] = match[2];
    }
    const placeholders = new Set(['?', '??', '???', '????.??.??', 'Casual Game']);
    const clean = (val: string | undefined) => val && !placeholders.has(val) ? val : '';
    setForm(prev => ({
      ...prev,
      white: clean(headers.White) || prev.white,
      black: clean(headers.Black) || prev.black,
      whiteElo: clean(headers.WhiteElo) || prev.whiteElo,
      blackElo: clean(headers.BlackElo) || prev.blackElo,
      result: clean(headers.Result) || prev.result,
      date: clean(headers.Date) || prev.date,
      event: clean(headers.Event) || prev.event,
    }));
  }, []);

  // Handle method switching — warn if board has moves
  const handleMethodSwitch = useCallback((newMethod: InputMethod) => {
    if (boardHasMoves && !boardOverridden) {
      setPendingMethod(newMethod);
      setShowReplaceWarning(true);
    } else {
      setMethod(newMethod);
    }
  }, [boardHasMoves, boardOverridden]);

  const handleReplaceConfirm = useCallback(() => {
    setBoardOverridden(true);
    if (pendingMethod) setMethod(pendingMethod);
    setShowReplaceWarning(false);
    setPendingMethod(null);
  }, [pendingMethod]);

  const handleReplaceCancel = useCallback(() => {
    setShowReplaceWarning(false);
    setPendingMethod(null);
  }, []);

  // ── Scoresheet Callback ──

  const handleScoresheetResult = useCallback((resultPgn: string) => {
    setScoresheetPgn(resultPgn);
    populateFormFromPgn(resultPgn);
  }, [populateFormFromPgn]);

  // ── Save Handler ──

  const handleSave = useCallback(async () => {
    setError('');

    let finalPgn = '';
    let source = 'manual';

    if (useBoardPgn) {
      // Use PGN from main board
      if (!boardPgn) {
        setError(t('myGames.addModal.noMoves'));
        return;
      }
      finalPgn = boardPgn;
      source = 'board_entry';
    } else if (method === 'pgn') {
      if (!pgn.trim()) {
        setError(t('myGames.addModal.pgnRequired'));
        return;
      }
      try {
        const chess = new Chess();
        chess.loadPgn(pgn.trim());
      } catch {
        setError(t('myGames.addModal.invalidPgn'));
        return;
      }
      finalPgn = pgn.trim();
      source = 'pgn_import';
    } else if (method === 'scoresheet') {
      if (!scoresheetPgn) {
        setError(t('myGames.addModal.noScoresheet'));
        return;
      }
      finalPgn = scoresheetPgn;
      source = 'scoresheet';
    }

    setSaving(true);
    try {
      const metadata: Record<string, unknown> = { source };
      if (form.title) metadata.title = form.title;
      if (form.white) metadata.white = form.white;
      if (form.black) metadata.black = form.black;
      if (form.whiteElo) metadata.white_elo = parseInt(form.whiteElo, 10);
      if (form.blackElo) metadata.black_elo = parseInt(form.blackElo, 10);
      if (form.result && form.result !== '*') metadata.result = form.result;
      if (form.date) metadata.date = form.date;
      if (form.event) metadata.event = form.event;
      if (form.notes) metadata.notes = form.notes;

      const success = await onSave(finalPgn, metadata as Parameters<typeof onSave>[1]);
      if (success) {
        // Clear the main board after successful save if we used board PGN
        if (useBoardPgn) {
          onBoardReset?.();
        }
        handleClose();
      }
    } catch {
      setError(t('myGames.addModal.saveFailed'));
    } finally {
      setSaving(false);
    }
  }, [useBoardPgn, boardPgn, method, pgn, scoresheetPgn, form, onSave, onBoardReset, handleClose, t]);

  const methods: { key: InputMethod; label: string; icon: React.ReactNode }[] = [
    { key: 'scoresheet', label: t('myGames.addModal.uploadScoresheet'), icon: <CameraAlt sx={{ fontSize: 16 }} /> },
    { key: 'pgn', label: t('myGames.addModal.importPgn'), icon: <Description sx={{ fontSize: 16 }} /> },
  ];

  return (
    <Dialog
      open={open}
      onClose={handleClose}
      maxWidth="sm"
      fullWidth
      PaperProps={{
        sx: {
          bgcolor: 'background.paper',
          border: '1px solid',
          borderColor: 'divider',
          borderRadius: 2,
          maxHeight: '90vh',
        },
      }}
      slotProps={{
        backdrop: {
          sx: {
            backgroundColor: 'rgba(0, 0, 0, 0.5)',
            backdropFilter: 'blur(4px)',
          },
        },
      }}
    >
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', pb: 1 }}>
        <Typography sx={{ fontSize: 16, fontWeight: 600, color: 'text.primary' }}>
          {t('myGames.addGame')}
        </Typography>
        <IconButton onClick={handleClose} size="small" sx={{ color: 'text.secondary' }}>
          <Close fontSize="small" />
        </IconButton>
      </DialogTitle>

      <DialogContent sx={{ px: 3, pb: 3 }}>
        {/* Board moves preview — show when board has moves and not overridden */}
        {boardHasMoves && !boardOverridden && boardPgn && (
          <Box sx={{
            mb: 2,
            p: 1.5,
            bgcolor: 'rgba(255,255,255,0.03)',
            borderRadius: 1,
            border: '1px solid rgba(255,255,255,0.08)',
          }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
              <Chip
                label={t('myGames.movesFromBoard')}
                size="small"
                color="success"
                sx={{ height: 20, fontSize: 10 }}
              />
            </Box>
            <Typography sx={{
              fontSize: 11,
              fontFamily: 'monospace',
              color: 'text.secondary',
              maxHeight: 60,
              overflow: 'auto',
              lineHeight: 1.6,
            }}>
              {boardPgn}
            </Typography>
          </Box>
        )}

        {/* Replace warning */}
        {showReplaceWarning && (
          <Alert
            severity="warning"
            sx={{ mb: 2, fontSize: 12 }}
            action={
              <Box sx={{ display: 'flex', gap: 0.5 }}>
                <Button size="small" onClick={handleReplaceCancel} sx={{ fontSize: 11, textTransform: 'none' }}>
                  {t('myGames.cancelBtn')}
                </Button>
                <Button size="small" onClick={handleReplaceConfirm} sx={{ fontSize: 11, textTransform: 'none', fontWeight: 600 }}>
                  {t('myGames.continueBtn')}
                </Button>
              </Box>
            }
          >
            {t('myGames.replaceWarning')}
          </Alert>
        )}

        {/* Method selector chips — show when no board moves or when overridden */}
        {(!boardHasMoves || boardOverridden) && (
          <Box sx={{ display: 'flex', gap: 0.75, mb: 2.5 }}>
            {methods.map((m) => (
              <Chip
                key={m.key}
                icon={m.icon as React.ReactElement}
                label={m.label}
                size="small"
                onClick={() => handleMethodSwitch(m.key)}
                sx={{
                  height: 28,
                  fontSize: 11,
                  fontWeight: method === m.key ? 700 : 400,
                  bgcolor: method === m.key ? 'primary.main' : 'action.hover',
                  color: method === m.key ? '#fff' : 'text.secondary',
                  '& .MuiChip-icon': {
                    color: method === m.key ? '#fff' : 'text.secondary',
                  },
                  '&:hover': {
                    bgcolor: method === m.key ? 'primary.dark' : 'action.selected',
                  },
                }}
              />
            ))}
          </Box>
        )}

        {/* Method chips shown even when board has moves — for switching */}
        {boardHasMoves && !boardOverridden && (
          <Box sx={{ display: 'flex', gap: 0.75, mb: 2.5 }}>
            {methods.map((m) => (
              <Chip
                key={m.key}
                icon={m.icon as React.ReactElement}
                label={m.label}
                size="small"
                onClick={() => handleMethodSwitch(m.key)}
                sx={{
                  height: 28,
                  fontSize: 11,
                  fontWeight: 400,
                  bgcolor: 'action.hover',
                  color: 'text.secondary',
                  '& .MuiChip-icon': { color: 'text.secondary' },
                  '&:hover': { bgcolor: 'action.selected' },
                }}
              />
            ))}
          </Box>
        )}

        {/* Input area based on method — only show when not using board PGN */}
        {!useBoardPgn && (
          <Box sx={{ mb: 2.5 }}>
            {method === 'pgn' && (
              <PgnImportTab
                pgn={pgn}
                onPgnChange={(val) => {
                  setPgn(val);
                  if (val.trim()) populateFormFromPgn(val);
                }}
                t={t}
              />
            )}
            {method === 'scoresheet' && (
              <ScoresheetTab
                scoresheetPgn={scoresheetPgn}
                onResult={handleScoresheetResult}
                t={t}
              />
            )}
          </Box>
        )}

        {/* Game details form */}
        <GameDetailsForm form={form} setForm={setForm} t={t} />

        {/* Error */}
        {error && (
          <Alert severity="error" sx={{ mt: 2, fontSize: 12 }} onClose={() => setError('')}>
            {error}
          </Alert>
        )}

        {/* Actions */}
        <Box sx={{ display: 'flex', justifyContent: 'flex-end', gap: 1.5, mt: 2.5 }}>
          <Button
            onClick={handleClose}
            size="small"
            sx={{
              color: 'text.secondary',
              fontSize: 12,
              textTransform: 'none',
              '&:hover': { bgcolor: 'action.hover' },
            }}
          >
            {t('myGames.cancel')}
          </Button>
          <Button
            variant="contained"
            size="small"
            onClick={handleSave}
            disabled={saving}
            sx={{
              fontSize: 12,
              textTransform: 'none',
              px: 3,
              background: 'linear-gradient(135deg, #7c3aed, #6366f1)',
              '&:hover': { background: 'linear-gradient(135deg, #6d28d9, #4f46e5)' },
            }}
          >
            {saving ? <CircularProgress size={16} sx={{ color: '#fff' }} /> : t('myGames.save')}
          </Button>
        </Box>
      </DialogContent>
    </Dialog>
  );
}

// ─── PGN Import Tab ─────────────────────

interface PgnImportTabProps {
  pgn: string;
  onPgnChange: (val: string) => void;
  t: ReturnType<typeof useTranslations>;
}

function PgnImportTab({ pgn, onPgnChange, t }: PgnImportTabProps) {
  const [preview, setPreview] = useState<{ moves: number; valid: boolean } | null>(null);

  useEffect(() => {
    if (!pgn.trim()) {
      setPreview(null);
      return;
    }
    try {
      const chess = new Chess();
      chess.loadPgn(pgn.trim());
      setPreview({ moves: chess.history().length, valid: true });
    } catch {
      setPreview({ moves: 0, valid: false });
    }
  }, [pgn]);

  return (
    <Box>
      <TextField
        multiline
        rows={6}
        fullWidth
        placeholder={t('myGames.addModal.pgnPlaceholder')}
        value={pgn}
        onChange={(e) => onPgnChange(e.target.value)}
        sx={{
          '& .MuiOutlinedInput-root': {
            fontSize: 12,
            fontFamily: 'monospace',
            bgcolor: 'action.hover',
          },
        }}
      />
      {preview && (
        <Box sx={{ mt: 1, display: 'flex', gap: 0.5 }}>
          <Chip
            label={preview.valid ? t('myGames.addModal.validPgn') : t('myGames.addModal.invalidPgn')}
            size="small"
            color={preview.valid ? 'success' : 'error'}
            sx={{ height: 20, fontSize: 10 }}
          />
          {preview.valid && (
            <Chip
              label={`${Math.ceil(preview.moves / 2)} ${t('myGames.addModal.movesCount')}`}
              size="small"
              sx={{ height: 20, fontSize: 10, bgcolor: 'action.selected' }}
            />
          )}
        </Box>
      )}
    </Box>
  );
}

// ─── Scoresheet Tab ─────────────────────

interface ScoresheetTabProps {
  scoresheetPgn: string;
  onResult: (pgn: string) => void;
  t: ReturnType<typeof useTranslations>;
}

function ScoresheetTab({ scoresheetPgn, onResult, t }: ScoresheetTabProps) {
  const [images, setImages] = useState<string[]>([]);
  const [previews, setPreviews] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [scanError, setScanError] = useState('');

  const handleFileUpload = useCallback((event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files;
    if (!files) return;

    const fileArray = Array.from(files).slice(0, 2);
    const readers = fileArray.map((file) => {
      return new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => {
          const base64 = reader.result as string;
          resolve(base64.split(',')[1]);
        };
        reader.onerror = reject;
        reader.readAsDataURL(file);
      });
    });

    const previewUrls = fileArray.map((file) => URL.createObjectURL(file));
    setPreviews(previewUrls);

    Promise.all(readers)
      .then((base64Images) => {
        setImages(base64Images);
        setScanError('');
      })
      .catch(() => {
        setScanError('Failed to read images');
      });
  }, []);

  const handleScan = useCallback(async () => {
    if (images.length === 0) return;
    setLoading(true);
    setScanError('');

    try {
      const { apiFetch } = await import('@/lib/api');
      const data = await apiFetch<{ pgn: string; confidence: number; moves_total: number }>('/api/convert-scoresheet', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ images }),
      });

      if (data.pgn) {
        onResult(data.pgn);
      } else {
        setScanError(t('myGames.addModal.scanFailed'));
      }
    } catch {
      setScanError(t('myGames.addModal.scanFailed'));
    } finally {
      setLoading(false);
    }
  }, [images, onResult, t]);

  // Auto-scan when images are added
  useEffect(() => {
    if (images.length > 0 && !scoresheetPgn && !loading) {
      handleScan();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [images]);

  return (
    <Box>
      {!scoresheetPgn ? (
        <>
          {images.length === 0 ? (
            <Box
              component="label"
              sx={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                p: 4,
                border: '2px dashed',
                borderColor: 'divider',
                borderRadius: 2,
                cursor: 'pointer',
                transition: 'all 0.2s',
                '&:hover': {
                  borderColor: 'primary.main',
                  bgcolor: 'action.hover',
                },
              }}
            >
              <input type="file" accept="image/*" multiple hidden onChange={handleFileUpload} />
              <CameraAlt sx={{ fontSize: 36, color: 'text.secondary', mb: 1 }} />
              <Typography sx={{ fontSize: 13, color: 'text.secondary' }}>
                {t('myGames.addModal.uploadPrompt')}
              </Typography>
              <Typography sx={{ fontSize: 10, color: 'text.secondary', opacity: 0.6, mt: 0.5 }}>
                {t('myGames.addModal.uploadHint')}
              </Typography>
            </Box>
          ) : (
            <Box>
              <Box sx={{ display: 'flex', gap: 1, mb: 1.5 }}>
                {previews.map((url, i) => (
                  <Box key={i} sx={{ width: 80, height: 80, borderRadius: 1, overflow: 'hidden', border: '1px solid', borderColor: 'divider' }}>
                    <img src={url} alt={`Scoresheet ${i + 1}`} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                  </Box>
                ))}
              </Box>
              {loading && (
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <CircularProgress size={16} />
                  <Typography sx={{ fontSize: 12, color: 'text.secondary' }}>
                    {t('myGames.addModal.scanning')}
                  </Typography>
                </Box>
              )}
            </Box>
          )}
          {scanError && (
            <Alert severity="error" sx={{ mt: 1.5, fontSize: 11 }}>
              {scanError}
            </Alert>
          )}
        </>
      ) : (
        <Box sx={{ p: 1.5, bgcolor: 'action.hover', borderRadius: 1 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
            <Chip label={t('myGames.addModal.scoresheetReady')} size="small" color="success" sx={{ height: 20, fontSize: 10 }} />
          </Box>
          <Typography sx={{ fontSize: 11, fontFamily: 'monospace', color: 'text.secondary', maxHeight: 80, overflow: 'auto' }}>
            {scoresheetPgn}
          </Typography>
        </Box>
      )}
    </Box>
  );
}

// ─── Game Details Form ──────────────────

interface GameDetailsFormProps {
  form: GameFormData;
  setForm: React.Dispatch<React.SetStateAction<GameFormData>>;
  t: ReturnType<typeof useTranslations>;
}

function GameDetailsForm({ form, setForm, t }: GameDetailsFormProps) {
  const updateField = (field: keyof GameFormData, value: string) => {
    setForm(prev => ({ ...prev, [field]: value }));
  };

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
      <Typography sx={{ fontSize: 12, fontWeight: 600, color: 'text.secondary', textTransform: 'uppercase', letterSpacing: 0.5 }}>
        {t('myGames.addModal.gameDetails')}
      </Typography>

      <TextField
        size="small"
        label={t('myGames.addModal.titleLabel')}
        value={form.title}
        onChange={(e) => updateField('title', e.target.value)}
        sx={fieldSx}
      />

      <Box sx={{ display: 'flex', gap: 1 }}>
        <TextField
          size="small"
          label={t('myGames.addModal.whiteName')}
          value={form.white}
          onChange={(e) => updateField('white', e.target.value)}
          sx={{ ...fieldSx, flex: 1 }}
        />
        <TextField
          size="small"
          label={t('myGames.addModal.whiteElo')}
          value={form.whiteElo}
          onChange={(e) => updateField('whiteElo', e.target.value.replace(/\D/g, ''))}
          sx={{ ...fieldSx, width: 80 }}
        />
      </Box>

      <Box sx={{ display: 'flex', gap: 1 }}>
        <TextField
          size="small"
          label={t('myGames.addModal.blackName')}
          value={form.black}
          onChange={(e) => updateField('black', e.target.value)}
          sx={{ ...fieldSx, flex: 1 }}
        />
        <TextField
          size="small"
          label={t('myGames.addModal.blackElo')}
          value={form.blackElo}
          onChange={(e) => updateField('blackElo', e.target.value.replace(/\D/g, ''))}
          sx={{ ...fieldSx, width: 80 }}
        />
      </Box>

      <Box sx={{ display: 'flex', gap: 1 }}>
        <FormControl size="small" sx={{ flex: 1 }}>
          <InputLabel sx={{ fontSize: 12 }}>{t('myGames.addModal.resultLabel')}</InputLabel>
          <Select
            value={form.result}
            onChange={(e) => updateField('result', e.target.value)}
            label={t('myGames.addModal.resultLabel')}
            sx={{ fontSize: 12, bgcolor: 'action.hover' }}
          >
            <MenuItem value="*">*</MenuItem>
            <MenuItem value="1-0">1-0</MenuItem>
            <MenuItem value="0-1">0-1</MenuItem>
            <MenuItem value="1/2-1/2">1/2-1/2</MenuItem>
          </Select>
        </FormControl>
        <TextField
          size="small"
          label={t('myGames.addModal.dateLabel')}
          placeholder="YYYY.MM.DD"
          value={form.date}
          onChange={(e) => updateField('date', e.target.value)}
          sx={{ ...fieldSx, flex: 1 }}
        />
      </Box>

      <TextField
        size="small"
        label={t('myGames.addModal.eventLabel')}
        value={form.event}
        onChange={(e) => updateField('event', e.target.value)}
        sx={fieldSx}
      />

      <TextField
        size="small"
        label={t('myGames.addModal.notesLabel')}
        value={form.notes}
        onChange={(e) => updateField('notes', e.target.value)}
        multiline
        rows={2}
        sx={fieldSx}
      />
    </Box>
  );
}

const fieldSx = {
  '& .MuiOutlinedInput-root': {
    fontSize: 12,
    bgcolor: 'action.hover',
  },
  '& .MuiInputLabel-root': {
    fontSize: 12,
  },
};
