'use client';

import React, { useMemo, useRef, useEffect, useState, useCallback } from 'react';
import { Box, Typography, IconButton, Tooltip, Menu, MenuItem, ListItemIcon, ListItemText, InputBase } from '@mui/material';
import { Backspace, DeleteSweep, Delete, TrendingUp, ArrowUpward, Star, AddComment, ModeComment } from '@mui/icons-material';
import type { OpeningNode } from '@/hooks/useOpeningRepertoire';

export interface MoveContextMenuActions {
  onDeleteFromHere?: (node: OpeningNode) => void;
  onDeleteVariation?: (node: OpeningNode) => void;
  onPromoteVariation?: (node: OpeningNode) => void;
  onMakeMainLine?: (node: OpeningNode) => void;
  /** Enables inline comments: rendered after each move and editable in place. */
  onCommentChange?: (node: OpeningNode, text: string) => void;
  labels?: {
    deleteFromHere?: string;
    deleteVariation?: string;
    promoteVariation?: string;
    makeMainLine?: string;
    addComment?: string;
    editComment?: string;
    commentPlaceholder?: string;
  };
}

type RenderComment = (node: OpeningNode) => React.ReactNode;

function CommentText({ text, onClick }: { text: string; onClick: () => void }) {
  return (
    <Typography
      component="span"
      data-testid="move-comment"
      onClick={onClick}
      sx={{
        color: 'text.secondary',
        fontStyle: 'italic',
        fontSize: '12px',
        px: '3px',
        cursor: 'text',
        borderRadius: '2px',
        '&:hover': { bgcolor: 'action.hover' },
      }}
    >
      {text}
    </Typography>
  );
}

function CommentEditor({ initial, placeholder, onDone }: {
  initial: string;
  placeholder?: string;
  onDone: (text: string | null) => void; // null = cancelled
}) {
  const [value, setValue] = useState(initial);
  const doneRef = useRef(false);
  const finish = (text: string | null) => {
    if (doneRef.current) return;
    doneRef.current = true;
    onDone(text);
  };
  return (
    <InputBase
      autoFocus
      value={value}
      placeholder={placeholder}
      onChange={(e) => setValue(e.target.value)}
      onBlur={() => finish(value)}
      onKeyDown={(e) => {
        if (e.key === 'Enter') { e.preventDefault(); finish(value); }
        else if (e.key === 'Escape') { e.preventDefault(); finish(null); }
      }}
      inputProps={{ 'aria-label': placeholder, 'data-testid': 'move-comment-input' }}
      sx={{
        flex: '1 1 160px',
        minWidth: 120,
        fontSize: '12px',
        fontStyle: 'italic',
        px: '4px',
        border: 1,
        borderColor: 'primary.main',
        borderRadius: '4px',
        '& input': { py: '1px' },
      }}
    />
  );
}

interface MoveNotationProps {
  tree: OpeningNode | null;
  selectedNodeId: string | null;
  onNodeSelect: (node: OpeningNode) => void;
  onDeleteLast?: () => void;
  onDeleteAll?: () => void;
  loading: boolean;
  contextMenuActions?: MoveContextMenuActions;
}

function MoveSpan({
  node,
  isSelected,
  selectedRef,
  onNodeSelect,
  onContextMenu,
}: {
  node: OpeningNode;
  isSelected: boolean;
  selectedRef: React.RefObject<HTMLSpanElement | null>;
  onNodeSelect: (node: OpeningNode) => void;
  onContextMenu?: (e: React.MouseEvent, node: OpeningNode) => void;
}) {
  return (
    <Typography
      ref={isSelected ? selectedRef : null}
      component="span"
      onClick={() => onNodeSelect(node)}
      onContextMenu={onContextMenu ? (e) => onContextMenu(e, node) : undefined}
      sx={{
        color: isSelected ? 'text.primary' : 'text.secondary',
        bgcolor: isSelected ? 'action.hover' : 'transparent',
        fontFamily: 'monospace',
        fontSize: '12px',
        fontWeight: isSelected ? 600 : 400,
        px: '3px',
        py: '1px',
        borderRadius: '2px',
        cursor: 'pointer',
        transition: 'background-color 0.1s',
        '&:hover': {
          bgcolor: isSelected ? 'action.selected' : 'action.hover',
          color: 'text.primary',
        },
      }}
    >
      {node.move_san}
    </Typography>
  );
}

