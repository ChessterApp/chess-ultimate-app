'use client';

import React, { useState, useRef, useEffect } from 'react';
import {
  Box,
  Typography,
  TextField,
  Tooltip,
  Menu,
  MenuItem,
  ListItemIcon,
  ListItemText,
} from '@mui/material';
import { ChatBubble, ChatBubbleOutline, Delete, AddComment, ModeComment } from '@mui/icons-material';
import { useTranslations } from 'next-intl';

interface MyGamesMoveListProps {
  moves: string[];
  currentIndex: number;
  comments: Record<number, string>;
  onNavigate: (moveIndex: number) => void;
  onComment: (moveIndex: number, comment: string) => void;
  /** Removes the move at this 1-based index and everything after it. */
  onDeleteMove: (moveIndex: number) => void;
}

export default function MyGamesMoveList({
  moves,
  currentIndex,
  comments,
  onNavigate,
  onComment,
  onDeleteMove,
}: MyGamesMoveListProps) {
  const t = useTranslations('debut');
  const [editingCommentIndex, setEditingCommentIndex] = useState<number | null>(null);
  const [commentText, setCommentText] = useState('');
  // Move actions menu — opened by tapping the current move again or right-click.
  const [menu, setMenu] = useState<{ anchor: HTMLElement; moveIndex: number } | null>(null);
  // The comment editor opens once the menu has fully closed so its focus
  // restore can't blur-save the freshly focused field.
  const pendingCommentRef = useRef<number | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to current move (container-scoped, avoids page scroll anchoring issues)
  useEffect(() => {
    const container = scrollRef.current;
    if (!container) return;
    const active = container.querySelector('[data-active="true"]') as HTMLElement | null;
    if (!active) return;
    const elTop = active.offsetTop;
    const elBottom = elTop + active.offsetHeight;
    const scrollTop = container.scrollTop;
    const viewBottom = scrollTop + container.clientHeight;
    if (elTop < scrollTop) {
      container.scrollTop = elTop;
    } else if (elBottom > viewBottom) {
      container.scrollTop = elBottom - container.clientHeight;
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

  const handleMoveClick = (e: React.MouseEvent<HTMLElement>, moveIdx: number) => {
    if (moveIdx === currentIndex) setMenu({ anchor: e.currentTarget, moveIndex: moveIdx });
    else onNavigate(moveIdx);
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

  if (moves.length === 0) return null;

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
        {moves.map((san, idx) => {
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
                onClick={(e) => handleMoveClick(e, moveIdx)}
                onContextMenu={(e) => {
                  e.preventDefault();
                  setMenu({ anchor: e.currentTarget, moveIndex: moveIdx });
                }}
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
        })}
      </Box>

      <Menu
        open={!!menu}
        anchorEl={menu?.anchor}
        onClose={() => setMenu(null)}
        disableRestoreFocus
        slotProps={{
          transition: {
            onExited: () => {
              if (pendingCommentRef.current !== null) handleCommentClick(pendingCommentRef.current);
              pendingCommentRef.current = null;
            },
          },
          paper: { sx: { minWidth: 180 } },
        }}
      >
        <MenuItem
          onClick={() => {
            if (menu) onDeleteMove(menu.moveIndex);
            setMenu(null);
          }}
          sx={{ fontSize: 13, minHeight: 44 }}
        >
          <ListItemIcon><Delete fontSize="small" sx={{ color: 'error.main' }} /></ListItemIcon>
          <ListItemText primaryTypographyProps={{ fontSize: 13 }}>{t('myGames.moveEdit.deleteMove')}</ListItemText>
        </MenuItem>
        <MenuItem
          onClick={() => {
            if (menu) pendingCommentRef.current = menu.moveIndex;
            setMenu(null);
          }}
          sx={{ fontSize: 13, minHeight: 44 }}
        >
          <ListItemIcon>
            {menu && comments[menu.moveIndex]
              ? <ModeComment fontSize="small" sx={{ color: 'primary.main' }} />
              : <AddComment fontSize="small" sx={{ color: 'primary.main' }} />}
          </ListItemIcon>
          <ListItemText primaryTypographyProps={{ fontSize: 13 }}>
            {menu && comments[menu.moveIndex] ? t('myGames.moveEdit.editComment') : t('myGames.moveEdit.addComment')}
          </ListItemText>
        </MenuItem>
      </Menu>

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
    </Box>
  );
}
