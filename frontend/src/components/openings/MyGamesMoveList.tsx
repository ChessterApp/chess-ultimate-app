'use client';

import React, { useState, useRef, useEffect } from 'react';
import {
  Box,
  Typography,
  IconButton,
  TextField,
  Tooltip,
  Button,
} from '@mui/material';
import { Undo, RestartAlt, ChatBubble, ChatBubbleOutline } from '@mui/icons-material';
import { useTranslations } from 'next-intl';

interface MyGamesMoveListProps {
  moves: string[];
  currentIndex: number;
  comments: Record<number, string>;
  onNavigate: (moveIndex: number) => void;
  onComment: (moveIndex: number, comment: string) => void;
  onUndo: () => void;
  onReset: () => void;
}

export default function MyGamesMoveList({
  moves,
  currentIndex,
  comments,
  onNavigate,
  onComment,
  onUndo,
  onReset,
}: MyGamesMoveListProps) {
  const t = useTranslations('debut');
  const [editingCommentIndex, setEditingCommentIndex] = useState<number | null>(null);
  const [commentText, setCommentText] = useState('');
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to current move
  useEffect(() => {
    if (scrollRef.current) {
      const active = scrollRef.current.querySelector('[data-active="true"]');
      if (active) {
        active.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
      }
    }
  }, [currentIndex]);

  const handleCommentClick = (moveIndex: number) => {
    if (editingCommentIndex === moveIndex) {
      // Close editor
      setEditingCommentIndex(null);
      setCommentText('');
    } else {
      setEditingCommentIndex(moveIndex);
      setCommentText(comments[moveIndex] || '');
    }
  };

  const handleCommentSave = () => {
    if (editingCommentIndex !== null) {
      onComment(editingCommentIndex, commentText);
      setEditingCommentIndex(null);
      setCommentText('');
    }
  };

  const handleCommentKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleCommentSave();
    } else if (e.key === 'Escape') {
      setEditingCommentIndex(null);
      setCommentText('');
    }
  };

  return (
    <Box sx={{
      width: { xs: 'calc(100% - 32px)', sm: 'calc(100% - 24px)', lg: 520 },
      maxWidth: 520,
      mx: 'auto',
      mt: 0.5,
    }}>
      {/* Move list */}
      <Box
        ref={scrollRef}
        sx={{
          maxHeight: 120,
          overflow: 'auto',
          p: 1,
          bgcolor: 'rgba(255,255,255,0.03)',
          borderRadius: '12px',
          border: '1px solid rgba(255,255,255,0.08)',
          fontFamily: 'monospace',
          fontSize: 12,
          lineHeight: 1.8,
          display: 'flex',
          flexWrap: 'wrap',
          gap: '2px',
          alignItems: 'center',
          '&::-webkit-scrollbar': { width: 4 },
          '&::-webkit-scrollbar-thumb': { bgcolor: 'rgba(255,255,255,0.2)', borderRadius: 2 },
        }}
      >
        {moves.length === 0 ? (
          <Typography sx={{ color: 'text.secondary', fontSize: 11, fontStyle: 'italic', fontFamily: 'inherit' }}>
            {t('startingPosition')}
          </Typography>
        ) : (
          moves.map((san, idx) => {
            const moveNumber = Math.floor(idx / 2) + 1;
            const isWhite = idx % 2 === 0;
            const moveIdx = idx + 1; // 1-based for navigation (1 = after first move)
            const isActive = moveIdx === currentIndex;
            const hasComment = !!comments[moveIdx];

            return (
              <React.Fragment key={idx}>
                {isWhite && (
                  <Typography
                    component="span"
                    sx={{ color: 'text.secondary', fontSize: 'inherit', fontFamily: 'inherit', mr: '2px' }}
                  >
                    {moveNumber}.
                  </Typography>
                )}
                <Typography
                  component="span"
                  data-active={isActive}
                  onClick={() => onNavigate(moveIdx)}
                  sx={{
                    color: isActive ? 'primary.main' : 'text.primary',
                    fontSize: 'inherit',
                    fontFamily: 'inherit',
                    fontWeight: isActive ? 700 : 400,
                    cursor: 'pointer',
                    px: '3px',
                    borderRadius: '4px',
                    bgcolor: isActive ? 'rgba(124,58,237,0.15)' : 'transparent',
                    '&:hover': { bgcolor: isActive ? 'rgba(124,58,237,0.2)' : 'rgba(255,255,255,0.06)' },
                    transition: 'all 0.1s',
                  }}
                >
                  {san}
                </Typography>
                {hasComment && (
                  <Tooltip title={comments[moveIdx]} arrow placement="top">
                    <ChatBubble
                      onClick={(e) => { e.stopPropagation(); handleCommentClick(moveIdx); }}
                      sx={{
                        fontSize: 10,
                        color: 'primary.main',
                        cursor: 'pointer',
                        opacity: 0.7,
                        '&:hover': { opacity: 1 },
                        mx: '1px',
                        verticalAlign: 'middle',
                      }}
                    />
                  </Tooltip>
                )}
                {!hasComment && isActive && (
                  <ChatBubbleOutline
                    onClick={(e) => { e.stopPropagation(); handleCommentClick(moveIdx); }}
                    sx={{
                      fontSize: 10,
                      color: 'text.secondary',
                      cursor: 'pointer',
                      opacity: 0.4,
                      '&:hover': { opacity: 0.8 },
                      mx: '1px',
                      verticalAlign: 'middle',
                    }}
                  />
                )}
              </React.Fragment>
            );
          })
        )}
      </Box>

      {/* Comment editor */}
      {editingCommentIndex !== null && (
        <Box sx={{ mt: 0.5, px: 0.5 }}>
          <TextField
            size="small"
            fullWidth
            multiline
            maxRows={3}
            value={commentText}
            onChange={(e) => setCommentText(e.target.value)}
            onKeyDown={handleCommentKeyDown}
            onBlur={handleCommentSave}
            placeholder={t('myGames.commentPlaceholder')}
            autoFocus
            sx={{
              '& .MuiOutlinedInput-root': {
                fontSize: 11,
                fontFamily: 'monospace',
                bgcolor: 'rgba(255,255,255,0.03)',
                borderRadius: '8px',
              },
            }}
          />
        </Box>
      )}

      {/* Controls */}
      <Box sx={{ display: 'flex', gap: 0.5, mt: 0.5, justifyContent: 'center' }}>
        <Button
          size="small"
          startIcon={<Undo sx={{ fontSize: 14 }} />}
          onClick={onUndo}
          disabled={moves.length === 0}
          sx={{
            fontSize: 11,
            textTransform: 'none',
            color: 'text.secondary',
            minWidth: 0,
            px: 1.5,
            '&:hover': { bgcolor: 'rgba(255,255,255,0.06)' },
          }}
        >
          {t('myGames.undoMove')}
        </Button>
        <Button
          size="small"
          startIcon={<RestartAlt sx={{ fontSize: 14 }} />}
          onClick={onReset}
          disabled={moves.length === 0}
          sx={{
            fontSize: 11,
            textTransform: 'none',
            color: 'error.main',
            minWidth: 0,
            px: 1.5,
            '&:hover': { bgcolor: 'rgba(255,255,255,0.06)' },
          }}
        >
          {t('myGames.resetMoves')}
        </Button>
      </Box>
    </Box>
  );
}
