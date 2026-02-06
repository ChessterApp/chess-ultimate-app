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
import { purpleTheme } from "@/theme/theme";

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
            backgroundColor: purpleTheme.primary,
            color: purpleTheme.text.primary,
            '&:hover': {
              backgroundColor: purpleTheme.primaryDark,
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
          Select a Recent Lichess Game
        </DialogTitle>
        
        <DialogContent sx={{ p: 0 }}>
          <UserLichessGames loadPGN={loadPGN} setOpen={setOpen} />
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

export default UserGameSelect;