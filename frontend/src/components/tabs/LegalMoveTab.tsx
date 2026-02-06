import React, { useState } from "react";
import {
  Box,
  Typography,
  Paper,
  Stack,
  Switch,
  IconButton,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Chip,
} from "@mui/material";
import { Settings as SettingsIcon, Gavel} from "@mui/icons-material";

export interface LegalMoveTabProps {
  legalMoves: string[];
  handleFutureMoveLegalClick: (move: string) => void;
  disabled?: boolean;
}

export function LegalMoveTab({
  legalMoves,
  handleFutureMoveLegalClick,
  disabled = false,
}: LegalMoveTabProps) {
  const [legalMovesEnabled, setLegalMovesEnabled] = useState(true);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [maxMoves, setMaxMoves] = useState(20);
  const [sortAlphabetically, setSortAlphabetically] = useState(false);
  const [filterByPiece, setFilterByPiece] = useState("all");

  const handleLegalMovesToggle = (event: React.ChangeEvent<HTMLInputElement>) => {
    setLegalMovesEnabled(event.target.checked);
  };

  const handleSettingsClose = () => {
    setSettingsOpen(false);
  };

  // Filter and sort moves based on settings
  const processedMoves = React.useMemo(() => {
    let moves = [...legalMoves];

    // Filter by piece type
    if (filterByPiece !== "all") {
      const pieceMap: { [key: string]: string[] } = {
        pawn: moves.filter(move => !move.match(/^[NBRQK]/)),
        knight: moves.filter(move => move.startsWith("N")),
        bishop: moves.filter(move => move.startsWith("B")),
        rook: moves.filter(move => move.startsWith("R")),
        queen: moves.filter(move => move.startsWith("Q")),
        king: moves.filter(move => move.startsWith("K")),
        castle: moves.filter(move => move === "O-O" || move === "O-O-O"),
      };
      moves = pieceMap[filterByPiece] || moves;
    }

    // Sort moves
    if (sortAlphabetically) {
      moves.sort();
    }

    return moves.slice(0, maxMoves);
  }, [legalMoves, maxMoves, sortAlphabetically, filterByPiece]);

  const availableMoves = legalMoves.length;
  const actualMaxMoves = availableMoves;

  const getMoveTypeColor = (move: string) => {
    if (move === "O-O" || move === "O-O-O") return "#e91e63"; // Pink for castling
    if (move.includes("+")) return "#ff5722"; // Orange for check
    if (move.includes("#")) return "#f44336"; // Red for checkmate
    if (move.includes("x")) return "#ff9800"; // Amber for capture
    return "#d3d3d3ff"; // Green for pawn moves
  };

  const getPieceIcon = (move: string) => {
    if (move === "O-O" || move === "O-O-O") return "♔";
    if (move.startsWith("N")) return "♘";
    if (move.startsWith("B")) return "♗";
    if (move.startsWith("R")) return "♖";
    if (move.startsWith("Q")) return "♕";
    if (move.startsWith("K")) return "♔";
    return "♙"; // Pawn
  };

  // Show disabled state
  if (!legalMovesEnabled) {
    return (
      <Paper
        sx={{
          p: 2,
          backgroundColor: "#1a1a1a",
          borderRadius: 2,
        }}
      >
        <Stack direction="row" alignItems="center" spacing={2}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
            <Box
              sx={{
                width: 8,
                height: 8,
                borderRadius: "50%",
                backgroundColor: "grey.600",
              }}
            />
            <Typography variant="subtitle2" sx={{ color: "grey.400", fontWeight: 600 }}>
              Legal Moves Off
            </Typography>
          </Box>
          <Switch
            checked={legalMovesEnabled}
            onChange={handleLegalMovesToggle}
            sx={{
              '& .MuiSwitch-switchBase.Mui-checked': {
                color: '#9c27b0',
              },
              '& .MuiSwitch-switchBase.Mui-checked + .MuiSwitch-track': {
                backgroundColor: '#9c27b0',
              },
            }}
          />
          <Box sx={{ flexGrow: 1 }} />
          <IconButton
            onClick={() => setSettingsOpen(true)}
            sx={{ color: "grey.400", p: 0.5 }}
            size="small"
          >
            <SettingsIcon fontSize="small" />
          </IconButton>
        </Stack>

        {/* Settings Dialog */}
        <Dialog
          open={settingsOpen}
          onClose={handleSettingsClose}
          PaperProps={{
            sx: {
              backgroundColor: "#1a1a1a",
              color: "white",
              minWidth: 400
            }
          }}
        >
          <DialogTitle>Legal Moves Settings</DialogTitle>
          <DialogContent>
            <Stack spacing={3} sx={{ pt: 1 }}>
              <Box>
                <Typography variant="body2" sx={{ color: "grey.300", mb: 1 }}>
                  Max Moves to Display: {maxMoves}
                </Typography>
                <Typography variant="caption" sx={{ color: "grey.400", mb: 2, display: "block" }}>
                  Set how many legal moves to show
                </Typography>
                <Box sx={{ px: 1 }}>
                  <input
                    type="range"
                    min={1}
                    max={Math.max(actualMaxMoves, 1)}
                    value={Math.min(maxMoves, actualMaxMoves)}
                    onChange={(e) => setMaxMoves(Number(e.target.value))}
                    style={{
                      width: '100%',
                      accentColor: '#4caf50'
                    }}
                  />
                </Box>
              </Box>
            </Stack>
          </DialogContent>
          <DialogActions>
            <Button onClick={handleSettingsClose} sx={{ color: "#4caf50" }}>
              Done
            </Button>
          </DialogActions>
        </Dialog>
      </Paper>
    );
  }

  // Show no moves state
  if (!legalMoves || legalMoves.length === 0) {
    return (
      <Box>
        {/* Header */}
        <Paper
          sx={{
            p: 2,
            backgroundColor: "#1a1a1a",
            borderRadius: 2,
            mb: 2
          }}
        >
          <Stack direction="row" alignItems="center" spacing={2}>
            <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
              <Box
                sx={{
                  width: 8,
                  height: 8,
                  borderRadius: "50%",
                  backgroundColor: "#9c27b0",
                }}
              />
              <Typography variant="subtitle2" sx={{ color: "white", fontWeight: 600 }}>
                Legal Moves On
              </Typography>
            </Box>
            <Switch
              checked={legalMovesEnabled}
              onChange={handleLegalMovesToggle}
              sx={{
                '& .MuiSwitch-switchBase.Mui-checked': {
                  color: '#9c27b0',
                },
                '& .MuiSwitch-switchBase.Mui-checked + .MuiSwitch-track': {
                  backgroundColor: '#9c27b0',
                },
              }}
            />
            <Box sx={{ flexGrow: 1 }} />
            <IconButton
              onClick={() => setSettingsOpen(true)}
              sx={{ color: "white", p: 0.5 }}
              size="small"
            >
              <SettingsIcon fontSize="small" />
            </IconButton>
          </Stack>
        </Paper>

        {/* No Moves State */}
        <Box sx={{ display: "flex", justifyContent: "center", py: 4 }}>
          <Typography variant="body2" sx={{ color: "grey.400", textAlign: "center" }}>
            No legal moves available.
          </Typography>
        </Box>
      </Box>
    );
  }

  return (
    <Box>
      {/* Header */}
      <Paper
        sx={{
          p: 2,
          backgroundColor: "#1a1a1a",
          borderRadius: 2,
          mb: 2
        }}
      >
        <Stack direction="row" alignItems="center" spacing={2} sx={{ mb: 2 }}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
            <Box
              sx={{
                width: 8,
                height: 8,
                borderRadius: "50%",
                backgroundColor: "#9c27b0",
              }}
            />
            <Typography variant="subtitle2" sx={{ color: "white", fontWeight: 600 }}>
              Legal Moves On
            </Typography>
          </Box>
          <Switch
            checked={legalMovesEnabled}
            onChange={handleLegalMovesToggle}
            sx={{
              '& .MuiSwitch-switchBase.Mui-checked': {
                color: '#9c27b0',
              },
              '& .MuiSwitch-switchBase.Mui-checked + .MuiSwitch-track': {
                backgroundColor: '#9c27b0',
              },
            }}
          />
          <Box sx={{ flexGrow: 1 }} />
          <IconButton
            onClick={() => setSettingsOpen(true)}
            sx={{ color: "white", p: 0.5 }}
            size="small"
          >
            <SettingsIcon fontSize="small" />
          </IconButton>
        </Stack>

        {/* Move Count Info */}
        <Stack direction="row" alignItems="center" spacing={2} sx={{ mb: 2 }}>
          <Typography variant="body2" sx={{ color: "white", fontWeight: 500 }}>
            Available Legal Moves
          </Typography>
          <Chip 
            label={`${processedMoves.length}`} 
            size="small" 
            sx={{ 
              backgroundColor: "rgba(76, 175, 80, 0.2)", 
              color: "#4caf50",
              fontSize: "0.7rem",
              fontWeight: 600
            }} 
          />
          <Typography variant="body2" sx={{ color: "white", fontWeight: 500 }}>
            {filterByPiece !== "all" ? `${filterByPiece} moves` : "total moves"}
          </Typography>
        </Stack>

        {/* Column Headers */}
        <Stack direction="row" spacing={2} sx={{ mb: 1 }}>
          <Typography variant="caption" sx={{ color: "grey.400", minWidth: "40px" }}>
            #
          </Typography>
          <Typography variant="caption" sx={{ color: "grey.400", minWidth: "40px" }}>
            Piece
          </Typography>
          <Typography variant="caption" sx={{ color: "grey.400", flex: 1 }}>
            Move
          </Typography>
          <Typography variant="caption" sx={{ color: "grey.400", minWidth: "80px" }}>
            Type
          </Typography>
        </Stack>
      </Paper>

      {/* Moves List */}
      <Stack spacing={0}>
        {processedMoves.map((move, index) => (
          <Paper
            key={`${move}-${index}`}
            onClick={() => !disabled && handleFutureMoveLegalClick(move)}
            sx={{
              p: 2,
              backgroundColor: "#1a1a1a",
              borderRadius: 0,
              borderBottom: index < processedMoves.length - 1 ? "1px solid rgba(255,255,255,0.1)" : "none",
              borderLeft: "3px solid transparent",
              cursor: disabled ? "not-allowed" : "pointer",
              transition: "background-color 0.2s ease",
              "&:hover": {
                backgroundColor: disabled ? "#1a1a1a" : "rgba(76, 175, 80, 0.1)",
                borderLeft: disabled ? "3px solid transparent" : "3px solid #4caf50",
              },
              filter: disabled ? "grayscale(50%)" : "none",
            }}
          >
            <Stack direction="row" alignItems="center" spacing={2}>
              {/* Index */}
              <Typography
                variant="body2"
                sx={{
                  color: "grey.400",
                  minWidth: "40px",
                  fontFamily: "monospace",
                  fontSize: "0.8rem"
                }}
              >
                {index + 1}
              </Typography>

              {/* Piece Icon */}
              <Typography
                variant="body2"
                sx={{
                  color: getMoveTypeColor(move),
                  minWidth: "40px",
                  fontSize: "1.2rem",
                  textAlign: "center"
                }}
              >
                {getPieceIcon(move)}
              </Typography>

              {/* Move */}
              <Typography
                variant="body2"
                sx={{
                  color: "grey.400",
                  fontWeight: "bold",
                  fontFamily: "monospace",
                  fontSize: "0.9rem",
                  flex: 1
                }}
              >
                {move}
              </Typography>

              {/* Move Type */}
              <Typography
                variant="body2"
                sx={{
                  color: getMoveTypeColor(move),
                  minWidth: "80px",
                  fontFamily: "monospace",
                  fontSize: "0.8rem",
                  fontWeight: 500
                }}
              >
                {move === "O-O" || move === "O-O-O" ? "Castle" :
                 move.includes("#") ? "Checkmate" :
                 move.includes("+") ? "Check" :
                 move.includes("x") ? "Capture" :
                 move.match(/^[NBRQK]/) ? "Piece" : "Pawn"}
              </Typography>
            </Stack>
          </Paper>
        ))}
      </Stack>

      {/* Footer Info */}
      <Paper
        sx={{
          p: 1.5,
          backgroundColor: "#1a1a1a",
          borderRadius: 0,
          mt: 0
        }}
      >
        <Stack direction="row" justifyContent="space-between" alignItems="center">
          <Stack direction="row" alignItems="center" spacing={1}>
            <Gavel fontSize="small" sx={{ color: "#4caf50" }} />
            <Typography variant="caption" sx={{ color: "grey.400" }}>
              Legal Moves Available
            </Typography>
          </Stack>
          <Typography variant="caption" sx={{ color: "grey.400" }}>
            Showing {processedMoves.length} of {legalMoves.length} moves
          </Typography>
        </Stack>
      </Paper>

      {/* Settings Dialog */}
      <Dialog
        open={settingsOpen}
        onClose={handleSettingsClose}
        PaperProps={{
          sx: {
            backgroundColor: "#1a1a1a",
            color: "white",
            minWidth: 400
          }
        }}
      >
        <DialogTitle>Legal Moves Settings</DialogTitle>
        <DialogContent>
          <Stack spacing={3} sx={{ pt: 1 }}>
            <Box>
              <Typography variant="body2" sx={{ color: "grey.300", mb: 1 }}>
                Max Moves to Display: {Math.min(maxMoves, actualMaxMoves)}
              </Typography>
              <Typography variant="caption" sx={{ color: "grey.400", mb: 1, display: "block" }}>
                Available moves in this position: {actualMaxMoves}
              </Typography>
              <Typography variant="caption" sx={{ color: "grey.400", mb: 2, display: "block" }}>
                Set how many legal moves to show
              </Typography>
              <Box sx={{ px: 1 }}>
                <input
                  type="range"
                  min={1}
                  max={Math.max(actualMaxMoves, 1)}
                  value={Math.min(maxMoves, actualMaxMoves)}
                  onChange={(e) => setMaxMoves(Number(e.target.value))}
                  style={{
                    width: '100%',
                    accentColor: '#9c27b0'
                  }}
                />
              </Box>
            </Box>

            <Box>
              <Typography variant="body2" sx={{ color: "grey.300", mb: 1 }}>
                Sort Options
              </Typography>
              <Stack direction="row" justifyContent="space-between" alignItems="center">
                <Typography variant="body2" sx={{ color: "grey.300" }}>
                  Sort Alphabetically
                </Typography>
                <Switch
                  checked={sortAlphabetically}
                  onChange={(e) => setSortAlphabetically(e.target.checked)}
                  sx={{
                    '& .MuiSwitch-switchBase.Mui-checked': {
                      color: '#9c27b0',
                    },
                    '& .MuiSwitch-switchBase.Mui-checked + .MuiSwitch-track': {
                      backgroundColor: '#9c27b0',
                    },
                  }}
                />
              </Stack>
            </Box>

            <Box>
              <Typography variant="body2" sx={{ color: "grey.300", mb: 2 }}>
                Filter by Piece Type
              </Typography>
              <Stack direction="row" flexWrap="wrap" gap={1}>
                {["all", "pawn", "knight", "bishop", "rook", "queen", "king", "castle"].map((piece) => (
                  <Chip
                    key={piece}
                    label={piece.charAt(0).toUpperCase() + piece.slice(1)}
                    variant={filterByPiece === piece ? "filled" : "outlined"}
                    onClick={() => setFilterByPiece(piece)}
                    sx={{
                      backgroundColor: filterByPiece === piece ? "#4caf50" : "transparent",
                      borderColor: "#4caf50",
                      color: filterByPiece === piece ? "white" : "#4caf50",
                      "&:hover": {
                        backgroundColor: filterByPiece === piece ? "#388e3c" : "rgba(76, 175, 80, 0.1)",
                      },
                      fontSize: "0.7rem"
                    }}
                    size="small"
                  />
                ))}
              </Stack>
            </Box>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleSettingsClose} sx={{ color: "#4caf50" }}>
            Done
          </Button>
        </DialogActions>
      </Dialog>

      {/* Hint */}
      <Box sx={{ mt: 2 }}>
        <Typography
          variant="caption"
          sx={{ color: "grey.500", fontStyle: "italic" }}
        >
          💡 Click on any legal move to get AI analysis of the move
        </Typography>
      </Box>
    </Box>
  );
}

export default LegalMoveTab;