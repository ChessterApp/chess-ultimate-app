import { Box, Typography, Button, Divider } from "@mui/material";
import { History as HistoryIcon } from "@mui/icons-material";
import { purpleTheme } from "@/theme/theme";
import { SavedGameReview } from "./SaveGameReviewDialog";
import { useLocalStorage } from "usehooks-ts";

interface GameReviewHistoryProp {
  setHistoryDialogOpen: (save: boolean) => void;
}

function GamereviewHistory({ setHistoryDialogOpen }: GameReviewHistoryProp) {
  const [gameReviewHistory] = useLocalStorage<SavedGameReview[]>(
    "chess-game-review-history",
    []
  );

  return (
    <>
      {gameReviewHistory.length > 0 && (
        <>
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
              <HistoryIcon sx={{ mr: 1 }} />
              Saved Game Reviews
            </Typography>
            <Button
              variant="outlined"
              fullWidth
              onClick={() => setHistoryDialogOpen(true)}
              startIcon={<HistoryIcon />}
              sx={{
                borderColor: purpleTheme.secondary,
                color: purpleTheme.text.primary,
                "&:hover": {
                  borderColor: purpleTheme.accent,
                  backgroundColor: `${purpleTheme.accent}20`,
                },
                borderRadius: 2,
                py: 1.5,
                textTransform: "none",
                fontSize: "1rem",
              }}
            >
              Load from History ({gameReviewHistory.length} saved)
            </Button>
          </Box>
          <Divider sx={{ borderColor: purpleTheme.secondary }} />
        </>
      )}
    </>
  );
}

export default GamereviewHistory;
