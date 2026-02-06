import React, { useState } from "react";
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Stack,
} from "@mui/material";
import UserChessDotComGames from "./UserChessDotComGames";
import SportsEsportsIcon from "@mui/icons-material/SportsEsports";
import { purpleTheme } from "@/theme/theme";

interface UserGameSelectProps {
  loadPGN: (pgn: string) => void;
}

const UserChessDotComGameSelect: React.FC<UserGameSelectProps> = ({ loadPGN }) => {
  const [open, setOpen] = useState(false);

  const handleOpen = () => setOpen(true);
  const handleClose = () => setOpen(false);

  return (
    <>
      <Stack spacing={2} sx={{ mb: 3 }}>
        <Button
          variant="contained"
          onClick={handleOpen}
          startIcon={<SportsEsportsIcon />}
          sx={{
            backgroundColor: "#7fa650", // Chess.com green color
            color: "#ffffff",
            '&:hover': {
              backgroundColor: "#6d8f44",
            },
            py: 1.5,
            fontWeight: 'medium',
          }}
        >
          Select Chess.com Game
        </Button>
      </Stack>

      <Dialog
        open={open}
        onClose={handleClose}
        fullWidth
        maxWidth="md"
        slotProps={{
          paper: {
            sx: {
              backgroundColor: purpleTheme.background.main,
              color: purpleTheme.text.primary,
              padding: 2,
              borderRadius: 2,
              border: `1px solid ${purpleTheme.secondary}`,
            },
          },
        }}
      >
        <DialogTitle
          sx={{
            color: purpleTheme.text.primary,
            textAlign: 'center',
            fontWeight: 'bold',
            borderBottom: `1px solid ${purpleTheme.secondary}`,
            pb: 2,
            mb: 2,
          }}
        >
          Select a Recent Chess.com Game
        </DialogTitle>

        <DialogContent sx={{ p: 0 }}>
          <UserChessDotComGames loadPGN={loadPGN} setOpen={setOpen} />
        </DialogContent>

        <DialogActions
          sx={{
            pt: 2,
            borderTop: `1px solid ${purpleTheme.secondary}`,
            justifyContent: 'center',
          }}
        >
          <Button
            onClick={handleClose}
            variant="outlined"
            sx={{
              color: purpleTheme.text.secondary,
              borderColor: purpleTheme.secondary,
              '&:hover': {
                borderColor: purpleTheme.primary,
                backgroundColor: purpleTheme.background.card,
                color: purpleTheme.text.primary,
              },
              minWidth: 100,
            }}
          >
            Close
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
};

export default UserChessDotComGameSelect;
