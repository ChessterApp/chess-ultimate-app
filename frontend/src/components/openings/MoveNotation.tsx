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
        color: isSelected ? '#fff' : '#d4d4d4',
        bgcolor: isSelected ? '#5c6bc0' : 'transparent',
        fontSize: 'inherit',
        fontFamily: 'inherit',
        fontWeight: isSelected ? 600 : 400,
        px: '3px',
        py: '0px',
        borderRadius: '2px',
        cursor: 'pointer',
        transition: 'all 0.12s ease',
        '&:hover': {
          bgcolor: isSelected ? '#5c6bc0' : 'rgba(255,255,255,0.06)',
          color: '#fff',
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
        color: '#666',
        fontSize: 'inherit',
        fontFamily: 'inherit',
        fontWeight: 600,
        mr: '1px',
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
    />
  );

  const children = node.children || [];
  if (children.length === 0) return elements;

  elements.push(
    ...renderNode(children[0], depth, false, selectedNodeId, onNodeSelect, selectedRef)
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
          fontSize: 'inherit',
          fontFamily: 'inherit',
        }}
      >
        <Typography
          component="span"
          sx={{ color: '#555', fontSize: 'inherit', fontFamily: 'inherit', userSelect: 'none' }}
        >
          (
        </Typography>
        {renderNode(alt, depth + 1, true, selectedNodeId, onNodeSelect, selectedRef)}
        <Typography
          component="span"
          sx={{ color: '#555', fontSize: 'inherit', fontFamily: 'inherit', userSelect: 'none' }}
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
): React.ReactNode[] {
  const children = root.children || [];
  if (children.length === 0) return [];

  const elements: React.ReactNode[] = [];

  elements.push(
    ...renderNode(children[0], 0, true, selectedNodeId, onNodeSelect, selectedRef)
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
          fontSize: 'inherit',
          fontFamily: 'inherit',
        }}
      >
        <Typography
          component="span"
          sx={{ color: '#555', fontSize: 'inherit', fontFamily: 'inherit', userSelect: 'none' }}
        >
          (
        </Typography>
        {renderNode(alt, 1, true, selectedNodeId, onNodeSelect, selectedRef)}
        <Typography
          component="span"
          sx={{ color: '#555', fontSize: 'inherit', fontFamily: 'inherit', userSelect: 'none' }}
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
      <Box sx={{ px: 1.5, py: 1, color: '#666' }}>
        <Typography sx={{ fontSize: 12 }}>Loading…</Typography>
      </Box>
    );
  }

  if (!tree || elements.length === 0) {
    return (
      <Box sx={{ px: 1.5, py: 1, color: '#555', textAlign: 'center' }}>
        <Typography sx={{ fontSize: 12 }}>Make a move on the board to start.</Typography>
      </Box>
    );
  }

  return (
    <Box
      sx={{
        display: 'flex',
        flexWrap: 'wrap',
        alignItems: 'baseline',
        gap: '0px 2px',
        px: 1.5,
        py: 0.75,
        bgcolor: '#1e1e1e',
        borderTop: '1px solid rgba(255,255,255,0.06)',
        overflow: 'auto',
        fontSize: { xs: 13, lg: 13 },
        fontFamily: '"Roboto Mono", "SF Mono", "Fira Code", monospace',
        lineHeight: 1.7,
        letterSpacing: '-0.01em',
        '&::-webkit-scrollbar': { width: 4 },
        '&::-webkit-scrollbar-thumb': { bgcolor: 'rgba(255,255,255,0.12)', borderRadius: 2 },
      }}
    >
      {elements}
    </Box>
  );
}
