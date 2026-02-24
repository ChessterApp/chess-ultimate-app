import React, { useEffect, useState } from "react";
import { useLocalStorage } from "usehooks-ts";
import {
  UserGame,
  fetchUserRecentGames,
  getSpeedColor,
  getSpeedLabel,
  formatGameDate
} from "./LichessTypes";
import {
  Box,
  CircularProgress,
  FormControl,
  List,
  ListItemButton,
  ListItemText,
  Paper,
  TextField,
  Typography,
  Chip,
} from "@mui/material";
import FlashOnIcon from "@mui/icons-material/FlashOn";
import TimerIcon from "@mui/icons-material/Timer";
import RocketLaunchIcon from "@mui/icons-material/RocketLaunch";
import HistoryIcon from "@mui/icons-material/History";
import CasinoIcon from "@mui/icons-material/Casino";
import CalendarMonthIcon from "@mui/icons-material/CalendarMonth";

interface UserGameProp {
  loadPGN: (pgn: string) => void;
  setOpen: (handle: boolean) => void;
}

export default function UserLichessGames({ loadPGN, setOpen }: UserGameProp) {
  const [requestCount, setRequestCount] = useState(0);
  const [lichessUsername, setLichessUsername] = useLocalStorage(
    "lichess-username",
    ""
  );
  const [games, setGames] = useState<UserGame[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!lichessUsername) {
      setGames([]);
      return;
    }

    setLoading(true);
    const timeout = setTimeout(async () => {
      const games = await fetchUserRecentGames(lichessUsername);
      setGames(games);
      setLoading(false);
    }, requestCount === 0 ? 0 : 500);

    setRequestCount((prev) => prev + 1);
    return () => clearTimeout(timeout);
  }, [lichessUsername]);

  const getSpeedIcon = (speed: string) => {
    switch (speed) {
      case "bullet":
      case "ultrabullet":
        return <FlashOnIcon fontSize="small" sx={{ mr: 1, color: "primary.main" }} />;
      case "blitz":
        return <TimerIcon fontSize="small" sx={{ mr: 1, color: "primary.main" }} />;
      case "rapid":
        return <RocketLaunchIcon fontSize="small" sx={{ mr: 1, color: "primary.main" }} />;
      case "classical":
        return <HistoryIcon fontSize="small" sx={{ mr: 1, color: "primary.main" }} />;
      case "correspondence":
        return <CalendarMonthIcon fontSize="small" sx={{ mr: 1, color: "primary.main" }} />;
      default:
        return <CasinoIcon fontSize="small" sx={{ mr: 1, color: "primary.main" }} />;
    }
  };

  const getResultDisplay = (game: UserGame, username: string) => {
    const userPlayedWhite = game.players.white.user?.name.toLowerCase() === username.toLowerCase();
    const userIsWinner = game.winner === (userPlayedWhite ? "white" : "black");
    const isDraw = !game.winner && game.status !== "started";

    let resultText = "";
    let backgroundColor = "";

    if (isDraw || game.status === "draw" || game.status === "stalemate") {
      resultText = "Draw";
      backgroundColor = "text.secondary";
    } else if (userIsWinner) {
      resultText = "Won";
      backgroundColor = "success.main";
    } else if (game.winner) {
      resultText = "Lost";
      backgroundColor = "error.main";
    } else {
      resultText = game.status.charAt(0).toUpperCase() + game.status.slice(1);
      backgroundColor = "text.secondary";
    }

    return (
      <Chip
        label={resultText}
        size="small"
        sx={{
          ml: 1,
          backgroundColor,
          color: "white",
          fontWeight: "bold",
        }}
      />
    );
  };

  return (
    <Paper
      elevation={3}
      sx={{
        p: 3,
        backgroundColor: "background.paper",
        color: "text.primary",
      }}
    >
      <Box display="flex" justifyContent="center" mb={2}>
        <FormControl>
          <TextField
            label="Lichess Username"
            variant="outlined"
            value={lichessUsername}
            onChange={(e) => setLichessUsername(e.target.value)}
            sx={{
              '& .MuiInputLabel-root': {
                color: 'text.secondary',
              },
              '& .MuiOutlinedInput-root': {
                color: 'text.primary',
                backgroundColor: 'background.paper',
                '& fieldset': {
                  borderColor: 'secondary.main',
                },
                '&:hover fieldset': {
                  borderColor: 'primary.main',
                },
                '&.Mui-focused fieldset': {
                  borderColor: 'primary.main',
                },
              },
            }}
          />
        </FormControl>
      </Box>

      {!lichessUsername ? (
        <Typography textAlign="center" color="text.secondary">
          Enter a username to load recent games
        </Typography>
      ) : loading ? (
        <Box display="flex" justifyContent="center" mt={4}>
          <CircularProgress sx={{ color: "primary.main" }} />
        </Box>
      ) : games.length === 0 ? (
        <Typography textAlign="center" color="text.secondary">
          No games found for this user
        </Typography>
      ) : (
        <List sx={{ maxHeight: 400, overflowY: "auto" }}>
          {games.map((game) => (
            <ListItemButton
              key={game.id}
              onClick={() => {
                loadPGN(game.pgn);
                setOpen(false);
              }}
              sx={{
                mb: 1,
                backgroundColor: "background.paper",
                color: "text.primary",
                borderRadius: "8px",
                "&:hover": {
                  backgroundColor: "primary.dark",
                },
              }}
            >
              <ListItemText
                primary={
                  <Box display="flex" alignItems="center">
                    {getSpeedIcon(game.speed)}
                    <span>
                      {`${game.players.white.user?.name || "white"} (${
                        game.players.white.rating || "?"
                      }) vs ${game.players.black.user?.name || "black"} (${
                        game.players.black.rating || "?"
                      })`}
                    </span>
                    {getResultDisplay(game, lichessUsername)}
                  </Box>
                }
                secondary={
                  <Box display="flex" alignItems="center" gap={1}>
                    <Chip
                      label={getSpeedLabel(game.speed)}
                      size="small"
                      sx={{
                        backgroundColor: getSpeedColor(game.speed),
                        color: "white",
                        fontSize: "0.7rem",
                      }}
                    />
                    <span>{formatGameDate(game.lastMoveAt)}</span>
                  </Box>
                }
                primaryTypographyProps={{
                  component: "div",
                  fontWeight: "bold",
                  noWrap: true,
                  color: "text.primary",
                }}
                secondaryTypographyProps={{
                  component: "div",
                  noWrap: true,
                  color: "text.secondary",
                }}
              />
            </ListItemButton>
          ))}
        </List>
      )}
    </Paper>
  );
}
