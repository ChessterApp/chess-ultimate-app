import { createTheme } from "@mui/material";

// ─── Light MUI Theme ───
export const chessterLightTheme = createTheme({
  palette: {
    mode: 'light',
    primary: {
      main: '#8B5CF6',
      dark: '#7C3AED',
      light: '#A78BFA',
    },
    secondary: {
      main: '#AB47BC',
    },
    background: {
      default: '#FAFAFA',
      paper: '#FFFFFF',
    },
    text: {
      primary: '#18181B',
      secondary: '#52525B',
    },
    success: { main: '#22C55E' },
    error: { main: '#EF4444' },
    warning: { main: '#F59E0B' },
    divider: '#E4E4E7',
  },
  shape: { borderRadius: 12 },
  components: {
    MuiCard: {
      styleOverrides: {
        root: { borderRadius: 16 },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: { borderRadius: 12 },
      },
    },
    MuiButton: {
      styleOverrides: {
        root: { borderRadius: 8, textTransform: 'none' as const },
      },
    },
    MuiChip: {
      styleOverrides: {
        root: { borderRadius: 6 },
      },
    },
    MuiDialog: {
      styleOverrides: {
        paper: { borderRadius: 16 },
      },
    },
  },
});

// ─── Dark MUI Theme ───
export const chessterDarkTheme = createTheme({
  palette: {
    mode: 'dark',
    primary: {
      main: '#A78BFA',
      dark: '#8B5CF6',
      light: '#C4B5FD',
    },
    secondary: {
      main: '#CE93D8',
    },
    background: {
      default: '#0f0f0f',
      paper: '#1a1a1a',
    },
    text: {
      primary: '#F0F0F0',
      secondary: '#A0A0A0',
    },
    success: { main: '#4ADE80' },
    error: { main: '#F87171' },
    warning: { main: '#FBBF24' },
    divider: '#2a2a2a',
  },
  shape: { borderRadius: 12 },
  components: {
    MuiCard: {
      styleOverrides: {
        root: { borderRadius: 16 },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: { borderRadius: 12 },
      },
    },
    MuiButton: {
      styleOverrides: {
        root: { borderRadius: 8, textTransform: 'none' as const },
      },
    },
    MuiChip: {
      styleOverrides: {
        root: { borderRadius: 6 },
      },
    },
    MuiDialog: {
      styleOverrides: {
        paper: { borderRadius: 16 },
      },
    },
  },
});