function MoveNumber({ text }: { text: string }) {
  return (
    <Typography
      component="span"
      sx={{
        color: 'text.secondary',
        fontFamily: 'monospace',
        fontSize: '12px',
        fontWeight: 500,
        mr: '3px',
        flexShrink: 0,
        userSelect: 'none',
      }}
    >
      {text}
    </Typography>
  );
}

function renderNode(
  node: OpeningNode,
  depth: number,
  isFirst: boolean,
  selectedNodeId: string | null,
  onNodeSelect: (node: OpeningNode) => void,
  selectedRef: React.RefObject<HTMLSpanElement | null>,
  onContextMenu?: (e: React.MouseEvent, node: OpeningNode) => void,
  renderComment?: RenderComment,
): React.ReactNode[] {
  const elements: React.ReactNode[] = [];
  const key = node.id;
  const isSelected = node.id === selectedNodeId;

  if (node.is_white_move) {
    elements.push(<MoveNumber key={`mn-${key}`} text={`${node.move_number}.`} />);
  } else if (isFirst) {
    elements.push(<MoveNumber key={`mn-${key}`} text={`${node.move_number}…`} />);
  }

  elements.push(
    <MoveSpan
      key={`m-${key}`}
      node={node}
      isSelected={isSelected}
      selectedRef={selectedRef}
      onNodeSelect={onNodeSelect}
      onContextMenu={onContextMenu}
    />
  );

  const comment = renderComment?.(node);
  if (comment) elements.push(<React.Fragment key={`c-${key}`}>{comment}</React.Fragment>);

  const children = node.children || [];
  if (children.length === 0) return elements;

  elements.push(
    // A comment breaks the move pair, so the next black move gets its number back
    ...renderNode(children[0], depth, !!comment, selectedNodeId, onNodeSelect, selectedRef, onContextMenu, renderComment)
  );

  for (let i = 1; i < children.length; i++) {
    const alt = children[i];
    elements.push(
      <Box
        key={`var-${alt.id}`}
        component="span"
        sx={{
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'baseline',
          gap: '0px 2px',
          width: '100%',
          pl: `${Math.min((depth + 1) * 10, 40)}px`,
          fontFamily: 'monospace',
          fontSize: '12px',
        }}
      >
        <Typography
          component="span"
          sx={{ color: 'text.secondary', fontFamily: 'monospace', fontSize: '12px', userSelect: 'none' }}
        >
          (
        </Typography>
        {renderNode(alt, depth + 1, true, selectedNodeId, onNodeSelect, selectedRef, onContextMenu, renderComment)}
        <Typography
          component="span"
          sx={{ color: 'text.secondary', fontFamily: 'monospace', fontSize: '12px', userSelect: 'none' }}
        >
          )
        </Typography>
      </Box>
    );
  }

  return elements;
}

