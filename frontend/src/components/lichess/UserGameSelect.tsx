import React, { useState } from "react";
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Stack,
} from "@mui/material";
import UserLichessGames from "./UserLichessGames";
import SportsEsportsIcon from "@mui/icons-material/SportsEsports";

interface UserGameSelectProps {
  loadPGN: (pgn: string) => void;
}

const UserGameSelect: React.FC<UserGameSelectProps> = ({ loadPGN }) => {
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
            backgroundColor: "primary.main",
            color: "text.primary",
            '&:hover': {
              backgroundColor: "primary.dark",
            },
            py: 1.5,
            fontWeight: 'medium',
          }}
        >
          Select Lichess Game
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
              backgroundColor: "background.default",
              color: "text.primary",
              padding: 2,
              borderRadius: 2,
              borderWidth: 1,
              borderStyle: "solid",
              borderColor: "secondary.main",
            },
          },
        }}
      >
        <DialogTitle
          sx={{
            color: "text.primary",
            textAlign: 'center',
            fontWeight: 'bold',
            borderBottomWidth: 1,
            borderBottomStyle: "solid",
            borderBottomColor: "secondary.main",
            pb: 2,
            mb: 2,
          }}
        >
          Select a Recent Lichess Game
        </DialogTitle>

        <DialogContent sx={{ p: 0 }}>
          <UserLichessGames loadPGN={loadPGN} setOpen={setOpen} />
        </DialogContent>

        <DialogActions
          sx={{
            pt: 2,
            borderTopWidth: 1,
            borderTopStyle: "solid",
            borderTopColor: "secondary.main",
            justifyContent: 'center',
          }}
        >
          <Button
            onClick={handleClose}
            variant="outlined"
            sx={{
              color: "text.secondary",
              borderColor: "secondary.main",
              '&:hover': {
                borderColor: "primary.main",
                backgroundColor: "background.paper",
                color: "text.primary",
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

export default UserGameSelect;
