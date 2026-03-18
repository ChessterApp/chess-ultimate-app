/**
 * TwicExplorer — Database explorer for TWIC position analysis
 *
 * Shows candidate moves from our local 100M+ TWIC database and master games
 */

import React, { useState } from "react";
import {
  Box,
  CircularProgress,
  Typography,
  Stack,
  Paper,
  TextField,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Chip,
  IconButton,
  Collapse,
  ToggleButton,
  ToggleButtonGroup,
  useTheme,
  alpha,
} from "@mui/material";
import {
  ExpandMore as ExpandMoreIcon,
  ExpandLess as ExpandLessIcon,
  Storage as StorageIcon,
  Person as PersonIcon,
} from "@mui/icons-material";
import { useTwicCandidates } from "@/hooks/useTwicCandidates";
import { useTwicGames } from "@/hooks/useTwicGames";

interface TwicExplorerProps {
  fen: string;
  onMoveClick?: (san: string) => void;
}

export const TwicExplorer: React.FC<TwicExplorerProps> = ({
  fen,
  onMoveClick,
}) => {
  const theme = useTheme();
  const [playerSearch, setPlayerSearch] = useState("");
  const [playerColor, setPlayerColor] = useState<"white" | "black" | "">("");
  const [showGames, setShowGames] = useState(true);

  // Fetch candidate moves
  const {
    data: candidatesData,
    loading: candidatesLoading,
    error: candidatesError,
  } = useTwicCandidates({ fen, enabled: true });

  // Fetch games (with player search)
  const {
    data: gamesData,
    loading: gamesLoading,
    error: gamesError,
  } = useTwicGames({
    fen,
    enabled: true,
    limit: 15,
    playerName: playerSearch,
    playerColor,
    sortBy: "rating",
  });

  const handlePlayerColorChange = (
    _event: React.MouseEvent<HTMLElement>,
    newColor: "white" | "black" | "",
  ) => {
    if (newColor !== null) {
      setPlayerColor(newColor);
    }
  };

  const formatPercentage = (value: number | undefined) => {
    if (value === undefined) return "0%";
    return `${value.toFixed(1)}%`;
  };

  const formatElo = (whiteElo: number, blackElo: number) => {
    const avgElo = Math.round((whiteElo + blackElo) / 2);
    return avgElo > 0 ? avgElo : "—";
  };

  return (
    <Paper
      sx={{
        backgroundColor: "background.paper",
        borderRadius: 2,
        overflow: "hidden",
      }}
    >
      {/* Header */}
      <Box
        sx={{
          p: 2,
          borderBottom: 1,
          borderColor: "divider",
          backgroundColor: alpha(theme.palette.primary.main, 0.05),
        }}
      >
        <Stack direction="row" alignItems="center" spacing={1}>
          <StorageIcon sx={{ color: "primary.main" }} />
          <Typography variant="h6" sx={{ fontWeight: 600 }}>
            Master Games Database
          </Typography>
          {candidatesData && (
            <Chip
              label={`${candidatesData.total_games.toLocaleString()} games`}
              size="small"
              sx={{ ml: 1 }}
            />
          )}
        </Stack>
      </Box>

      {/* Candidate Moves Section */}
      <Box sx={{ p: 2 }}>
        <Typography variant="subtitle2" sx={{ mb: 2, fontWeight: 600 }}>
          Candidate Moves
        </Typography>

        {candidatesLoading && (
          <Box sx={{ display: "flex", justifyContent: "center", py: 4 }}>
            <CircularProgress size={32} />
          </Box>
        )}

        {candidatesError && (
          <Typography variant="body2" color="error" sx={{ py: 2 }}>
            {candidatesError}
          </Typography>
        )}

        {candidatesData && candidatesData.moves.length === 0 && (
          <Typography variant="body2" color="text.secondary" sx={{ py: 2 }}>
            No data for this position in our database.
          </Typography>
        )}

        {candidatesData && candidatesData.moves.length > 0 && (
          <TableContainer>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell sx={{ fontWeight: 600 }}>Move</TableCell>
                  <TableCell align="right" sx={{ fontWeight: 600 }}>
                    Games
                  </TableCell>
                  <TableCell align="right" sx={{ fontWeight: 600 }}>
                    Win%
                  </TableCell>
                  <TableCell align="right" sx={{ fontWeight: 600 }}>
                    Draw%
                  </TableCell>
                  <TableCell align="right" sx={{ fontWeight: 600 }}>
                    Loss%
                  </TableCell>
                  <TableCell align="right" sx={{ fontWeight: 600 }}>
                    Avg Elo
                  </TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {candidatesData.moves.map((move, index) => (
                  <TableRow
                    key={index}
                    hover
                    onClick={() => onMoveClick?.(move.san)}
                    sx={{
                      cursor: onMoveClick ? "pointer" : "default",
                      "&:hover": {
                        backgroundColor: alpha(theme.palette.primary.main, 0.08),
                      },
                    }}
                  >
                    <TableCell>
                      <Typography
                        variant="body2"
                        sx={{ fontWeight: 600, fontFamily: "monospace" }}
                      >
                        {move.san}
                      </Typography>
                    </TableCell>
                    <TableCell align="right">
                      <Typography variant="body2">
                        {move.games.toLocaleString()}
                      </Typography>
                    </TableCell>
                    <TableCell align="right">
                      <Typography variant="body2" color="success.main">
                        {formatPercentage(move.win_rate)}
                      </Typography>
                    </TableCell>
                    <TableCell align="right">
                      <Typography variant="body2" color="text.secondary">
                        {formatPercentage(move.draw_rate)}
                      </Typography>
                    </TableCell>
                    <TableCell align="right">
                      <Typography variant="body2" color="error.main">
                        {formatPercentage(move.loss_rate)}
                      </Typography>
                    </TableCell>
                    <TableCell align="right">
                      <Typography variant="body2">
                        {formatElo(move.avg_white_elo, move.avg_black_elo)}
                      </Typography>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        )}
      </Box>

      {/* Master Games Section */}
      <Box
        sx={{
          borderTop: 1,
          borderColor: "divider",
        }}
      >
        <Box
          sx={{
            p: 2,
            display: "flex",
            alignItems: "center",
            cursor: "pointer",
            "&:hover": {
              backgroundColor: alpha(theme.palette.primary.main, 0.05),
            },
          }}
          onClick={() => setShowGames(!showGames)}
        >
          <Typography variant="subtitle2" sx={{ fontWeight: 600, flex: 1 }}>
            Master Games
            {gamesData && ` (${gamesData.total})`}
          </Typography>
          <IconButton size="small">
            {showGames ? <ExpandLessIcon /> : <ExpandMoreIcon />}
          </IconButton>
        </Box>

        <Collapse in={showGames}>
          <Box sx={{ px: 2, pb: 2 }}>
            {/* Player Search */}
            <Stack spacing={2} sx={{ mb: 2 }}>
              <TextField
                size="small"
                placeholder="Search by player name..."
                value={playerSearch}
                onChange={(e) => setPlayerSearch(e.target.value)}
                InputProps={{
                  startAdornment: <PersonIcon sx={{ mr: 1, color: "text.secondary" }} />,
                }}
              />

              <ToggleButtonGroup
                value={playerColor}
                exclusive
                onChange={handlePlayerColorChange}
                size="small"
                fullWidth
              >
                <ToggleButton value="">Both</ToggleButton>
                <ToggleButton value="white">White</ToggleButton>
                <ToggleButton value="black">Black</ToggleButton>
              </ToggleButtonGroup>
            </Stack>

            {gamesLoading && (
              <Box sx={{ display: "flex", justifyContent: "center", py: 4 }}>
                <CircularProgress size={32} />
              </Box>
            )}

            {gamesError && (
              <Typography variant="body2" color="error" sx={{ py: 2 }}>
                {gamesError}
              </Typography>
            )}

            {gamesData && gamesData.games.length === 0 && (
              <Typography variant="body2" color="text.secondary" sx={{ py: 2 }}>
                No games found for this position.
              </Typography>
            )}

            {gamesData && gamesData.games.length > 0 && (
              <Stack spacing={1}>
                {gamesData.games.map((game) => (
                  <Paper
                    key={game.id}
                    elevation={0}
                    sx={{
                      p: 1.5,
                      border: 1,
                      borderColor: "divider",
                      borderRadius: 1,
                      "&:hover": {
                        backgroundColor: alpha(theme.palette.primary.main, 0.05),
                      },
                    }}
                  >
                    <Stack spacing={0.5}>
                      <Stack direction="row" justifyContent="space-between" alignItems="center">
                        <Typography variant="body2" sx={{ fontWeight: 600 }}>
                          {game.white_name} vs {game.black_name}
                        </Typography>
                        <Chip
                          label={game.result}
                          size="small"
                          sx={{
                            height: 20,
                            fontSize: "0.7rem",
                            backgroundColor:
                              game.result === "1-0"
                                ? alpha(theme.palette.success.main, 0.2)
                                : game.result === "0-1"
                                ? alpha(theme.palette.error.main, 0.2)
                                : alpha(theme.palette.grey[500], 0.2),
                          }}
                        />
                      </Stack>
                      <Stack direction="row" spacing={2}>
                        <Typography variant="caption" color="text.secondary">
                          {game.white_elo && `${game.white_elo}`} vs{" "}
                          {game.black_elo && `${game.black_elo}`}
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                          {game.date}
                        </Typography>
                        {game.event && (
                          <Typography variant="caption" color="text.secondary">
                            {game.event}
                          </Typography>
                        )}
                      </Stack>
                    </Stack>
                  </Paper>
                ))}
              </Stack>
            )}
          </Box>
        </Collapse>
      </Box>
    </Paper>
  );
};

export default TwicExplorer;