function renderTree(
  root: OpeningNode,
  selectedNodeId: string | null,
  onNodeSelect: (node: OpeningNode) => void,
  selectedRef: React.RefObject<HTMLSpanElement | null>,
  onContextMenu?: (e: React.MouseEvent, node: OpeningNode) => void,
  renderComment?: RenderComment,
): React.ReactNode[] {
  const children = root.children || [];
  const rootComment = renderComment?.(root);
  if (children.length === 0) return rootComment ? [<React.Fragment key="c-root">{rootComment}</React.Fragment>] : [];

  const elements: React.ReactNode[] = [];
  if (rootComment) elements.push(<React.Fragment key="c-root">{rootComment}</React.Fragment>);

  elements.push(
    ...renderNode(children[0], 0, true, selectedNodeId, onNodeSelect, selectedRef, onContextMenu, renderComment)
  );

  for (let i = 1; i < children.length; i++) {
    const alt = children[i];
    elements.push(
      <Box
        key={`rootvar-${alt.id}`}
        component="span"
        sx={{
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'baseline',
          gap: '0px 2px',
          width: '100%',
          pl: '10px',
          fontFamily: 'monospace',
          fontSize: '12px',
        }}
      >
        <Typography
          component="span"
          sx={{ color: 'text.secondary', fontFamily: 'monospace', fontSize: '12px', userSelect: 'none' }}
        >
          (
        </Typography>
        {renderNode(alt, 1, true, selectedNodeId, onNodeSelect, selectedRef, onContextMenu, renderComment)}
        <Typography
          component="span"
          sx={{ color: 'text.secondary', fontFamily: 'monospace', fontSize: '12px', userSelect: 'none' }}
        >
          )
        </Typography>
      </Box>
    );
  }

  return elements;
}

