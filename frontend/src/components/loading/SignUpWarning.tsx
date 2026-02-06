import { Box, Typography } from "@mui/material"
import { purpleTheme } from "@/theme/theme"

const Warning = () => {
    return (
        <Box
        sx={{
          p: 4,
          display: "flex",
          justifyContent: "center",
          backgroundColor: purpleTheme.background.main,
          minHeight: "100vh",
        }}
      >
        <Typography variant="h6" sx={{ color: purpleTheme.text.primary }}>
          Please sign in to view this page.
        </Typography>
      </Box>
    )
}

export default Warning