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
          Select a Recent Chess.com Game
        </DialogTitle>

        <DialogContent sx={{ p: 0 }}>
          <UserChessDotComGames loadPGN={loadPGN} setOpen={setOpen} />
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

export default UserChessDotComGameSelect;
