import React, { useState, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import {
  Box,
  Button,
  TextField,
  Typography,
  Stack,
  Alert,
  Chip,
  Paper,
  LinearProgress,
  IconButton,
  Tooltip,
  List,
  ListItem,
  ListItemText,
} from '@mui/material';
import {
  Upload,
  Close,
  ContentCopy,
  Download,
  Check,
  Warning,
} from '@mui/icons-material';
import { apiFetch, ApiError } from '@/lib/api';

interface ScoresheetScannerProps {
  onGameLoaded?: (pgn: string, fen: string) => void;
}

interface MoveCorrection {
  move_number: number;
  original: string;
  corrected: string;
  reason: string;
}

interface ScoresheetResult {
  pgn: string;
  moves_total: number;
  moves_corrected: number;
  corrections: MoveCorrection[];
  confidence: number;
  fen_final: string;
}

export default function ScoresheetScanner({ onGameLoaded }: ScoresheetScannerProps) {
  const t = useTranslations('scoresheet');

  // UI state
  const [images, setImages] = useState<string[]>([]);
  const [imagePreviews, setImagePreviews] = useState<string[]>([]);
  const [metadata, setMetadata] = useState({
    white: '',
    black: '',
    event: '',
    date: '',
  });

  // Processing state
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>('');
  const [result, setResult] = useState<ScoresheetResult | null>(null);
  const [copied, setCopied] = useState(false);

  // Handle file upload
  const handleFileUpload = useCallback((event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files;
    if (!files) return;

    const fileArray = Array.from(files).slice(0, 2); // Max 2 images

    // Convert to base64
    const readers = fileArray.map((file) => {
      return new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => {
          const base64 = reader.result as string;
          const base64Data = base64.split(',')[1]; // Remove data:image/...;base64, prefix
          resolve(base64Data);
        };
        reader.onerror = reject;
        reader.readAsDataURL(file);
      });
    });

    // Also create preview URLs
    const previewUrls = fileArray.map((file) => URL.createObjectURL(file));
    setImagePreviews(previewUrls);

    // Wait for all readers to complete
    Promise.all(readers)
      .then((base64Images) => {
        setImages(base64Images);
        setError('');
      })
      .catch((err) => {
        console.error('Error reading files:', err);
        setError('Failed to read image files');
      });
  }, []);

  // Handle scan
  const handleScan = useCallback(async () => {
    if (images.length === 0) {
      setError(t('noImagesError'));
      return;
    }

    setLoading(true);
    setError('');
    setResult(null);

    try {
      const data = await apiFetch<ScoresheetResult>('/api/convert-scoresheet', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          images,
          metadata: {
            white: metadata.white || undefined,
            black: metadata.black || undefined,
            event: metadata.event || undefined,
            date: metadata.date || undefined,
          },
        }),
      });

      setResult(data);
    } catch (e) {
      if (e instanceof ApiError) {
        setError(e.message || t('scanError'));
      } else {
        setError(t('networkError'));
      }
    } finally {
      setLoading(false);
    }
  }, [images, metadata, t]);

  // Copy PGN to clipboard
  const handleCopyPGN = useCallback(() => {
    if (result?.pgn) {
      navigator.clipboard.writeText(result.pgn);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  }, [result]);

  // Download PGN
  const handleDownloadPGN = useCallback(() => {
    if (result?.pgn) {
      const blob = new Blob([result.pgn], { type: 'text/plain' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'scoresheet.pgn';
      a.click();
      URL.revokeObjectURL(url);
    }
  }, [result]);

  // Load into board
  const handleLoadIntoBoard = useCallback(() => {
    if (result && onGameLoaded) {
      onGameLoaded(result.pgn, result.fen_final);
    }
  }, [result, onGameLoaded]);

  // Clear all
  const handleClear = useCallback(() => {
    setImages([]);
    setImagePreviews([]);
    setResult(null);
    setError('');
    setMetadata({ white: '', black: '', event: '', date: '' });
  }, []);

  return (
    <Box sx={{ width: '100%' }}>
      <Stack spacing={3}>
        {/* Upload Area */}
        {images.length === 0 ? (
          <Paper
            sx={{
              p: 4,
              textAlign: 'center',
              border: '2px dashed',
              borderColor: 'divider',
              backgroundColor: 'background.default',
              cursor: 'pointer',
              transition: 'all 0.2s',
              '&:hover': {
                borderColor: 'primary.main',
                backgroundColor: 'action.hover',
              },
            }}
            component="label"
          >
            <input
              type="file"
              accept="image/*"
              multiple
              hidden
              onChange={handleFileUpload}
            />
            <Upload sx={{ fontSize: 48, color: 'text.secondary', mb: 2 }} />
            <Typography variant="h6" gutterBottom>
              {t('uploadTitle')}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {t('uploadSubtitle')}
            </Typography>
          </Paper>
        ) : (
          <Box>
            <Typography variant="subtitle2" gutterBottom>
              {t('imagesUploaded', { count: images.length })}
            </Typography>
            <Stack direction="row" spacing={2}>
              {imagePreviews.map((preview, idx) => (
                <Box
                  key={idx}
                  sx={{
                    position: 'relative',
                    width: 150,
                    height: 150,
                    borderRadius: 1,
                    overflow: 'hidden',
                    border: '1px solid',
                    borderColor: 'divider',
                  }}
                >
                  <img
                    src={preview}
                    alt={`Scoresheet ${idx + 1}`}
                    style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                  />
                </Box>
              ))}
              <IconButton onClick={handleClear} sx={{ alignSelf: 'flex-start' }}>
                <Close />
              </IconButton>
            </Stack>
          </Box>
        )}

        {/* Metadata Fields */}
        {images.length > 0 && !result && (
          <Stack spacing={2}>
            <Typography variant="subtitle2">{t('optionalMetadata')}</Typography>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
              <TextField
                label={t('whitePlayer')}
                value={metadata.white}
                onChange={(e) => setMetadata({ ...metadata, white: e.target.value })}
                size="small"
                fullWidth
              />
              <TextField
                label={t('blackPlayer')}
                value={metadata.black}
                onChange={(e) => setMetadata({ ...metadata, black: e.target.value })}
                size="small"
                fullWidth
              />
            </Stack>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
              <TextField
                label={t('eventName')}
                value={metadata.event}
                onChange={(e) => setMetadata({ ...metadata, event: e.target.value })}
                size="small"
                fullWidth
              />
              <TextField
                label={t('date')}
                value={metadata.date}
                onChange={(e) => setMetadata({ ...metadata, date: e.target.value })}
                size="small"
                fullWidth
                placeholder="YYYY.MM.DD"
              />
            </Stack>
          </Stack>
        )}

        {/* Scan Button */}
        {images.length > 0 && !result && (
          <Button
            variant="contained"
            onClick={handleScan}
            disabled={loading}
            startIcon={loading ? undefined : <Check />}
            fullWidth
          >
            {loading ? t('scanning') : t('scanButton')}
          </Button>
        )}

        {/* Loading Progress */}
        {loading && (
          <Box>
            <LinearProgress />
            <Typography variant="caption" color="text.secondary" sx={{ mt: 1 }}>
              {t('scanningProgress')}
            </Typography>
          </Box>
        )}

        {/* Error */}
        {error && (
          <Alert severity="error" onClose={() => setError('')}>
            {error}
          </Alert>
        )}

        {/* Results */}
        {result && (
          <Stack spacing={2}>
            {/* Confidence Badge */}
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <Chip
                label={`${t('confidence')}: ${Math.round(result.confidence * 100)}%`}
                color={result.confidence > 0.9 ? 'success' : result.confidence > 0.7 ? 'warning' : 'error'}
                size="small"
              />
              <Chip
                label={`${result.moves_total} ${t('moves')}`}
                size="small"
              />
              {result.moves_corrected > 0 && (
                <Chip
                  icon={<Warning />}
                  label={`${result.moves_corrected} ${t('corrected')}`}
                  color="warning"
                  size="small"
                />
              )}
            </Box>

            {/* PGN Display */}
            <Paper
              sx={{
                p: 2,
                backgroundColor: 'background.default',
                maxHeight: 200,
                overflow: 'auto',
              }}
            >
              <Typography
                variant="body2"
                component="pre"
                sx={{
                  fontFamily: 'monospace',
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word',
                }}
              >
                {result.pgn}
              </Typography>
            </Paper>

            {/* Corrections List */}
            {result.corrections.length > 0 && (
              <Box>
                <Typography variant="subtitle2" gutterBottom>
                  {t('corrections')}:
                </Typography>
                <List dense>
                  {result.corrections.map((correction, idx) => (
                    <ListItem key={idx} sx={{ py: 0.5 }}>
                      <ListItemText
                        primary={
                          <Typography variant="body2">
                            {t('moveNumber', { number: correction.move_number })}:
                            <Box component="span" sx={{ color: 'error.main', mx: 1 }}>
                              {correction.original}
                            </Box>
                            →
                            <Box component="span" sx={{ color: 'success.main', mx: 1 }}>
                              {correction.corrected}
                            </Box>
                          </Typography>
                        }
                        secondary={correction.reason}
                      />
                    </ListItem>
                  ))}
                </List>
              </Box>
            )}

            {/* Action Buttons */}
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
              <Tooltip title={copied ? t('copied') : t('copyPGN')}>
                <Button
                  variant="outlined"
                  startIcon={copied ? <Check /> : <ContentCopy />}
                  onClick={handleCopyPGN}
                  fullWidth
                >
                  {t('copyPGN')}
                </Button>
              </Tooltip>
              <Button
                variant="outlined"
                startIcon={<Download />}
                onClick={handleDownloadPGN}
                fullWidth
              >
                {t('downloadPGN')}
              </Button>
              {onGameLoaded && (
                <Button
                  variant="contained"
                  onClick={handleLoadIntoBoard}
                  fullWidth
                >
                  {t('loadIntoBoard')}
                </Button>
              )}
            </Stack>

            {/* Scan Another */}
            <Button variant="text" onClick={handleClear}>
              {t('scanAnother')}
            </Button>
          </Stack>
        )}
      </Stack>
    </Box>
  );
}
