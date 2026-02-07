'use client';

import React, { useState } from 'react';
import {
  Dialog, DialogTitle, DialogContent, DialogActions, Button, TextField,
  Typography, Slider, Box, Alert, Chip, CircularProgress, IconButton,
} from '@mui/material';
import { Close } from '@mui/icons-material';
import type { ImportPgnResult } from '@/hooks/useOpeningRepertoire';

interface PgnImporterProps {
  open: boolean;
  onClose: () => void;
  onImport: (pgn: string, maxPly: number) => Promise<ImportPgnResult>;
  repertoireName: string;
}

const SAMPLE_PGN = `[Event "Caro-Kann Repertoire"]
[Result "*"]

1. e4 c6 2. d4 d5 3. Nc3 dxe4 4. Nxe4 Bf5 5. Ng3 Bg6 6. h4 h6 7. Nf3 Nd7
(5... Nf6 6. Nf3 e6 7. Bd3)
(3... Nf6 4. e5 Nfd7 5. Nf3)
*`;

export default function PgnImporter({ open, onClose, onImport, repertoireName }: PgnImporterProps) {
  const [pgn, setPgn] = useState('');
  const [maxPly, setMaxPly] = useState(30);
  const [importing, setImporting] = useState(false);
  const [result, setResult] = useState<ImportPgnResult | null>(null);

  const handleImport = async () => {
    if (!pgn.trim()) return;
    setImporting(true);
    setResult(null);
    try {
      const res = await onImport(pgn, maxPly);
      setResult(res);
    } catch (e: any) {
      setResult({ imported: 0, skipped: 0, errors: [e.message] });
    } finally {
      setImporting(false);
    }
  };

  const handleReset = () => {
    setPgn('');
    setResult(null);
  };

  const handleClose = () => {
    setPgn('');
    setResult(null);
    setImporting(false);
    onClose();
  };

  return (
    <Dialog
      open={open}
      onClose={handleClose}
      fullWidth
      maxWidth="md"
      PaperProps={{ sx: { bgcolor: '#1e1e1e', color: '#e0e0e0' } }}
    >
      <DialogTitle sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        Import PGN into &ldquo;{repertoireName}&rdquo;
        <IconButton onClick={handleClose} sx={{ color: '#aaa' }}><Close /></IconButton>
      </DialogTitle>

      <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        {!result ? (
          <>
            <TextField
              multiline
              rows={10}
              value={pgn}
              onChange={e => setPgn(e.target.value)}
              placeholder="Paste your PGN here..."
              fullWidth
              sx={{
                '& .MuiInputBase-root': {
                  fontFamily: 'monospace', fontSize: 13, color: '#e0e0e0', bgcolor: '#252525',
                },
                '& .MuiOutlinedInput-notchedOutline': { borderColor: '#444' },
              }}
            />

            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <Button size="small" onClick={() => setPgn(SAMPLE_PGN)} sx={{ color: '#7986cb', fontSize: 11, textTransform: 'none' }}>
                Load Example
              </Button>
            </Box>

            <Box sx={{ px: 1 }}>
              <Typography variant="caption" sx={{ color: '#aaa' }}>Max Ply Depth: {maxPly}</Typography>
              <Slider
                value={maxPly}
                onChange={(_, v) => setMaxPly(v as number)}
                min={5}
                max={50}
                step={5}
                marks={[5, 10, 20, 30, 40, 50].map(v => ({ value: v, label: String(v) }))}
                sx={{ color: '#7986cb', '& .MuiSlider-markLabel': { color: '#777', fontSize: 10 } }}
              />
            </Box>

            <Alert severity="info" sx={{ bgcolor: '#1a237e', color: '#bbdefb', '& .MuiAlert-icon': { color: '#64b5f6' } }}>
              Variations will be imported as separate branches. Duplicate positions are automatically skipped.
            </Alert>
          </>
        ) : (
          <>
            <Alert
              severity={result.errors.length > 0 ? 'warning' : 'success'}
              sx={{
                bgcolor: result.errors.length > 0 ? '#4a2700' : '#1b5e20',
                color: '#fff',
                '& .MuiAlert-icon': { color: '#fff' },
              }}
            >
              {result.errors.length > 0
                ? 'Import completed with some issues.'
                : 'Import completed successfully!'}
            </Alert>

            <Box sx={{ display: 'flex', gap: 1 }}>
              <Chip label={`${result.imported} imported`} sx={{ bgcolor: '#1b5e20', color: '#fff' }} />
              <Chip label={`${result.skipped} skipped`} sx={{ bgcolor: '#555', color: '#ccc' }} />
              <Chip label={`${result.errors.length} errors`} sx={{ bgcolor: result.errors.length > 0 ? '#b71c1c' : '#555', color: '#fff' }} />
            </Box>

            {result.nodes && result.nodes.length > 0 && (
              <Box>
                <Typography variant="caption" sx={{ color: '#aaa', mb: 0.5, display: 'block' }}>Sample imported moves:</Typography>
                {result.nodes.slice(0, 5).map((n, i) => (
                  <Typography key={i} variant="body2" sx={{ color: '#ccc', fontFamily: 'monospace', fontSize: 12 }}>
                    {n.move_san} {n.opening_name ? `— ${n.opening_name}` : ''}
                  </Typography>
                ))}
              </Box>
            )}

            {result.errors.length > 0 && (
              <Box>
                <Typography variant="caption" sx={{ color: '#f44336', mb: 0.5, display: 'block' }}>Errors:</Typography>
                {result.errors.slice(0, 5).map((e, i) => (
                  <Typography key={i} variant="body2" sx={{ color: '#ef9a9a', fontSize: 12 }}>{e}</Typography>
                ))}
              </Box>
            )}
          </>
        )}
      </DialogContent>

      <DialogActions>
        {result ? (
          <>
            <Button onClick={handleReset} sx={{ color: '#7986cb' }}>Import More</Button>
            <Button onClick={handleClose} variant="contained">Done</Button>
          </>
        ) : (
          <>
            <Button onClick={handleClose} sx={{ color: '#aaa' }}>Cancel</Button>
            <Button
              onClick={handleImport}
              variant="contained"
              disabled={!pgn.trim() || importing}
              startIcon={importing ? <CircularProgress size={16} /> : undefined}
            >
              {importing ? 'Importing...' : 'Import'}
            </Button>
          </>
        )}
      </DialogActions>
    </Dialog>
  );
}
