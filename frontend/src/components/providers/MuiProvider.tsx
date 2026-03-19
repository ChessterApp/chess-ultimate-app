"use client"

import { type ReactNode } from "react"
import { ThemeProvider } from "@mui/material/styles"
import CssBaseline from "@mui/material/CssBaseline"
import { useDarkMode } from "@/hooks/useDarkMode"
import { chessterLightTheme, chessterDarkTheme } from "@/theme/theme"

/**
 * MUI ThemeProvider wrapper that dynamically applies theme based on dark mode state.
 * Only load this provider on pages that actually use MUI components.
 */
export default function MuiProvider({ children }: { children: ReactNode }) {
  const { isDark } = useDarkMode()
  const muiTheme = isDark ? chessterDarkTheme : chessterLightTheme

  return (
    <ThemeProvider theme={muiTheme}>
      <CssBaseline enableColorScheme />
      {children}
    </ThemeProvider>
  )
}
