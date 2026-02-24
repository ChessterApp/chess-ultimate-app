import React, { useEffect, useState } from "react";
import { useLocalStorage } from "usehooks-ts";
import {
  ChessDotComGame,
  fetchUserRecentGames,
  formatGameDate,
  getTimeClassColor,
  getTimeClassLabel,
} from "./ChessDotComTypes";
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
import CalendarMonthIcon from "@mui/icons-material/CalendarMonth";

interface UserGameProp {
  loadPGN: (pgn: string) => void;
  setOpen: (handle: boolean) => void;
}

export default function UserChessDotComGames({ loadPGN, setOpen }: UserGameProp) {
  const [requestCount, setRequestCount] = useState(0);
  const [chessdotcomUsername, setChessdotcomUsername] = useLocalStorage(
    "chessdotcom-username",
    ""
  );
  const [games, setGames] = useState<ChessDotComGame[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!chessdotcomUsername) {
      setGames([]);
      return;
    }

    setLoading(true);
    const timeout = setTimeout(async () => {
      const games = await fetchUserRecentGames(chessdotcomUsername);
      setGames(games);
      setLoading(false);
    }, requestCount === 0 ? 0 : 500);

    setRequestCount((prev) => prev + 1);
    return () => clearTimeout(timeout);
  }, [chessdotcomUsername]);

  const getSpeedIcon = (timeClass: string) => {
    switch (timeClass) {
      case "bullet":
        return <FlashOnIcon fontSize="small" sx={{ mr: 1, color: "primary.main" }} />;
      case "blitz":
        return <TimerIcon fontSize="small" sx={{ mr: 1, color: "primary.main" }} />;
      case "rapid":
        return <RocketLaunchIcon fontSize="small" sx={{ mr: 1, color: "primary.main" }} />;
      case "classical":
        return <HistoryIcon fontSize="small" sx={{ mr: 1, color: "primary.main" }} />;
      case "daily":
        return <CalendarMonthIcon fontSize="small" sx={{ mr: 1, color: "primary.main" }} />;
      default:
        return <TimerIcon fontSize="small" sx={{ mr: 1, color: "primary.main" }} />;
    }
  };

  const getResultDisplay = (game: ChessDotComGame, username: string) => {
    const userPlayedWhite = game.white.username.toLowerCase() === username.toLowerCase();
    const userPlayer = userPlayedWhite ? game.white : game.black;

    let resultText = "";
    if (userPlayer.result === "win") {
      resultText = "Won";
    } else if (userPlayer.result === "resigned" || userPlayer.result === "timeout" || userPlayer.result === "checkmated") {
      resultText = "Lost";
    } else if (userPlayer.result === "agreed" || userPlayer.result === "stalemate" || userPlayer.result === "repetition" || userPlayer.result === "insufficient") {
      resultText = "Draw";
    } else {
      resultText = userPlayer.result;
    }

    return (
      <Chip
        label={resultText}
        size="small"
        sx={{
          ml: 1,
          backgroundColor:
            userPlayer.result === "win"
              ? "#27ae60"
              : userPlayer.result.includes("draw") || userPlayer.result === "agreed" || userPlayer.result === "stalemate"
              ? "#95a5a6"
              : "#e74c3c",
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
            label="Chess.com Username"
            variant="outlined"
            value={chessdotcomUsername}
            onChange={(e) => setChessdotcomUsername(e.target.value)}
            sx={{
              '& .MuiInputLabel-root': {
                color: 'text.secondary',
              },
              "& .MuiOutlinedInput-root": {
                color: "text.primary",
                backgroundColor: "background.paper",
                "& fieldset": {
                  borderColor: "secondary.main",
                },
                "&:hover fieldset": {
                  borderColor: "primary.main",
                },
                "&.Mui-focused fieldset": {
                  borderColor: "primary.main",
                },
              },
            }}
          />
        </FormControl>
      </Box>

      {!chessdotcomUsername ? (
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
              key={game.uuid}
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
                    {getSpeedIcon(game.time_class)}
                    <span>
                      {`${game.white.username} (${game.white.rating}) vs ${game.black.username} (${game.black.rating})`}
                    </span>
                    {getResultDisplay(game, chessdotcomUsername)}
                  </Box>
                }
                secondary={
                  <Box display="flex" alignItems="center" gap={1}>
                    <Chip
                      label={getTimeClassLabel(game.time_class)}
                      size="small"
                      sx={{
                        backgroundColor: getTimeClassColor(game.time_class),
                        color: "white",
                        fontSize: "0.7rem",
                      }}
                    />
                    <span>{formatGameDate(game.end_time)}</span>
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
