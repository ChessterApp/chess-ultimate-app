'use client';

import { useState, type MouseEvent, type ReactNode } from 'react';
import { useTranslations } from 'next-intl';
import { Box, IconButton, Popover, ToggleButton, ToggleButtonGroup, Typography } from '@mui/material';
import SettingsIcon from '@mui/icons-material/Settings';
import {
  ENGINE_DEPTH_OPTIONS,
  ENGINE_LINES_OPTIONS,
  useEngineDisplaySettings,
} from '@/hooks/useEngineDisplaySettings';

interface EngineSettingsMenuProps {
  /** Rendered below the depth/lines groups (e.g. an engine-version picker). */
  extra?: ReactNode;
}

function OptionGroup({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: readonly number[];
  value: number;
  onChange: (value: number) => void;
}) {
  return (
    <Box>
      <Typography variant="caption" color="text.secondary" component="div" sx={{ mb: 0.5 }}>
        {label}
      </Typography>
      <ToggleButtonGroup
        exclusive
        size="small"
        value={value}
        aria-label={label}
        onChange={(_, next: number | null) => next !== null && onChange(next)}
      >
        {options.map((option) => (
          <ToggleButton key={option} value={option} sx={{ minWidth: 36, py: 0.25 }}>
            {option}
          </ToggleButton>
        ))}
      </ToggleButtonGroup>
    </Box>
  );
}

/** Gear button + popover for the shared engine depth / line-count settings. */
export default function EngineSettingsMenu({ extra }: EngineSettingsMenuProps) {
  const t = useTranslations('engine');
  const { depth, lines, setDepth, setLines } = useEngineDisplaySettings();
  const [anchorEl, setAnchorEl] = useState<HTMLElement | null>(null);

  const open = (event: MouseEvent<HTMLElement>) => {
    // The gear sits next to the engine on/off switch — never toggle it.
    event.stopPropagation();
    setAnchorEl(event.currentTarget);
  };

  return (
    <>
      <IconButton size="small" aria-label={t('settings')} onClick={open}>
        <SettingsIcon fontSize="small" />
      </IconButton>
      <Popover
        open={anchorEl !== null}
        anchorEl={anchorEl}
        onClose={() => setAnchorEl(null)}
        onClick={(event) => event.stopPropagation()}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'left' }}
      >
        <Box sx={{ p: 1.5, display: 'flex', flexDirection: 'column', gap: 1.5 }}>
          <OptionGroup label={t('depth')} options={ENGINE_DEPTH_OPTIONS} value={depth} onChange={setDepth} />
          <OptionGroup label={t('lines')} options={ENGINE_LINES_OPTIONS} value={lines} onChange={setLines} />
          {extra}
        </Box>
      </Popover>
    </>
  );
}
