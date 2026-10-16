'use client';

import React, { useMemo, useRef, useEffect, useState, useCallback } from 'react';
import { Box, Typography, IconButton, Button, Tooltip, Menu, MenuItem, ListItemIcon, ListItemText, InputBase, Divider, Popover, useMediaQuery, useTheme } from '@mui/material';
import { Backspace, DeleteSweep, Delete, TrendingUp, Star, AddComment, ModeComment, MoreHoriz } from '@mui/icons-material';
import type { OpeningNode } from '@/hooks/useOpeningRepertoire';
import { MOVE_QUALITY_COLORS, getNag, suffixToNag } from '@/lib/nags';
import NagPalette, { type NagPaletteLabels } from './NagPalette';
import MoveActionSheet, { type MoveAction, type MoveSheetView } from './MoveActionSheet';

export interface MoveContextMenuActions {
  /** Removes the move and everything after it in its line. */
  onDeleteMove?: (node: OpeningNode) => void;
  onDeleteVariation?: (node: OpeningNode) => void;
  onPromoteVariation?: (node: OpeningNode) => void;
  onMakeMainLine?: (node: OpeningNode) => void;
  /** Enables inline comments: rendered after each move and editable in place. */
  onCommentChange?: (node: OpeningNode, text: string) => void;
  /** Enables move symbols: palette in the context menu + toolbar, `!`/`?` keys. */
  onNagToggle?: (node: OpeningNode, code: number) => void;
  labels?: NagPaletteLabels & {
    deleteMove?: string;
    deleteVariation?: string;
    promoteVariation?: string;
    makeMainLine?: string;
    addComment?: string;
    editComment?: string;
    commentPlaceholder?: string;
    moveSymbols?: string;
    /** Short action-bar labels shown at mobile width. */
    comment?: string;
    symbols?: string;
    more?: string;
    moreActions?: string;
    saveComment?: string;
    cancel?: string;
  };
}

/** `!`/`?` presses within this window combine into `!!`, `!?`, `?!`, `??`. */
const NAG_KEY_WINDOW_MS = 400;

/** Touch hold that opens the move action sheet; moving past the slop cancels it. */
const LONG_PRESS_MS = 450;
const LONG_PRESS_SLOP_PX = 10;

// Several notations can be mounted at once (responsive layouts); only the first
// listener acts on a given key press.
const handledNagKeys = new WeakSet<KeyboardEvent>();

function isTextTarget(target: EventTarget | null): boolean {
  return target instanceof HTMLInputElement
    || target instanceof HTMLTextAreaElement
    || (target instanceof HTMLElement && target.isContentEditable);
}

function findNode(root: OpeningNode, id: string): OpeningNode | null {
  if (root.id === id) return root;
  for (const c of root.children || []) { const f = findNode(c, id); if (f) return f; }
  return null;
}