export default function MoveNotation({ tree, selectedNodeId, onNodeSelect, onDeleteLast, onDeleteAll, loading, contextMenuActions }: MoveNotationProps) {
  const selectedRef = useRef<HTMLSpanElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [contextMenu, setContextMenu] = useState<{ x: number; y: number; node: OpeningNode } | null>(null);
  const [editingCommentId, setEditingCommentId] = useState<string | null>(null);
  // Comment chosen from the context menu; the editor opens once the menu has
  // fully closed so its focus trap can't steal focus (and blur-save) the input.
  const pendingCommentIdRef = useRef<string | null>(null);
  const onCommentChange = contextMenuActions?.onCommentChange;
  const commentPlaceholder = contextMenuActions?.labels?.commentPlaceholder;

  useEffect(() => {
    const el = selectedRef.current;
    const container = containerRef.current;
    if (!el || !container) return;
    const elTop = el.offsetTop;
    const elBottom = elTop + el.offsetHeight;
    const scrollTop = container.scrollTop;
    const viewBottom = scrollTop + container.clientHeight;
    if (elTop < scrollTop) {
      container.scrollTop = elTop;
    } else if (elBottom > viewBottom) {
      container.scrollTop = elBottom - container.clientHeight;
    }
  }, [selectedNodeId]);

  const handleContextMenu = useCallback((e: React.MouseEvent, node: OpeningNode) => {
    if (!contextMenuActions) return;
    e.preventDefault();
    setContextMenu({ x: e.clientX, y: e.clientY, node });
  }, [contextMenuActions]);

  const handleCloseMenu = useCallback(() => {
    setContextMenu(null);
  }, []);

  // Check if the context menu node is a variation (not children[0] of its parent)
  const isVariation = useCallback((node: OpeningNode): boolean => {
    if (!tree) return false;
    const findParent = (root: OpeningNode, targetId: string): OpeningNode | null => {
      for (const child of root.children || []) {
        if (child.id === targetId) return root;
        const found = findParent(child, targetId);
        if (found) return found;
      }
      return null;
    };
    const parent = findParent(tree, node.id);
    if (!parent || !parent.children || parent.children.length <= 1) return false;
    return parent.children[0].id !== node.id;
  }, [tree]);

  const renderComment = useCallback<RenderComment>((node) => {
    if (node.id === editingCommentId) {
      return (
        <CommentEditor
          initial={node.notes || ''}
          placeholder={commentPlaceholder}
          onDone={(text) => {
            setEditingCommentId(null);
            if (text !== null) onCommentChange?.(node, text);
          }}
        />
      );
    }
    if (!node.notes) return null;
    return <CommentText text={node.notes} onClick={() => setEditingCommentId(node.id)} />;
  }, [editingCommentId, commentPlaceholder, onCommentChange]);

  const elements = useMemo(() => {
    if (!tree) return [];
    return renderTree(
      tree, selectedNodeId, onNodeSelect, selectedRef,
      contextMenuActions ? handleContextMenu : undefined,
      onCommentChange ? renderComment : undefined,
    );
  }, [tree, selectedNodeId, onNodeSelect, contextMenuActions, handleContextMenu, onCommentChange, renderComment]);

  const selectedMoveNode = useMemo(() => {
    if (!tree || !selectedNodeId || selectedNodeId === tree.id) return null;
    const find = (n: OpeningNode): OpeningNode | null => {
      if (n.id === selectedNodeId) return n;
      for (const c of n.children || []) { const f = find(c); if (f) return f; }
      return null;
    };
    return find(tree);
  }, [tree, selectedNodeId]);

  if (loading) {
    return (
      <Box sx={{ px: 1, py: 0.75, color: 'text.secondary' }}>
        <Typography sx={{ fontFamily: 'monospace', fontSize: '12px' }}>Loading…</Typography>
      </Box>
    );
  }

  if (!tree || elements.length === 0) {
    return (
      <Box sx={{ px: 1, py: 0.75, color: 'text.secondary', textAlign: 'center' }}>
        <Typography sx={{ fontFamily: 'monospace', fontSize: '12px', fontStyle: 'italic' }}>Make a move on the board to start.</Typography>
      </Box>
    );
  }

  const hasContent = elements.length > 0;
  const labels = contextMenuActions?.labels || {};

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column' }}>
      {/* Notation content */}
      <Box
        ref={containerRef}
        sx={{
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'baseline',
          gap: '1px 2px',
          px: 1,
          py: 0.5,
          overflow: 'auto',
          flex: 1,
          fontFamily: 'monospace',
          fontSize: '12px',
          lineHeight: 1.4,
        }}
      >
        {elements}
      </Box>

      {/* Comment button for the selected move (editable mode) */}
      {onCommentChange && selectedMoveNode && (
        <Box sx={{ display: 'flex', justifyContent: 'flex-end', px: 0.5, py: 0.25, borderTop: 1, borderColor: 'divider' }}>
          <Tooltip title={selectedMoveNode.notes ? labels.editComment || 'Edit comment' : labels.addComment || 'Add comment'} arrow placement="top">
            <IconButton
              size="small"
              aria-label={selectedMoveNode.notes ? labels.editComment || 'Edit comment' : labels.addComment || 'Add comment'}
              onClick={() => setEditingCommentId(selectedMoveNode.id)}
              sx={{ color: 'text.secondary', p: 0.4, '&:hover': { color: 'primary.main' } }}
            >
              {selectedMoveNode.notes ? <ModeComment sx={{ fontSize: 15 }} /> : <AddComment sx={{ fontSize: 15 }} />}
            </IconButton>
          </Tooltip>
        </Box>
      )}

      {/* Action bar */}
      {hasContent && (onDeleteLast || onDeleteAll) && (
        <Box sx={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'flex-end',
          gap: 0.25,
          px: 0.5,
          py: 0.25,
          borderTop: 1, borderColor: 'divider',
        }}>
          {onDeleteLast && (
            <Tooltip title="Delete last move" arrow placement="top">
              <IconButton
                size="small"
                onClick={onDeleteLast}
                disabled={!selectedNodeId}
                sx={{ color: 'text.secondary', p: 0.4, '&:hover': { color: 'error.light', bgcolor: 'rgba(229,115,115,0.08)' } }}
              >
                <Backspace sx={{ fontSize: 15 }} />
              </IconButton>
            </Tooltip>
          )}
          {onDeleteAll && (
            <Tooltip title="Delete all moves" arrow placement="top">
              <IconButton
                size="small"
                onClick={onDeleteAll}
                sx={{ color: 'text.secondary', p: 0.4, '&:hover': { color: 'error.light', bgcolor: 'rgba(229,115,115,0.08)' } }}
              >
                <DeleteSweep sx={{ fontSize: 15 }} />
              </IconButton>
            </Tooltip>
          )}
        </Box>
      )}

      {/* Context menu for move editing */}
      {contextMenuActions && (
        <Menu
          open={!!contextMenu}
          onClose={handleCloseMenu}
          anchorReference="anchorPosition"
          anchorPosition={contextMenu ? { top: contextMenu.y, left: contextMenu.x } : undefined}
          disableRestoreFocus
          slotProps={{
            transition: {
              onExited: () => {
                if (pendingCommentIdRef.current) setEditingCommentId(pendingCommentIdRef.current);
                pendingCommentIdRef.current = null;
              },
            },
            paper: {
              sx: {
                bgcolor: 'background.paper',
                minWidth: 180,
              },
            },
          }}
        >
          {onCommentChange && contextMenu && (
            <MenuItem
              onClick={() => {
                if (contextMenu) pendingCommentIdRef.current = contextMenu.node.id;
                handleCloseMenu();
              }}
              sx={{ fontSize: 13 }}
            >
              <ListItemIcon>
                {contextMenu.node.notes
                  ? <ModeComment fontSize="small" sx={{ color: 'primary.main' }} />
                  : <AddComment fontSize="small" sx={{ color: 'primary.main' }} />}
              </ListItemIcon>
              <ListItemText primaryTypographyProps={{ fontSize: 13 }}>
                {contextMenu.node.notes ? labels.editComment || 'Edit comment' : labels.addComment || 'Add comment'}
              </ListItemText>
            </MenuItem>
          )}
          {contextMenuActions.onDeleteFromHere && (
            <MenuItem
              onClick={() => {
                if (contextMenu) contextMenuActions.onDeleteFromHere!(contextMenu.node);
                handleCloseMenu();
              }}
              sx={{ fontSize: 13 }}
            >
              <ListItemIcon><Delete fontSize="small" sx={{ color: 'error.main' }} /></ListItemIcon>
              <ListItemText primaryTypographyProps={{ fontSize: 13 }}>{labels.deleteFromHere || 'Delete from here'}</ListItemText>
            </MenuItem>
          )}
          {contextMenuActions.onDeleteVariation && contextMenu && isVariation(contextMenu.node) && (
            <MenuItem
              onClick={() => {
                if (contextMenu) contextMenuActions.onDeleteVariation!(contextMenu.node);
                handleCloseMenu();
              }}
              sx={{ fontSize: 13 }}
            >
              <ListItemIcon><Delete fontSize="small" sx={{ color: 'warning.main' }} /></ListItemIcon>
              <ListItemText primaryTypographyProps={{ fontSize: 13 }}>{labels.deleteVariation || 'Delete variation'}</ListItemText>
            </MenuItem>
          )}
          {contextMenuActions.onPromoteVariation && contextMenu && isVariation(contextMenu.node) && (
            <MenuItem
              onClick={() => {
                if (contextMenu) contextMenuActions.onPromoteVariation!(contextMenu.node);
                handleCloseMenu();
              }}
              sx={{ fontSize: 13 }}
            >
              <ListItemIcon><TrendingUp fontSize="small" sx={{ color: 'info.main' }} /></ListItemIcon>
              <ListItemText primaryTypographyProps={{ fontSize: 13 }}>{labels.promoteVariation || 'Promote variation'}</ListItemText>
            </MenuItem>
          )}
          {contextMenuActions.onMakeMainLine && contextMenu && isVariation(contextMenu.node) && (
            <MenuItem
              onClick={() => {
                if (contextMenu) contextMenuActions.onMakeMainLine!(contextMenu.node);
                handleCloseMenu();
              }}
              sx={{ fontSize: 13 }}
            >
              <ListItemIcon><Star fontSize="small" sx={{ color: 'success.main' }} /></ListItemIcon>
              <ListItemText primaryTypographyProps={{ fontSize: 13 }}>{labels.makeMainLine || 'Make main line'}</ListItemText>
            </MenuItem>
          )}
        </Menu>
      )}
    </Box>
  );
}
