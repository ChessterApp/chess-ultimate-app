import { useState } from "react";
import { Box, Typography, TextField, Button } from "@mui/material";
import { purpleTheme } from "@/theme/theme";
import { Analytics } from "@mui/icons-material";
import { parsePgnChapters } from "@/libs/game/helper";

export interface Chapter {
    title: string;
    url: string;
    pgn: string;
}

interface GameLoaderProp {
    setChapters: (chapter: Chapter[]) => void;
    setInputsVisible: (view: boolean) => void;
}

function LoadStudy({setChapters, setInputsVisible}: GameLoaderProp) {

  const [studyUrl, setStudyUrl] = useState("");

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
        <Analytics sx={{ mr: 1 }} />
        Lichess Study
      </Typography>
      <TextField
        fullWidth
        label="Paste Lichess Study URL"
        value={studyUrl}
        onChange={(e) => setStudyUrl(e.target.value)}
        placeholder="https://lichess.org/study/GuglnqGD"
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
        slotProps={{
          inputLabel: { sx: { color: purpleTheme.text.secondary } },
          input: { sx: { color: purpleTheme.text.primary } },
        }}
      />
      <Button
        variant="contained"
        fullWidth
        sx={{
          backgroundColor: purpleTheme.primary,
          "&:hover": { backgroundColor: purpleTheme.primaryDark },
          borderRadius: 2,
          py: 1.5,
          textTransform: "none",
          fontSize: "1rem",
        }}
        onClick={async () => {
          const idMatch = studyUrl.match(/study\/([a-zA-Z0-9]+)/);
          if (!idMatch) return alert("Invalid study URL");

          try {
            const res = await fetch(
              `https://lichess.org/api/study/${idMatch[1]}.pgn`
            );

            if (!res.ok) {
              if (res.status === 404) {
                return alert("Study not found. Please check the URL.");
              }
              return alert(`Failed to load study: ${res.status} ${res.statusText}`);
            }

            const text = await res.text();

            // Check if response is HTML (error page) instead of PGN
            if (text.trim().startsWith('<!DOCTYPE') || text.trim().startsWith('<html')) {
              return alert("This study is private or does not exist. Please use a public study URL.");
            }

            const parsed = parsePgnChapters(text);
            if (parsed.length === 0) return alert("No chapters found in this study");

            setChapters(parsed);
            setInputsVisible(false);
          } catch (error) {
            console.error("Error loading study:", error);
            alert("Failed to load study. Please check your connection and try again.");
          }
        }}
      >
        Load Study
      </Button>
    </Box>
  );
}

export default LoadStudy;
