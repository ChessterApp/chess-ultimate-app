import { Box } from "@mui/material"
import {CircularProgress} from "@mui/material"

const Loader = () => {

    return (
        <Box
        sx={{
          p: 4,
          display: "flex",
          justifyContent: "center",
          backgroundColor: "background.default",
          minHeight: "100vh",
        }}
      >
        <CircularProgress sx={{ color: "primary.light" }} />
      </Box>
    )
}

export default Loader;
