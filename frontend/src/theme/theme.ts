import { createTheme } from "@mui/material";

// ─── Light MUI Theme ───
export const chessterLightTheme = createTheme({
  palette: {
    mode: 'light',
    primary: {
      main: '#1f2937',
      dark: '#111827',
      light: '#14b8a6',
    },
    secondary: {
      main: '#AB47BC',
    },
    background: {
      default: '#fafaf9',
      paper: '#FFFFFF',
    },
    text: {
      primary: '#18181B',
      secondary: '#52525B',
    },
    success: { main: '#22C55E' },
    error: { main: '#EF4444' },
    warning: { main: '#F59E0B' },
    divider: '#e5e7eb',
  },
  shape: { borderRadius: 12 },
  components: {
    MuiCard: {
      styleOverrides: {
        root: { borderRadius: 32 },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: { borderRadius: 24 },
      },
    },
    MuiButton: {
      styleOverrides: {
        root: { borderRadius: 9999, textTransform: 'none' as const },
      },
    },
    MuiChip: {
      styleOverrides: {
        root: { borderRadius: 9999 },
      },
    },
    MuiDialog: {
      styleOverrides: {
        paper: { borderRadius: 24 },
      },
    },
    MuiMenu: {
      styleOverrides: {
        paper: {
          backgroundImage: 'none !important',
          backgroundColor: '#FFFFFF !important',
          border: '1px solid #e5e7eb',
        },
      },
    },
    MuiPopover: {
      styleOverrides: {
        paper: {
          backgroundImage: 'none !important',
          backgroundColor: '#FFFFFF !important',
        },
      },
    },
    MuiSelect: {
      defaultProps: {
        MenuProps: {
          PaperProps: {
            sx: {
              backgroundImage: 'none !important',
              backgroundColor: '#FFFFFF !important',
              border: '1px solid #e5e7eb',
            },
          },
        },
      },
    },
  },
});

// ─── Dark MUI Theme ───
export const chessterDarkTheme = createTheme({
  palette: {
    mode: 'dark',
    primary: {
      main: '#14b8a6',
      dark: '#0d9488',
      light: '#2dd4bf',
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
        root: { borderRadius: 32 },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: { borderRadius: 24 },
      },
    },
    MuiButton: {
      styleOverrides: {
        root: { borderRadius: 9999, textTransform: 'none' as const },
      },
    },
    MuiChip: {
      styleOverrides: {
        root: { borderRadius: 9999 },
      },
    },
    MuiDialog: {
      styleOverrides: {
        paper: { borderRadius: 24 },
      },
    },
    MuiMenu: {
      styleOverrides: {
        paper: {
          backgroundImage: 'none !important',
          backgroundColor: '#1a1a1a !important',
          border: '1px solid #2a2a2a',
        },
      },
    },
    MuiPopover: {
      styleOverrides: {
        paper: {
          backgroundImage: 'none !important',
          backgroundColor: '#1a1a1a !important',
        },
      },
    },
    MuiSelect: {
      defaultProps: {
        MenuProps: {
          PaperProps: {
            sx: {
              backgroundImage: 'none !important',
              backgroundColor: '#1a1a1a !important',
              border: '1px solid #2a2a2a',
            },
          },
        },
      },
    },
  },
});
