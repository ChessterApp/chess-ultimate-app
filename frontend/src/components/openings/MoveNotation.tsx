'use client';

import React, { useMemo, useRef, useEffect } from 'react';
import { Box, Typography } from '@mui/material';
import type { OpeningNode } from '@/hooks/useOpeningRepertoire';

interface MoveNotationProps {
  tree: OpeningNode | null;
  selectedNodeId: string | null;
  onNodeSelect: (node: OpeningNode) => void;
  loading: boolean;
}

/**
 * Renders a move span — clickable, highlighted if selected.
 */
function MoveSpan({
  node,
  isSelected,
  selectedRef,
  onNodeSelect,
}: {
  node: OpeningNode;
  isSelected: boolean;
  selectedRef: React.RefObject<HTMLSpanElement | null>;
  onNodeSelect: (node: OpeningNode) => void;
}) {
  return (
    <Typography
      ref={isSelected ? selectedRef : null}
      component="span"
      onClick={() => onNodeSelect(node)}
      sx={{
        color: isSelected ? '#fff' : '#ccc',
        bgcolor: isSelected ? '#3692e7' : 'transparent',
        fontSize: 'inherit',
        fontFamily: 'inherit',
        fontWeight: isSelected ? 700 : 400,
        px: '4px',
        py: '1px',
        borderRadius: '3px',
        cursor: 'pointer',
        transition: 'background-color 0.1s',
        '&:hover': {
          bgcolor: isSelected ? '#3692e7' : 'rgba(255,255,255,0.08)',
        },
      }}
    >
      {node.move_san}
    </Typography>
  );
}

/**
 * Renders a move number span.
 */
function MoveNumber({ text }: { text: string }) {
  return (
    <Typography
      component="span"
      sx={{
        color: '#999',
        fontSize: 'inherit',
        fontFamily: 'inherit',
        fontWeight: 500,
        mr: '2px',
        userSelect: 'none',
      }}
    >
      {text}
    </Typography>
  );
}

/**
 * Recursively renders a node and its descendants.
 * Main line continues inline; side lines get their own indented line.
 *
 * @param node       The current node to render
 * @param depth      Nesting depth (for indentation of variations)
 * @param isFirst    Whether this is the first node rendered in a variation (need black move number)
 * @param selectedNodeId  Currently selected node id
 * @param onNodeSelect    Selection callback
 * @param selectedRef     Ref for auto-scroll
 */
function renderNode(
  node: OpeningNode,
  depth: number,
  isFirst: boolean,
  selectedNodeId: string | null,
  onNodeSelect: (node: OpeningNode) => void,
  selectedRef: React.RefObject<HTMLSpanElement | null>,
): React.ReactNode[] {
  const elements: React.ReactNode[] = [];
  const key = node.id;
  const isSelected = node.id === selectedNodeId;

  // Move number
  if (node.is_white_move) {
    elements.push(<MoveNumber key={`mn-${key}`} text={`${node.move_number}.`} />);
  } else if (isFirst) {
    // Black move at start of a variation — show "N..."
    elements.push(<MoveNumber key={`mn-${key}`} text={`${node.move_number}...`} />);
  }

  // The move itself
  elements.push(
    <MoveSpan
      key={`m-${key}`}
      node={node}
      isSelected={isSelected}
      selectedRef={selectedRef}
      onNodeSelect={onNodeSelect}
    />
  );

  const children = node.children || [];
  if (children.length === 0) return elements;

  // Main line (first child) continues inline
  elements.push(
    ...renderNode(children[0], depth, false, selectedNodeId, onNodeSelect, selectedRef)
  );

  // Side lines as indented variations
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
          gap: '1px 3px',
          width: '100%',
          pl: `${(depth + 1) * 12}px`,
          color: '#b0b0b0',
          fontSize: 'inherit',
          fontFamily: 'inherit',
        }}
      >
        <Typography
          component="span"
          sx={{ color: '#777', fontSize: 'inherit', fontFamily: 'inherit', userSelect: 'none' }}
        >
          (
        </Typography>
        {renderNode(alt, depth + 1, true, selectedNodeId, onNodeSelect, selectedRef)}
        <Typography
          component="span"
          sx={{ color: '#777', fontSize: 'inherit', fontFamily: 'inherit', userSelect: 'none' }}
        >
          )
        </Typography>
      </Box>
    );
  }

  return elements;
}

/**
 * Renders the entire tree starting from root.
 * Root node (move_san === null) is skipped; its children are rendered.
 */
function renderTree(
  root: OpeningNode,
  selectedNodeId: string | null,
  onNodeSelect: (node: OpeningNode) => void,
  selectedRef: React.RefObject<HTMLSpanElement | null>,
): React.ReactNode[] {
  const children = root.children || [];
  if (children.length === 0) return [];

  const elements: React.ReactNode[] = [];

  // First child is the main line
  elements.push(
    ...renderNode(children[0], 0, true, selectedNodeId, onNodeSelect, selectedRef)
  );

  // Additional root children are alternative first moves (branches)
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
          gap: '1px 3px',
          width: '100%',
          pl: '12px',
          color: '#b0b0b0',
          fontSize: 'inherit',
          fontFamily: 'inherit',
        }}
      >
        <Typography
          component="span"
          sx={{ color: '#777', fontSize: 'inherit', fontFamily: 'inherit', userSelect: 'none' }}
        >
          (
        </Typography>
        {renderNode(alt, 1, true, selectedNodeId, onNodeSelect, selectedRef)}
        <Typography
          component="span"
          sx={{ color: '#777', fontSize: 'inherit', fontFamily: 'inherit', userSelect: 'none' }}
        >
          )
        </Typography>
      </Box>
    );
  }

  return elements;
}

export default function MoveNotation({ tree, selectedNodeId, onNodeSelect, loading }: MoveNotationProps) {
  const selectedRef = useRef<HTMLSpanElement>(null);

  // Auto-scroll to selected move
  useEffect(() => {
    if (selectedRef.current) {
      selectedRef.current.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }
  }, [selectedNodeId]);

  const elements = useMemo(() => {
    if (!tree) return [];
    return renderTree(tree, selectedNodeId, onNodeSelect, selectedRef);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tree, selectedNodeId, onNodeSelect]);

  if (loading) {
    return (
      <Box sx={{ p: 1.5, color: '#888' }}>
        <Typography variant="caption">Loading...</Typography>
      </Box>
    );
  }

  if (!tree || elements.length === 0) {
    return (
      <Box sx={{ p: 1.5, color: '#666', textAlign: 'center' }}>
        <Typography variant="caption">Make a move on the board to start.</Typography>
      </Box>
    );
  }

  return (
    <Box
      sx={{
        display: 'flex',
        flexWrap: 'wrap',
        alignItems: 'baseline',
        gap: '1px 3px',
        p: 1,
        bgcolor: '#262422',
        overflow: 'auto',
        fontSize: 14,
        fontFamily: '"Noto Sans", "Roboto", sans-serif',
        lineHeight: 1.6,
      }}
    >
      {elements}
    </Box>
  );
}
