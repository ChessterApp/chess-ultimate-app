'use client';

import React, { useState, useMemo, useEffect, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import {
  Box, Typography, IconButton, Chip, Tooltip, Button,
} from '@mui/material';
import {
  ExpandMore, ChevronRight, Star, Schedule, CheckCircle,
  UnfoldMore, UnfoldLess,
} from '@mui/icons-material';
import type { OpeningNode } from '@/hooks/useOpeningRepertoire';

interface OpeningTreeProps {
  tree: OpeningNode | null;
  selectedNodeId: string | null;
  onNodeSelect: (node: OpeningNode) => void;
  onNodeDelete?: (nodeId: string) => void;
  loading: boolean;
}

// Count total descendants
function countDescendants(node: OpeningNode): number {
  let count = 0;
  for (const child of node.children || []) {
    count += 1 + countDescendants(child);
  }
  return count;
}

// Collect all node IDs
function collectIds(node: OpeningNode): string[] {
  const ids = [node.id];
  for (const child of node.children || []) {
    ids.push(...collectIds(child));
  }
  return ids;
}

// Find path from root to target
function findPath(node: OpeningNode, targetId: string): string[] | null {
  if (node.id === targetId) return [node.id];
  for (const child of node.children || []) {
    const sub = findPath(child, targetId);
    if (sub) return [node.id, ...sub];
  }
  return null;
}

const TreeNodeItem = React.memo(function TreeNodeItem({
  node, depth, selectedId, onSelect, expandedIds, onToggle,
}: {
  node: OpeningNode;
  depth: number;
  selectedId: string | null;
  onSelect: (node: OpeningNode) => void;
  expandedIds: Set<string>;
  onToggle: (id: string) => void;
}) {
  const t = useTranslations('debut');
  const hasChildren = (node.children?.length || 0) > 0;
  const isExpanded = expandedIds.has(node.id);
  const isSelected = node.id === selectedId;
  const isRoot = node.move_san === null;

  // Status indicators
  const isCritical = node.is_critical;
  const needsReview = node.next_review_at ? new Date(node.next_review_at) <= new Date() : false;
  const isMastered = node.times_trained >= 5 &&
    node.times_correct / Math.max(node.times_trained, 1) >= 0.8;

  // Move display
  let moveText = '';
  if (!isRoot && node.move_san) {
    if (node.is_white_move) {
      moveText = `${node.move_number}. ${node.move_san}`;
    } else {
      moveText = `${node.move_number}... ${node.move_san}`;
    }
  }

  const descendantCount = !isExpanded && hasChildren ? countDescendants(node) : 0;

  return (
    <Box>
      <Box
        onClick={() => onSelect(node)}
        sx={{
          display: 'flex', alignItems: 'center', gap: 0.5,
          pl: depth * 2, pr: 1, py: 0.3, cursor: 'pointer',
          bgcolor: isSelected ? 'rgba(128, 128, 255, 0.15)' : 'transparent',
          '&:hover': { bgcolor: isSelected ? 'rgba(128, 128, 255, 0.2)' : 'rgba(255,255,255,0.04)' },
          borderLeft: isSelected ? '2px solid #7c7cff' : '2px solid transparent',
          minHeight: 28,
        }}
      >
        {/* Expand toggle */}
        {hasChildren ? (
          <IconButton
            size="small"
            onClick={(e) => { e.stopPropagation(); onToggle(node.id); }}
            sx={{ p: 0, color: '#888', width: 20, height: 20 }}
          >
            {isExpanded ? <ExpandMore sx={{ fontSize: 16 }} /> : <ChevronRight sx={{ fontSize: 16 }} />}
          </IconButton>
        ) : (
          <Box sx={{ width: 20 }} />
        )}

        {/* Status indicators */}
        {isCritical && <Star sx={{ fontSize: 14, color: '#ffd700' }} />}
        {needsReview && !isMastered && <Schedule sx={{ fontSize: 14, color: '#f44336' }} />}
        {isMastered && <CheckCircle sx={{ fontSize: 14, color: '#4caf50' }} />}

        {/* Move text */}
        <Typography
          component="span"
          sx={{
            fontSize: 13, fontFamily: 'monospace', color: '#e0e0e0',
            fontWeight: isSelected ? 600 : 400,
          }}
        >
          {isRoot ? t('start') : moveText}
        </Typography>

        {/* ECO chip */}
        {node.eco_code && (
          <Chip
            label={node.eco_code}
            size="small"
            sx={{ height: 16, fontSize: 10, bgcolor: '#444', color: '#aaa', ml: 0.5 }}
          />
        )}

        {/* Opening name */}
        {node.opening_name && (
          <Typography
            component="span"
            sx={{ fontSize: 11, color: '#888', ml: 0.5, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
          >
            {node.opening_name}
          </Typography>
        )}

        {/* Descendant count when collapsed */}
        {descendantCount > 0 && (
          <Chip
            label={`+${descendantCount}`}
            size="small"
            sx={{ height: 16, fontSize: 10, bgcolor: '#333', color: '#777', ml: 'auto' }}
          />
        )}
      </Box>

      {/* Children */}
      {isExpanded && hasChildren && (
        <Box>
          {node.children!.map(child => (
            <TreeNodeItem
              key={child.id}
              node={child}
              depth={depth + 1}
              selectedId={selectedId}
              onSelect={onSelect}
              expandedIds={expandedIds}
              onToggle={onToggle}
            />
          ))}
        </Box>
      )}
    </Box>
  );
});

export default function OpeningTree({
  tree, selectedNodeId, onNodeSelect, loading,
}: OpeningTreeProps) {
  const t = useTranslations('debut');
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());

  // Auto-expand path to selected node
  useEffect(() => {
    if (tree && selectedNodeId) {
      const path = findPath(tree, selectedNodeId);
      if (path) {
        setExpandedIds(prev => {
          const next = new Set(prev);
          path.forEach(id => next.add(id));
          return next;
        });
      }
    }
  }, [tree, selectedNodeId]);

  // Auto-expand root on first load
  useEffect(() => {
    if (tree) {
      setExpandedIds(prev => {
        const next = new Set(prev);
        next.add(tree.id);
        return next;
      });
    }
  }, [tree?.id]);

  const onToggle = useCallback((id: string) => {
    setExpandedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const expandAll = useCallback(() => {
    if (!tree) return;
    setExpandedIds(new Set(collectIds(tree)));
  }, [tree]);

  const collapseAll = useCallback(() => {
    if (!tree) return;
    setExpandedIds(new Set([tree.id]));
  }, [tree]);

  if (loading) {
    return (
      <Box sx={{ p: 2, color: '#888' }}>
        <Typography variant="body2">Loading tree...</Typography>
      </Box>
    );
  }

  if (!tree) {
    return (
      <Box sx={{ p: 2, color: '#888' }}>
        <Typography variant="body2">Select a repertoire to view the opening tree.</Typography>
      </Box>
    );
  }

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0 }}>
      {/* Toolbar */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, px: 1, py: 0.5, borderBottom: '1px solid #333' }}>
        <Button size="small" startIcon={<UnfoldMore sx={{ fontSize: 14 }} />} onClick={expandAll}
          sx={{ color: '#aaa', fontSize: 11, textTransform: 'none', minWidth: 0, px: 1 }}>
          {t('expand')}
        </Button>
        <Button size="small" startIcon={<UnfoldLess sx={{ fontSize: 14 }} />} onClick={collapseAll}
          sx={{ color: '#aaa', fontSize: 11, textTransform: 'none', minWidth: 0, px: 1 }}>
          {t('collapse')}
        </Button>
        <Box sx={{ ml: 'auto', display: 'flex', gap: 1, alignItems: 'center' }}>
          <Tooltip title="Critical position"><Star sx={{ fontSize: 12, color: '#ffd700' }} /></Tooltip>
          <Tooltip title="Needs review"><Schedule sx={{ fontSize: 12, color: '#f44336' }} /></Tooltip>
          <Tooltip title="Mastered"><CheckCircle sx={{ fontSize: 12, color: '#4caf50' }} /></Tooltip>
        </Box>
      </Box>

      {/* Tree */}
      <Box sx={{ flex: 1, overflow: 'auto', py: 0.5 }}>
        {(tree.children?.length || 0) === 0 && !tree.move_san ? (
          <Box sx={{ p: 2, color: '#777', textAlign: 'center' }}>
            <Typography variant="body2">No moves yet. Make a move on the board to start building your repertoire.</Typography>
          </Box>
        ) : (
          <TreeNodeItem
            node={tree}
            depth={0}
            selectedId={selectedNodeId}
            onSelect={onNodeSelect}
            expandedIds={expandedIds}
            onToggle={onToggle}
          />
        )}
      </Box>
    </Box>
  );
}
