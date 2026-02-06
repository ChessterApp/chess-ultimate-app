import { Box, Typography, Button, TextField } from "@mui/material";
import { purpleTheme } from "@/theme/theme";
import { Upload } from "@mui/icons-material";

interface LoadPGNProp {
    pgnText: string;
    setPgnText: (pgn: string) => void;
    loadPGN: () => void;
    setInputsVisible: (view: boolean) => void;
}

function LoadPGNGame({pgnText, setPgnText, loadPGN, setInputsVisible}: LoadPGNProp) {


  return (
    <Box>
      <Typography
        variant="h6"
        sx={{
          color: purpleTheme.text.accent,
          mb: 2,
          display: "flex",
          alignItems: "center",
        }}
      >
        <Upload sx={{ mr: 1 }} />
        Direct PGN Input
      </Typography>
      <TextField
        multiline
        minRows={4}
        label="Paste PGN Here"
        fullWidth
        value={pgnText}
        onChange={(e) => setPgnText(e.target.value)}
        sx={{
          backgroundColor: purpleTheme.background.input,
          borderRadius: 2,
          mb: 2,
          "& .MuiOutlinedInput-root": {
            "& fieldset": {
              borderColor: purpleTheme.secondary,
            },
            "&:hover fieldset": {
              borderColor: purpleTheme.accent,
            },
            "&.Mui-focused fieldset": {
              borderColor: purpleTheme.accent,
            },
          },
        }}
        placeholder="1. e4 e5 2. Nf3 Nc6 3. Bb5 a6..."
        slotProps={{
          input: { sx: { color: purpleTheme.text.primary } },
          inputLabel: { sx: { color: purpleTheme.text.secondary } },
        }}
      />
      <Button
        variant="contained"
        fullWidth
        onClick={() => {
          if (pgnText !== "") {
            loadPGN();
            setInputsVisible(false);
          } else {
            alert("Invalid PGN input!");
          }
        }}
        sx={{
          backgroundColor: purpleTheme.primary,
          "&:hover": { backgroundColor: purpleTheme.primaryDark },
          borderRadius: 2,
          py: 1.5,
          textTransform: "none",
          fontSize: "1rem",
        }}
      >
        Load PGN
      </Button>
    </Box>
  );
}

export default LoadPGNGame;
