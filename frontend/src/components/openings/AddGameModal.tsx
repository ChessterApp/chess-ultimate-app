/**
 * AddGameModal — Modal with 3 input methods for adding games:
 * 1. Enter on Board — play moves on a chessboard
 * 2. Upload Scoresheet — reuse ScoresheetScanner for OCR
 * 3. Import PGN — paste PGN text
 */

'use client';

import React, { useState, useCallback, useRef, useEffect } from 'react';
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
import { Close, GridOn, CameraAlt, Description } from '@mui/icons-material';
import { useTranslations } from 'next-intl';
import { Chess } from 'chess.js';

type InputMethod = 'board' | 'scoresheet' | 'pgn';

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

export default function AddGameModal({ open, onClose, onSave }: AddGameModalProps) {
  const t = useTranslations('debut');
  const [method, setMethod] = useState<InputMethod>('pgn');
  const [form, setForm] = useState<GameFormData>(INITIAL_FORM);
  const [pgn, setPgn] = useState('');
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  // Board entry state
  const [boardMoves, setBoardMoves] = useState<string[]>([]);
  const [boardFen, setBoardFen] = useState('rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1');
  const chessRef = useRef(new Chess());

  // Scoresheet state
  const [scoresheetPgn, setScoresheetPgn] = useState('');

  const resetState = useCallback(() => {
    setMethod('pgn');
    setForm(INITIAL_FORM);
    setPgn('');
    setError('');
    setSaving(false);
    setBoardMoves([]);
    setBoardFen('rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1');
    chessRef.current = new Chess();
    setScoresheetPgn('');
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
    setForm(prev => ({
      ...prev,
      white: headers.White || prev.white,
      black: headers.Black || prev.black,
      whiteElo: headers.WhiteElo || prev.whiteElo,
      blackElo: headers.BlackElo || prev.blackElo,
      result: headers.Result || prev.result,
      date: headers.Date || prev.date,
      event: headers.Event || prev.event,
    }));
  }, []);

  // ── Board Entry Methods ──

  const handleBoardMove = useCallback((from: string, to: string, promotion?: string) => {
    const chess = chessRef.current;
    try {
      const move = chess.move({ from, to, promotion: promotion || undefined });
      if (move) {
        setBoardMoves(prev => [...prev, move.san]);
        setBoardFen(chess.fen());
      }
    } catch {
      // Invalid move — ignore
    }
  }, []);

  const handleBoardUndo = useCallback(() => {
    const chess = chessRef.current;
    chess.undo();
    setBoardMoves(prev => prev.slice(0, -1));
    setBoardFen(chess.fen());
  }, []);

  const handleBoardReset = useCallback(() => {
    chessRef.current = new Chess();
    setBoardMoves([]);
    setBoardFen('rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1');
  }, []);

  // Build PGN from board moves
  const buildBoardPgn = useCallback(() => {
    return chessRef.current.pgn();
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

    if (method === 'pgn') {
      if (!pgn.trim()) {
        setError(t('myGames.addModal.pgnRequired'));
        return;
      }
      // Validate PGN
      try {
        const chess = new Chess();
        chess.loadPgn(pgn.trim());
      } catch {
        setError(t('myGames.addModal.invalidPgn'));
        return;
      }
      finalPgn = pgn.trim();
      source = 'pgn_import';
    } else if (method === 'board') {
      if (boardMoves.length === 0) {
        setError(t('myGames.addModal.noMoves'));
        return;
      }
      finalPgn = buildBoardPgn();
      source = 'board_entry';
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
        handleClose();
      }
    } catch {
      setError(t('myGames.addModal.saveFailed'));
    } finally {
      setSaving(false);
    }
  }, [method, pgn, boardMoves, scoresheetPgn, form, buildBoardPgn, onSave, handleClose, t]);

  const methods: { key: InputMethod; label: string; icon: React.ReactNode }[] = [
    { key: 'board', label: t('myGames.addModal.enterOnBoard'), icon: <GridOn sx={{ fontSize: 16 }} /> },
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
          bgcolor: '#0f0f1a',
          border: '1px solid rgba(139, 92, 246, 0.3)',
          borderRadius: 2,
          maxHeight: '90vh',
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
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', pb: 1 }}>
        <Typography sx={{ fontSize: 16, fontWeight: 600, color: '#fff' }}>
          {t('myGames.addGame')}
        </Typography>
        <IconButton onClick={handleClose} size="small" sx={{ color: 'text.secondary' }}>
          <Close fontSize="small" />
        </IconButton>
      </DialogTitle>

      <DialogContent sx={{ px: 3, pb: 3 }}>
        {/* Method selector chips */}
        <Box sx={{ display: 'flex', gap: 0.75, mb: 2.5 }}>
          {methods.map((m) => (
            <Chip
              key={m.key}
              icon={m.icon as React.ReactElement}
              label={m.label}
              size="small"
              onClick={() => setMethod(m.key)}
              sx={{
                height: 28,
                fontSize: 11,
                fontWeight: method === m.key ? 700 : 400,
                bgcolor: method === m.key ? 'primary.main' : 'rgba(255,255,255,0.06)',
                color: method === m.key ? '#fff' : 'text.secondary',
                '& .MuiChip-icon': {
                  color: method === m.key ? '#fff' : 'text.secondary',
                },
                '&:hover': {
                  bgcolor: method === m.key ? 'primary.dark' : 'rgba(255,255,255,0.1)',
                },
              }}
            />
          ))}
        </Box>

        {/* Input area based on method */}
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
          {method === 'board' && (
            <BoardEntryTab
              fen={boardFen}
              moves={boardMoves}
              onMove={handleBoardMove}
              onUndo={handleBoardUndo}
              onReset={handleBoardReset}
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
              '&:hover': { bgcolor: 'rgba(255,255,255,0.06)' },
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
            bgcolor: 'rgba(255,255,255,0.03)',
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
              sx={{ height: 20, fontSize: 10, bgcolor: 'rgba(255,255,255,0.1)' }}
            />
          )}
        </Box>
      )}
    </Box>
  );
}

