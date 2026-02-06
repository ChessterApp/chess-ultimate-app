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
import { purpleTheme } from "@/theme/theme";

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
        return <FlashOnIcon fontSize="small" sx={{ mr: 1, color: purpleTheme.primary }} />;
      case "blitz":
        return <TimerIcon fontSize="small" sx={{ mr: 1, color: purpleTheme.primary }} />;
      case "rapid":
        return <RocketLaunchIcon fontSize="small" sx={{ mr: 1, color: purpleTheme.primary }} />;
      case "classical":
        return <HistoryIcon fontSize="small" sx={{ mr: 1, color: purpleTheme.primary }} />;
      case "daily":
        return <CalendarMonthIcon fontSize="small" sx={{ mr: 1, color: purpleTheme.primary }} />;
      default:
        return <TimerIcon fontSize="small" sx={{ mr: 1, color: purpleTheme.primary }} />;
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
        backgroundColor: purpleTheme.background.paper,
        color: purpleTheme.text.primary,
      }}
    >
      <Box display="flex" justifyContent="center" mb={2}>
        <FormControl>
          <TextField
            label="Chess.com Username"
            variant="outlined"
            value={chessdotcomUsername}
            onChange={(e) => setChessdotcomUsername(e.target.value)}
            InputLabelProps={{
              style: { color: purpleTheme.text.secondary },
            }}
            InputProps={{
              style: {
                color: purpleTheme.text.primary,
                backgroundColor: purpleTheme.background.input,
              },
            }}
            sx={{
              "& .MuiOutlinedInput-root": {
                "& fieldset": {
                  borderColor: purpleTheme.secondary,
                },
                "&:hover fieldset": {
                  borderColor: purpleTheme.primary,
                },
                "&.Mui-focused fieldset": {
                  borderColor: purpleTheme.primary,
                },
              },
            }}
          />
        </FormControl>
      </Box>

      {!chessdotcomUsername ? (
        <Typography textAlign="center" color={purpleTheme.text.secondary}>
          Enter a username to load recent games
        </Typography>
      ) : loading ? (
        <Box display="flex" justifyContent="center" mt={4}>
          <CircularProgress sx={{ color: purpleTheme.primary }} />
        </Box>
      ) : games.length === 0 ? (
        <Typography textAlign="center" color={purpleTheme.text.secondary}>
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
                backgroundColor: purpleTheme.background.card,
                color: purpleTheme.text.primary,
                borderRadius: "8px",
                "&:hover": {
                  backgroundColor: purpleTheme.primaryDark,
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
                  color: purpleTheme.text.primary,
                }}
                secondaryTypographyProps={{
                  component: "div",
                  noWrap: true,
                  color: purpleTheme.text.secondary,
                }}
              />
            </ListItemButton>
          ))}
        </List>
      )}
    </Paper>
  );
}
