import { useState, useEffect, useCallback } from 'react';
import { Color } from 'chess.js';
import { ThemeScore } from '@/lib/themes/helper';
import { apiFetch, ApiError } from '@/lib/api';

interface UseThemeScoreResult {
    scores: ThemeScore | null;
    loading: boolean;
    error: string | null;
    refetch: () => Promise<void>;
}

export function useThemeScore(fen: string | null, color: Color): UseThemeScoreResult {
    const [scores, setScores] = useState<ThemeScore | null>(null);
    const [loading, setLoading] = useState<boolean>(false);
    const [error, setError] = useState<string | null>(null);

    const fetchThemeScore = useCallback(async () => {
        if (!fen) {
            setScores(null);
            setError(null);
            return;
        }

        setLoading(true);
        setError(null);

        try {
            const data = await apiFetch<ThemeScore>('/api/themescore', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ fen, color }),
            });
            setScores(data);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'An unknown error occurred');
            setScores(null);
        } finally {
            setLoading(false);
        }
    }, [fen, color]);

    useEffect(() => {
        fetchThemeScore();
    }, [fetchThemeScore]);

    return {
        scores,
        loading,
        error,
        refetch: fetchThemeScore,
    };
}

