import { Box } from "@mui/material"
import { purpleTheme } from "@/theme/theme"
import {CircularProgress} from "@mui/material"

const Loader = () => {

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
        <CircularProgress sx={{ color: purpleTheme.accent }} />
      </Box>
    )
}

export default Loader;