function MoveNags({ nags }: { nags: number[] }) {
  const defs = nags.map(getNag).filter(d => d !== undefined);
  const quality = defs.find(d => d.group === 'move');
  const rest = defs.filter(d => d.group !== 'move');
  return (
    <>
      {quality && (
        <Box component="span" data-testid="move-nag-quality" sx={{ color: MOVE_QUALITY_COLORS[quality.code] ?? 'text.primary', fontWeight: 700 }}>
          {quality.symbol}
        </Box>
      )}
      {rest.length > 0 && (
        <Box component="span" data-testid="move-nag-extra" sx={{ color: 'text.disabled' }}>
          {`\u2009${rest.map(d => d.symbol).join('\u2009')}`}
        </Box>
      )}
    </>
  );
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

interface MoveHandlers {
  onContextMenu: (e: React.MouseEvent, node: OpeningNode) => void;
  onTouchStart: (e: React.TouchEvent, node: OpeningNode) => void;
  onTouchMove: (e: React.TouchEvent) => void;
  onTouchEnd: (e: React.TouchEvent) => void;
  onTouchCancel: () => void;
}

function MoveSpan({
  node,
  isSelected,
  selectedRef,
  onNodeSelect,
  handlers,
}: {
  node: OpeningNode;
  isSelected: boolean;
  selectedRef: React.RefObject<HTMLSpanElement | null>;
  onNodeSelect: (node: OpeningNode) => void;
  handlers?: MoveHandlers;
}) {
  return (
    <Typography
      ref={isSelected ? selectedRef : null}
      component="span"
      onClick={() => onNodeSelect(node)}
      onContextMenu={handlers ? (e) => handlers.onContextMenu(e, node) : undefined}
      onTouchStart={handlers ? (e) => handlers.onTouchStart(e, node) : undefined}
      onTouchMove={handlers?.onTouchMove}
      onTouchEnd={handlers?.onTouchEnd}
      onTouchCancel={handlers?.onTouchCancel}
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
        // Long-press opens the action sheet — keep iOS from selecting text or
        // showing its callout instead.
        ...(handlers && { '@media (pointer: coarse)': { WebkitTouchCallout: 'none', userSelect: 'none' } }),
        '&:hover': {
          bgcolor: isSelected ? 'action.selected' : 'action.hover',
          color: 'text.primary',
        },
      }}
    >
      {node.move_san}
      {node.nags?.length ? <MoveNags nags={node.nags} /> : null}
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
  handlers?: MoveHandlers,
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
      handlers={handlers}
    />
  );

  const comment = renderComment?.(node);
  if (comment) elements.push(<React.Fragment key={`c-${key}`}>{comment}</React.Fragment>);

  const children = node.children || [];
  if (children.length === 0) return elements;

  elements.push(
    // A comment breaks the move pair, so the next black move gets its number back
    ...renderNode(children[0], depth, !!comment, selectedNodeId, onNodeSelect, selectedRef, handlers, renderComment)
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
        {renderNode(alt, depth + 1, true, selectedNodeId, onNodeSelect, selectedRef, handlers, renderComment)}
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
  handlers?: MoveHandlers,
  renderComment?: RenderComment,
): React.ReactNode[] {
  const children = root.children || [];
  const rootComment = renderComment?.(root);
  if (children.length === 0) return rootComment ? [<React.Fragment key="c-root">{rootComment}</React.Fragment>] : [];

  const elements: React.ReactNode[] = [];
  if (rootComment) elements.push(<React.Fragment key="c-root">{rootComment}</React.Fragment>);

  elements.push(
    ...renderNode(children[0], 0, true, selectedNodeId, onNodeSelect, selectedRef, handlers, renderComment)
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
        {renderNode(alt, 1, true, selectedNodeId, onNodeSelect, selectedRef, handlers, renderComment)}
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

function moveLabel(node: OpeningNode): string {
  return `${node.move_number}${node.is_white_move ? '.' : '…'} ${node.move_san}`;
}

function ActionBarButton({ label, showLabel, disabled, onClick, children }: {
  label: string;
  showLabel: boolean;
  disabled: boolean;
  onClick: (e: React.MouseEvent<HTMLElement>) => void;
  children: React.ReactNode;
}) {
  return (
    <Tooltip title={showLabel ? '' : label} arrow placement="top" describeChild>
      <span>
        <Button
          size="small"
          aria-label={label}
          disabled={disabled}
          onClick={onClick}
          sx={{
            minWidth: 40,
            minHeight: 40,
            px: showLabel ? 1.25 : 0.5,
            gap: 0.75,
            color: 'text.secondary',
            textTransform: 'none',
            fontSize: 13,
            fontWeight: 600,
            '&:hover': { color: 'primary.main' },
          }}
        >
          {children}
          {showLabel && <span>{label}</span>}
        </Button>
      </span>
    </Tooltip>
  );
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
  const onNagToggle = contextMenuActions?.onNagToggle;
  const [nagAnchor, setNagAnchor] = useState<HTMLElement | null>(null);
  const commentPlaceholder = contextMenuActions?.labels?.commentPlaceholder;
  // Phones/tablets: the right-click menu is unreachable, so the move actions and
  // comment editor live in a bottom sheet instead.
  const theme = useTheme();
  const isNarrow = useMediaQuery(theme.breakpoints.down('md'));
  const isTouch = useMediaQuery('(pointer: coarse)');
  const isMobile = isNarrow || isTouch;
  const [sheet, setSheet] = useState<{ nodeId: string; view: MoveSheetView } | null>(null);
  const pressRef = useRef<{ node: OpeningNode; x: number; y: number; timer: ReturnType<typeof setTimeout>; fired: boolean } | null>(null);

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

  const openSheet = useCallback((node: OpeningNode, view: MoveSheetView = 'actions') => {
    if (node.id !== selectedNodeId) onNodeSelect(node);
    setSheet({ nodeId: node.id, view });
  }, [selectedNodeId, onNodeSelect]);

  const closeSheet = useCallback(() => setSheet(null), []);

  // ─── Long-press (touch) ───
  const endPress = useCallback(() => {
    const press = pressRef.current;
    if (press) clearTimeout(press.timer);
    pressRef.current = null;
    return press;
  }, []);

  useEffect(() => () => { endPress(); }, [endPress]);

  const handleTouchStart = useCallback((e: React.TouchEvent, node: OpeningNode) => {
    endPress();
    const touch = e.touches[0];
    const press = {
      node,
      x: touch?.clientX ?? 0,
      y: touch?.clientY ?? 0,
      fired: false,
      timer: setTimeout(() => {
        press.fired = true;
        navigator.vibrate?.(10);
      }, LONG_PRESS_MS),
    };
    pressRef.current = press;
  }, [endPress]);

  const handleTouchMove = useCallback((e: React.TouchEvent) => {
    const press = pressRef.current;
    const touch = e.touches[0];
    if (press && touch && Math.hypot(touch.clientX - press.x, touch.clientY - press.y) > LONG_PRESS_SLOP_PX) endPress();
  }, [endPress]);

  const handleTouchEnd = useCallback((e: React.TouchEvent) => {
    const press = endPress();
    if (!press?.fired) return;
    // Swallow the tap that would otherwise follow the hold.
    e.preventDefault();
    openSheet(press.node);
  }, [endPress, openSheet]);

  const handleContextMenu = useCallback((e: React.MouseEvent, node: OpeningNode) => {
    if (!contextMenuActions) return;
    e.preventDefault();
    // Android fires contextmenu for a touch hold — treat it as the long-press.
    const press = endPress();
    if (press) {
      openSheet(press.node);
      return;
    }
    setContextMenu({ x: e.clientX, y: e.clientY, node });
  }, [contextMenuActions, endPress, openSheet]);

  const handlers = useMemo<MoveHandlers>(() => ({
    onContextMenu: handleContextMenu,
    onTouchStart: handleTouchStart,
    onTouchMove: handleTouchMove,
    onTouchEnd: handleTouchEnd,
    onTouchCancel: endPress,
  }), [handleContextMenu, handleTouchStart, handleTouchMove, handleTouchEnd, endPress]);

  // On mobile a second tap on the current move opens its action sheet.
  const handleMoveClick = useCallback((node: OpeningNode) => {
    if (isMobile && contextMenuActions && node.id === selectedNodeId) openSheet(node);
    else onNodeSelect(node);
  }, [isMobile, contextMenuActions, selectedNodeId, openSheet, onNodeSelect]);

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

  const editComment = useCallback((node: OpeningNode) => {
    if (isMobile) openSheet(node, 'comment');
    else setEditingCommentId(node.id);
  }, [isMobile, openSheet]);

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
    return <CommentText text={node.notes} onClick={() => editComment(node)} />;
  }, [editingCommentId, commentPlaceholder, onCommentChange, editComment]);

  const elements = useMemo(() => {
    if (!tree) return [];
    return renderTree(
      tree, selectedNodeId, handleMoveClick, selectedRef,
      contextMenuActions ? handlers : undefined,
      onCommentChange ? renderComment : undefined,
    );
  }, [tree, selectedNodeId, handleMoveClick, contextMenuActions, handlers, onCommentChange, renderComment]);

  const selectedMoveNode = useMemo(() => {
    if (!tree || !selectedNodeId || selectedNodeId === tree.id) return null;
    const find = (n: OpeningNode): OpeningNode | null => {
      if (n.id === selectedNodeId) return n;
      for (const c of n.children || []) { const f = find(c); if (f) return f; }
      return null;
    };
    return find(tree);
  }, [tree, selectedNodeId]);

  // Typed `!`/`?` sequences set the selected move's quality symbol.
  const nagKeyTargetRef = useRef({ node: selectedMoveNode, onNagToggle });
  useEffect(() => {
    nagKeyTargetRef.current = { node: selectedMoveNode, onNagToggle };
  });
  const nagKeysEnabled = !!onNagToggle;
  useEffect(() => {
    if (!nagKeysEnabled) return;
    let buffer = '';
    let timer: ReturnType<typeof setTimeout> | null = null;
    const flush = () => {
      if (timer) clearTimeout(timer);
      timer = null;
      const code = suffixToNag(buffer);
      buffer = '';
      const { node, onNagToggle: toggle } = nagKeyTargetRef.current;
      if (code !== null && node && toggle) toggle(node, code);
    };
    const handleKey = (e: KeyboardEvent) => {
      if ((e.key !== '!' && e.key !== '?') || e.ctrlKey || e.metaKey || e.altKey) return;
      if (isTextTarget(e.target) || handledNagKeys.has(e) || !nagKeyTargetRef.current.node) return;
      handledNagKeys.add(e);
      e.preventDefault();
      buffer += e.key;
      if (buffer.length >= 2) flush();
      else timer = setTimeout(flush, NAG_KEY_WINDOW_MS);
    };
    window.addEventListener('keydown', handleKey);
    return () => {
      window.removeEventListener('keydown', handleKey);
      if (timer) clearTimeout(timer);
    };
  }, [nagKeysEnabled]);

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
  const commentLabel = (node: OpeningNode | null) =>
    node?.notes ? labels.editComment || 'Edit comment' : labels.addComment || 'Add comment';
  const symbolsLabel = labels.moveSymbols || 'Move symbols';

  // One action list for both surfaces: the desktop context menu and the mobile
  // sheet. Order is the sheet's; the menu pulls "Delete move" to the top and
  // shows the symbol palette inline instead of the "Symbols" row.
  const moveActions = (node: OpeningNode): MoveAction[] => {
    if (!contextMenuActions) return [];
    const variation = isVariation(node);
    const actions: MoveAction[] = [];
    if (onCommentChange) {
      actions.push({
        key: 'comment',
        label: commentLabel(node),
        icon: node.notes ? <ModeComment fontSize="small" /> : <AddComment fontSize="small" />,
        color: 'primary.main',
      });
    }
    if (onNagToggle) {
      actions.push({ key: 'symbols', label: symbolsLabel, icon: <Box component="span" sx={{ fontWeight: 700, fontSize: 14 }}>!?</Box> });
    }
    if (contextMenuActions.onMakeMainLine && variation) {
      actions.push({ key: 'makeMainLine', label: labels.makeMainLine || 'Make main line', icon: <Star fontSize="small" />, color: 'success.main' });
    }
    if (contextMenuActions.onPromoteVariation && variation) {
      actions.push({ key: 'promoteVariation', label: labels.promoteVariation || 'Promote variation', icon: <TrendingUp fontSize="small" />, color: 'info.main' });
    }
    if (contextMenuActions.onDeleteVariation && variation) {
      actions.push({ key: 'deleteVariation', label: labels.deleteVariation || 'Delete variation', icon: <Delete fontSize="small" />, color: 'warning.main' });
    }
    if (contextMenuActions.onDeleteMove) {
      actions.push({ key: 'deleteMove', label: labels.deleteMove || 'Delete move', icon: <Delete fontSize="small" />, color: 'error.main' });
    }
    return actions;
  };

  const runAction = (key: string, node: OpeningNode, surface: 'menu' | 'sheet') => {
    if (!contextMenuActions) return;
    if (key === 'comment') {
      if (surface === 'sheet') setSheet({ nodeId: node.id, view: 'comment' });
      else pendingCommentIdRef.current = node.id;
      return;
    }
    if (key === 'symbols') {
      setSheet({ nodeId: node.id, view: 'nags' });
      return;
    }
    setSheet(null);
    if (key === 'makeMainLine') contextMenuActions.onMakeMainLine?.(node);
    else if (key === 'promoteVariation') contextMenuActions.onPromoteVariation?.(node);
    else if (key === 'deleteVariation') contextMenuActions.onDeleteVariation?.(node);
    else if (key === 'deleteMove') contextMenuActions.onDeleteMove?.(node);
  };

  const menuNode = contextMenu ? findNode(tree, contextMenu.node.id) ?? contextMenu.node : null;
  const menuActions = menuNode ? moveActions(menuNode).filter(a => a.key !== 'symbols') : [];
  const menuDelete = menuActions.find(a => a.key === 'deleteMove');
  const menuRest = menuActions.filter(a => a.key !== 'deleteMove');
  const renderMenuItem = (action: MoveAction) => (
    <MenuItem
      key={action.key}
      onClick={() => {
        handleCloseMenu();
        if (menuNode) runAction(action.key, menuNode, 'menu');
      }}
      sx={{ fontSize: 13 }}
    >
      <ListItemIcon sx={{ color: action.color }}>{action.icon}</ListItemIcon>
      <ListItemText primaryTypographyProps={{ fontSize: 13 }}>{action.label}</ListItemText>
    </MenuItem>
  );

  const sheetNode = sheet ? findNode(tree, sheet.nodeId) : null;

  const openMore = (e: React.MouseEvent<HTMLElement>) => {
    if (!selectedMoveNode) return;
    if (isMobile) {
      openSheet(selectedMoveNode);
      return;
    }
    const rect = e.currentTarget.getBoundingClientRect();
    setContextMenu({ x: rect.left, y: rect.bottom, node: selectedMoveNode });
  };

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0 }}>
      {/* Notation content — scrolls on its own so the action bar below stays visible */}
      <Box
        ref={containerRef}
        data-testid="move-notation-scroll"
        onScroll={endPress}
        sx={{
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'baseline',
          gap: '1px 2px',
          px: 1,
          py: 0.5,
          overflow: 'auto',
          flex: 1,
          minHeight: 0,
          maxHeight: { xs: 150, lg: 'none' },
          fontFamily: 'monospace',
          fontSize: '12px',
          lineHeight: 1.4,
        }}
      >
        {elements}
      </Box>

      {/* Move action bar for the selected move (editable mode) */}
      {contextMenuActions && (
        <Box
          data-testid="move-action-bar"
          sx={{ display: 'flex', justifyContent: 'flex-end', gap: 0.5, px: 0.5, py: 0.25, borderTop: 1, borderColor: 'divider' }}
        >
          {onCommentChange && (
            <ActionBarButton
              label={isMobile ? labels.comment || 'Comment' : commentLabel(selectedMoveNode)}
              showLabel={isMobile}
              disabled={!selectedMoveNode}
              onClick={() => selectedMoveNode && editComment(selectedMoveNode)}
            >
              {selectedMoveNode?.notes ? <ModeComment sx={{ fontSize: 18 }} /> : <AddComment sx={{ fontSize: 18 }} />}
            </ActionBarButton>
          )}
          {onNagToggle && (
            <ActionBarButton
              label={isMobile ? labels.symbols || 'Symbols' : symbolsLabel}
              showLabel={isMobile}
              disabled={!selectedMoveNode}
              onClick={(e) => {
                if (!selectedMoveNode) return;
                if (isMobile) openSheet(selectedMoveNode, 'nags');
                else setNagAnchor(e.currentTarget);
              }}
            >
              <Box component="span" sx={{ fontSize: 14, fontWeight: 700, lineHeight: '18px' }}>!?</Box>
            </ActionBarButton>
          )}
          <ActionBarButton
            label={isMobile ? labels.more || 'More' : labels.moreActions || 'More actions'}
            showLabel={isMobile}
            disabled={!selectedMoveNode}
            onClick={openMore}
          >
            <MoreHoriz sx={{ fontSize: 18 }} />
          </ActionBarButton>
        </Box>
      )}

      {onNagToggle && (
        <Popover
          open={!!nagAnchor && !!selectedMoveNode}
          anchorEl={nagAnchor}
          onClose={() => setNagAnchor(null)}
          anchorOrigin={{ vertical: 'top', horizontal: 'right' }}
          transformOrigin={{ vertical: 'bottom', horizontal: 'right' }}
        >
          {selectedMoveNode && (
            <NagPalette
              nags={selectedMoveNode.nags}
              onToggle={(code) => onNagToggle(selectedMoveNode, code)}
              labels={labels}
            />
          )}
        </Popover>
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

      {/* Context menu for move editing (desktop) */}
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
          {menuDelete && renderMenuItem(menuDelete)}
          {menuDelete && (onNagToggle || menuRest.length > 0) && <Divider sx={{ my: 0.5 }} />}
          {onNagToggle && menuNode && (
            <NagPalette
              nags={menuNode.nags}
              onToggle={(code) => onNagToggle(menuNode, code)}
              labels={labels}
            />
          )}
          {onNagToggle && menuNode && menuRest.length > 0 && <Divider sx={{ my: 0.5 }} />}
          {menuRest.map(renderMenuItem)}
        </Menu>
      )}

      {/* Action sheet (mobile) */}
      {contextMenuActions && (
        <MoveActionSheet
          open={!!sheetNode}
          view={sheet?.view ?? 'actions'}
          title={sheetNode ? moveLabel(sheetNode) : ''}
          actions={sheetNode ? moveActions(sheetNode) : []}
          onAction={(key) => sheetNode && runAction(key, sheetNode, 'sheet')}
          onClose={closeSheet}
          nags={sheetNode?.nags}
          onNagToggle={onNagToggle && sheetNode ? (code) => onNagToggle(sheetNode, code) : undefined}
          nagLabels={labels}
          comment={sheetNode?.notes || ''}
          onCommentSave={(text) => {
            if (sheetNode) onCommentChange?.(sheetNode, text);
            closeSheet();
          }}
          labels={{
            commentPlaceholder,
            save: labels.saveComment || 'Save',
            cancel: labels.cancel || 'Cancel',
          }}
        />
      )}
    </Box>
  );
}
