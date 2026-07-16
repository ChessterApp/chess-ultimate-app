import { useState } from "react";
import { Box, Typography, TextField, Button } from "@mui/material";
import { Analytics } from "@mui/icons-material";
import { parsePgnChapters } from "@/lib/game/helper";
import { apiFetch, ApiError } from '@/lib/api';
import { useToast } from '@/components/ToastProvider';

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
  const { showToast } = useToast();
  const [studyUrl, setStudyUrl] = useState("");

  return (
    <Box>
      <Typography
        variant="h6"
        sx={{
          color: 'secondary.main',
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
          backgroundColor: 'background.paper',
          borderRadius: 2,
          mb: 2,
          "& .MuiOutlinedInput-root": {
            "& fieldset": {
              borderColor: 'secondary.main',
            },
            "&:hover fieldset": {
              borderColor: 'primary.light',
            },
            "&.Mui-focused fieldset": {
              borderColor: 'primary.light',
            },
          },
        }}
        slotProps={{
          inputLabel: { sx: { color: 'text.secondary' } },
          input: { sx: { color: 'text.primary' } },
        }}
      />
      <Button
        variant="contained"
        fullWidth
        sx={{
          backgroundColor: 'primary.main',
          "&:hover": { backgroundColor: 'primary.dark' },
          borderRadius: 2,
          py: 1.5,
          textTransform: "none",
          fontSize: "1rem",
        }}
        onClick={async () => {
          const idMatch = studyUrl.match(/study\/([a-zA-Z0-9]+)/);
          if (!idMatch) {
            showToast("Invalid study URL", "error");
            return;
          }

          try {
            const text = await apiFetch<string>(
              `https://lichess.org/api/study/${idMatch[1]}.pgn`
            );

            // Check if response is HTML (error page) instead of PGN
            if (text.trim().startsWith('<!DOCTYPE') || text.trim().startsWith('<html')) {
              showToast("This study is private or does not exist", "error");
              return;
            }

            const parsed = parsePgnChapters(text);
            if (parsed.length === 0) {
              showToast("No chapters found in this study", "error");
              return;
            }

            setChapters(parsed);
            setInputsVisible(false);
            showToast("Study loaded successfully!", "success");
          } catch (error) {
            if (error instanceof ApiError) {
              if (error.status === 404) {
                showToast("Study not found — please check the URL", "error");
                return;
              }
              if (error.status === 429) {
                showToast("Too many requests — please slow down", "error");
                return;
              }
              if (error.status === 0) {
                showToast("Network error — check your connection", "error");
                return;
              }
            }
            console.error("Error loading study:", error);
            showToast("Failed to load study — please try again", "error");
          }
        }}
      >
        Load Study
      </Button>
    </Box>
  );
}

export default LoadStudy;