// ─── Board Entry Tab ────────────────────

interface BoardEntryTabProps {
  fen: string;
  moves: string[];
  onMove: (from: string, to: string, promotion?: string) => void;
  onUndo: () => void;
  onReset: () => void;
  t: ReturnType<typeof useTranslations>;
}

function BoardEntryTab({ fen, moves, onMove, onUndo, onReset, t }: BoardEntryTabProps) {
  const boardRef = useRef<HTMLDivElement>(null);
  const cgRef = useRef<ReturnType<typeof import('chessground')['Chessground']> | null>(null);
  const chessRef = useRef(new Chess());

  // Keep chess instance in sync
  useEffect(() => {
    chessRef.current.load(fen);
  }, [fen]);

  // Initialize chessground
  useEffect(() => {
    if (!boardRef.current) return;

    let cleanup: (() => void) | undefined;

    import('chessground').then(({ Chessground }) => {
      if (!boardRef.current) return;

      const chess = chessRef.current;
      const dests = getLegalMoves(chess);
      const turnColor = chess.turn() === 'w' ? 'white' : 'black';

      const cg = Chessground(boardRef.current, {
        fen,
        orientation: 'white',
        turnColor,
        movable: {
          free: false,
          color: 'both',
          dests,
        },
        animation: { enabled: true, duration: 150 },
        premovable: { enabled: false },
        events: {
          move: (orig: string, dest: string) => {
            // Check if promotion
            const chess = chessRef.current;
            const piece = chess.get(orig as never);
            if (piece?.type === 'p' && (dest[1] === '8' || dest[1] === '1')) {
              onMove(orig, dest, 'q');
            } else {
              onMove(orig, dest);
            }
          },
        },
      });

      cgRef.current = cg;
      cleanup = () => cg.destroy();
    });

    return () => cleanup?.();
  // Only initialize once
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Update board when fen changes
  useEffect(() => {
    if (!cgRef.current) return;
    const chess = chessRef.current;
    const dests = getLegalMoves(chess);
    const turnColor = chess.turn() === 'w' ? 'white' : 'black';

    cgRef.current.set({
      fen,
      turnColor,
      movable: {
        dests,
        color: 'both',
      },
    });
  }, [fen]);

  return (
    <Box>
      <Box
        ref={boardRef}
        sx={{
          width: '100%',
          maxWidth: 320,
          aspectRatio: '1/1',
          mx: 'auto',
          '& .cg-wrap': { width: '100%', height: '100%' },
        }}
      />
      {/* Move list */}
      {moves.length > 0 && (
        <Box sx={{
          mt: 1.5,
          p: 1,
          bgcolor: 'rgba(255,255,255,0.03)',
          borderRadius: 1,
          maxHeight: 80,
          overflow: 'auto',
        }}>
          <Typography sx={{ fontSize: 11, fontFamily: 'monospace', color: 'text.secondary', lineHeight: 1.6 }}>
            {moves.map((m, i) => (
              <React.Fragment key={i}>
                {i % 2 === 0 && <span style={{ color: 'rgba(255,255,255,0.4)' }}>{Math.floor(i / 2) + 1}. </span>}
                <span style={{ color: '#fff' }}>{m} </span>
              </React.Fragment>
            ))}
          </Typography>
        </Box>
      )}
      {/* Controls */}
      <Box sx={{ display: 'flex', gap: 1, mt: 1, justifyContent: 'center' }}>
        <Button size="small" onClick={onUndo} disabled={moves.length === 0} sx={{ fontSize: 11, textTransform: 'none' }}>
          {t('myGames.addModal.undo')}
        </Button>
        <Button size="small" onClick={onReset} disabled={moves.length === 0} sx={{ fontSize: 11, textTransform: 'none', color: 'error.main' }}>
          {t('myGames.addModal.reset')}
        </Button>
      </Box>
    </Box>
  );
}

function getLegalMoves(chess: Chess) {
  const dests = new Map();
  const moves = chess.moves({ verbose: true });
  for (const move of moves) {
    const existing = dests.get(move.from) || [];
    existing.push(move.to);
    dests.set(move.from, existing);
  }
  return dests;
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
                border: '2px dashed rgba(255,255,255,0.15)',
                borderRadius: 2,
                cursor: 'pointer',
                transition: 'all 0.2s',
                '&:hover': {
                  borderColor: 'primary.main',
                  bgcolor: 'rgba(139, 92, 246, 0.05)',
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
                  <Box key={i} sx={{ width: 80, height: 80, borderRadius: 1, overflow: 'hidden', border: '1px solid rgba(255,255,255,0.1)' }}>
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
        <Box sx={{ p: 1.5, bgcolor: 'rgba(255,255,255,0.03)', borderRadius: 1 }}>
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
            sx={{ fontSize: 12, bgcolor: 'rgba(255,255,255,0.03)' }}
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
    bgcolor: 'rgba(255,255,255,0.03)',
  },
  '& .MuiInputLabel-root': {
    fontSize: 12,
  },
};
