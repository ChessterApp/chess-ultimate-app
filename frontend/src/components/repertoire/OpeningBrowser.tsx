'use client';

/**
 * OpeningBrowser Component
 * Browse and search for openings to add to repertoire
 * Currently uses mock data - can be integrated with backend opening database
 */

import React, { useState, useMemo } from 'react';
import {
  Box,
  TextField,
  Select,
  MenuItem,
  Button,
  Card,
  CardContent,
  Typography,
  CircularProgress,
  Alert,
  FormControl,
  InputLabel,
} from '@mui/material';
import { Add as AddIcon } from '@mui/icons-material';
import { useTranslations } from 'next-intl';

import { RepertoireOpening, AddOpeningRequest } from '@/types/repertoire';
import AddOpeningDialog from './AddOpeningDialog';

interface OpeningSearchResult {
  id: string;
  name: string;
  eco_code: string;
  moves: string;
  description?: string;
}

interface OpeningBrowserProps {
  onAddToRepertoire: (opening: AddOpeningRequest) => Promise<RepertoireOpening>;
  existingRepertoire: RepertoireOpening[];
}

// Mock data - in production, this would come from backend opening API
const MOCK_OPENINGS: OpeningSearchResult[] = [
  {
    id: 'ruy-lopez',
    name: 'Ruy Lopez',
    eco_code: 'C60-C99',
    moves: '1.e4 e5 2.Nf3 Nc6 3.Bb5',
    description: 'One of the most popular and respected openings in chess',
  },
  {
    id: 'sicilian-defense',
    name: 'Sicilian Defense',
    eco_code: 'B20-B99',
    moves: '1.e4 c5',
    description: 'The most popular response to 1.e4',
  },
  {
    id: 'french-defense',
    name: 'French Defense',
    eco_code: 'C00-C19',
    moves: '1.e4 e6',
    description: 'A solid and flexible opening for Black',
  },
  {
    id: 'caro-kann',
    name: 'Caro-Kann Defense',
    eco_code: 'B10-B19',
    moves: '1.e4 c6',
    description: 'Solid and safe defense for Black',
  },
  {
    id: 'kings-indian',
    name: "King's Indian Defense",
    eco_code: 'E60-E99',
    moves: '1.d4 Nf6 2.c4 g6',
    description: 'Dynamic and flexible opening for Black',
  },
  {
    id: 'queens-gambit',
    name: "Queen's Gambit",
    eco_code: 'D04-D69',
    moves: '1.d4 d5 2.c4',
    description: 'Classic opening with active play for White',
  },
  {
    id: 'london-system',
    name: 'London System',
    eco_code: 'D20',
    moves: '1.d4 d5 2.Bf4',
    description: 'A solid and systematic approach',
  },
  {
    id: 'italian-game',
    name: 'Italian Game',
    eco_code: 'C50-C59',
    moves: '1.e4 e5 2.Nf3 Nc6 3.Bc4',
    description: 'Open and aggressive opening',
  },
];

export default function OpeningBrowser({
  onAddToRepertoire,
  existingRepertoire,
}: OpeningBrowserProps) {
  const t = useTranslations();
  const [searchQuery, setSearchQuery] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('all');
  const [selectedOpening, setSelectedOpening] = useState<OpeningSearchResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Filter and search openings
  const filteredOpenings = useMemo(() => {
    return MOCK_OPENINGS.filter((opening) => {
      const matchesSearch =
        opening.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        opening.eco_code.toLowerCase().includes(searchQuery.toLowerCase()) ||
        opening.moves.toLowerCase().includes(searchQuery.toLowerCase());

      // In production, categoryFilter would filter by type (open, semi-open, closed, etc.)
      return matchesSearch;
    });
  }, [searchQuery, categoryFilter]);

  const isInRepertoire = (openingId: string) => {
    return existingRepertoire.some((o) => o.opening_id === openingId);
  };

  const handleAddOpening = async (request: AddOpeningRequest) => {
    setLoading(true);
    try {
      await onAddToRepertoire(request);
      setSelectedOpening(null);
      setError(null);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to add opening';
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Box>
      {/* Search and Filter Section */}
      <Box sx={{ display: 'flex', gap: 2, mb: 3, flexWrap: 'wrap', alignItems: 'flex-end' }}>
        {/* Search Input */}
        <TextField
          label={t('repertoire.searchOpenings')}
          placeholder="e.g., Sicilian, Ruy Lopez, e4"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          sx={{ flex: 1, minWidth: '250px' }}
          size="small"
        />

        {/* Category Filter */}
        <FormControl sx={{ minWidth: '150px' }} size="small">
          <InputLabel>{t('repertoire.category')}</InputLabel>
          <Select value={categoryFilter} onChange={(e) => setCategoryFilter(e.target.value)} label={t('repertoire.category')}>
            <MenuItem value="all">{t('repertoire.allOpenings')}</MenuItem>
            <MenuItem value="open">{t('repertoire.openGames')}</MenuItem>
            <MenuItem value="semi-open">{t('repertoire.semiOpen')}</MenuItem>
            <MenuItem value="closed">{t('repertoire.closedGames')}</MenuItem>
          </Select>
        </FormControl>
      </Box>

      {/* Error Message */}
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      {/* Results Counter */}
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 2 }}>
        {filteredOpenings.length} {t('repertoire.openingsFound')}
      </Typography>

      {/* Openings List */}
      {filteredOpenings.length === 0 ? (
        <Alert severity="info">{t('repertoire.noOpeningsFound')}</Alert>
      ) : (
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
          {filteredOpenings.map((opening) => {
            const inRepertoire = isInRepertoire(opening.id);

            return (
              <Card
                key={opening.id}
                variant="outlined"
                sx={{
                  '&:hover': {
                    boxShadow: 1,
                  },
                  opacity: inRepertoire ? 0.6 : 1,
                  transition: 'all 0.2s ease',
                }}
              >
                <CardContent sx={{ pb: 1 }}>
                  {/* Opening Name and ECO Code */}
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 0.5 }}>
                    <Typography variant="subtitle1" sx={{ fontWeight: 600, flex: 1 }}>
                      {opening.name}
                    </Typography>
                    <Typography
                      variant="caption"
                      sx={{
                        backgroundColor: 'action.hover',
                        px: 1,
                        py: 0.5,
                        borderRadius: 1,
                        fontFamily: 'monospace',
                      }}
                    >
                      {opening.eco_code}
                    </Typography>
                  </Box>

                  {/* Moves */}
                  <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.5 }}>
                    {opening.moves}
                  </Typography>

                  {/* Description */}
                  {opening.description && (
                    <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                      {opening.description}
                    </Typography>
                  )}

                  {/* Add Button */}
                  <Button
                    size="small"
                    variant={inRepertoire ? 'outlined' : 'contained'}
                    startIcon={!inRepertoire && <AddIcon />}
                    onClick={() => setSelectedOpening(opening)}
                    disabled={inRepertoire || loading}
                  >
                    {inRepertoire
                      ? t('repertoire.inRepertoire')
                      : t('repertoire.addToRepertoire')}
                  </Button>
                </CardContent>
              </Card>
            );
          })}
        </Box>
      )}

      {/* Add Opening Dialog */}
      {selectedOpening && (
        <AddOpeningDialog
          opening={selectedOpening}
          onAdd={handleAddOpening}
          onClose={() => setSelectedOpening(null)}
          loading={loading}
        />
      )}
    </Box>
  );
}
