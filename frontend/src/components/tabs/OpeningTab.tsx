import React, { useState } from "react";
import {
  Box,
  CircularProgress,
  Typography,
  Stack,
  Paper,
  Chip,
  Link,
  IconButton,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Switch,
  ToggleButton,
  ToggleButtonGroup,
  
} from "@mui/material";
import { Settings as SettingsIcon, TrendingUp } from "@mui/icons-material";
import { MasterGames, Moves } from "../../libs/openingdatabase/helper";

type ExplorerType = 'master' | 'lichess';

interface OpeningExplorerProps {
  openingLoading: boolean;
  lichessOpeningData?: MasterGames | null;
  lichessOpeningLoading?: boolean;
  openingData?: MasterGames | null;
  llmLoading: boolean;
  handleOpeningMoveClick: (move: Moves) => void;
}

export const OpeningExplorer: React.FC<OpeningExplorerProps> = ({
  openingLoading,
  openingData,
  llmLoading,
  lichessOpeningData,
  lichessOpeningLoading,
  handleOpeningMoveClick,
}) => {
  const [explorerType, setExplorerType] = useState<ExplorerType>('master');
  const [explorerEnabled, setExplorerEnabled] = useState(true);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [showTopGames, setShowTopGames] = useState(true);
  const [maxMoves, setMaxMoves] = useState(8);

  const handleExplorerChange = (
    _event: React.MouseEvent<HTMLElement>,
    newExplorerType: ExplorerType,
  ) => {
    if (newExplorerType !== null) {
      setExplorerType(newExplorerType);
    }
  };

  const handleExplorerToggle = (event: React.ChangeEvent<HTMLInputElement>) => {
    setExplorerEnabled(event.target.checked);
  };

  const handleSettingsClose = () => {
    setSettingsOpen(false);
  };

  // Determine which data to use based on explorer type
  const currentData = explorerType === 'master' ? openingData : lichessOpeningData;
  const isLoading = explorerType === 'master' ? openingLoading : lichessOpeningLoading;

  // Show disabled state
  if (!explorerEnabled) {
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
              Opening Explorer Off
            </Typography>
          </Box>
          <Switch
            checked={explorerEnabled}
            onChange={handleExplorerToggle}
            sx={{
              '& .MuiSwitch-switchBase.Mui-checked': {
                color: '#9c27b0"',
              },
              '& .MuiSwitch-switchBase.Mui-checked + .MuiSwitch-track': {
                backgroundColor: '#9c27b0"',
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
          <DialogTitle>Opening Explorer Settings</DialogTitle>
          <DialogContent>
            <Stack spacing={3} sx={{ pt: 1 }}>
              <Box>
                <Typography variant="body2" sx={{ color: "grey.300", mb: 2 }}>
                  Database Source
                </Typography>
                <ToggleButtonGroup
                  value={explorerType}
                  exclusive
                  onChange={handleExplorerChange}
                  size="small"
                  sx={{
                    '& .MuiToggleButton-root': {
                      color: 'grey.300',
                      borderColor: '#444',
                      '&.Mui-selected': {
                        backgroundColor: '#9c27b0"',
                        color: '#000',
                        '&:hover': {
                          backgroundColor: '#9c27b0"',
                        }
                      },
                      '&:hover': {
                        backgroundColor: '#333',
                      }
                    }
                  }}
                >
                  <ToggleButton value="master">Master Games</ToggleButton>
                  <ToggleButton value="lichess">Lichess Games</ToggleButton>
                </ToggleButtonGroup>
              </Box>
              <Box>
                <Typography variant="body2" sx={{ color: "grey.300", mb: 1 }}>
                  Show Top Games
                </Typography>
                <Switch
                  checked={showTopGames}
                  onChange={(e) => setShowTopGames(e.target.checked)}
                  sx={{
                    '& .MuiSwitch-switchBase.Mui-checked': {
                      color: '#9c27b0"',
                    },
                    '& .MuiSwitch-switchBase.Mui-checked + .MuiSwitch-track': {
                      backgroundColor: '#9c27b0"',
                    },
                  }}
                />
              </Box>
            </Stack>
          </DialogContent>
          <DialogActions>
            <Button onClick={handleSettingsClose} sx={{ color: "#9c27b0" }}>
              Done
            </Button>
          </DialogActions>
        </Dialog>
      </Paper>
    );
  }

  // Show loading state when opening is loading OR when no opening data is available
  if (isLoading || !currentData) {
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
                Opening Explorer On
              </Typography>
            </Box>
            <Switch
              checked={explorerEnabled}
              onChange={handleExplorerToggle}
              sx={{
                '& .MuiSwitch-switchBase.Mui-checked': {
                  color: '#00d4aa',
                },
                '& .MuiSwitch-switchBase.Mui-checked + .MuiSwitch-track': {
                  backgroundColor: '#00d4aa',
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

        {/* Loading State */}
        <Box sx={{ display: "flex", justifyContent: "center", py: 4 }}>
          <Stack alignItems="center" spacing={2}>
            <CircularProgress 
              size={40} 
              sx={{ color: "#9c27b0" }} 
            />
            <Typography variant="body2" sx={{ color: "grey.400" }}>
              Loading {explorerType} database...
            </Typography>
          </Stack>
        </Box>

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
          <DialogTitle>Opening Explorer Settings</DialogTitle>
          <DialogContent>
            <Stack spacing={3} sx={{ pt: 1 }}>
              <Box>
                <Typography variant="body2" sx={{ color: "grey.300", mb: 2 }}>
                  Database Source
                </Typography>
                <ToggleButtonGroup
                  value={explorerType}
                  exclusive
                  onChange={handleExplorerChange}
                  size="small"
                  sx={{
                    '& .MuiToggleButton-root': {
                      color: 'grey.300',
                      borderColor: '#444',
                      '&.Mui-selected': {
                        backgroundColor: "#9c27b0",
                        color: '#000',
                        '&:hover': {
                          backgroundColor: "#9c27b0",
                        }
                      },
                      '&:hover': {
                        backgroundColor: '#333',
                      }
                    }
                  }}
                >
                  <ToggleButton value="master">Master Games</ToggleButton>
                  <ToggleButton value="lichess">Lichess Games</ToggleButton>
                </ToggleButtonGroup>
              </Box>
              <Box>
                <Typography variant="body2" sx={{ color: "grey.300", mb: 1 }}>
                  Show Top Games
                </Typography>
                <Switch
                  checked={showTopGames}
                  onChange={(e) => setShowTopGames(e.target.checked)}
                  sx={{
                    '& .MuiSwitch-switchBase.Mui-checked': {
                      color: "#9c27b0",
                    },
                    '& .MuiSwitch-switchBase.Mui-checked + .MuiSwitch-track': {
                      backgroundColor: "#9c27b0",
                    },
                  }}
                />
              </Box>
            </Stack>
          </DialogContent>
          <DialogActions>
            <Button onClick={handleSettingsClose} sx={{ color: "#9c27b0" }}>
              Done
            </Button>
          </DialogActions>
        </Dialog>
      </Box>
    );
  }

  const totalGames = (currentData.white ?? 0) + (currentData.draws ?? 0) + (currentData.black ?? 0);

  if (totalGames === 0) {
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
                Opening Explorer On
              </Typography>
            </Box>
            <Switch
              checked={explorerEnabled}
              onChange={handleExplorerToggle}
              sx={{
                '& .MuiSwitch-switchBase.Mui-checked': {
                  color: "#9c27b0",
                },
                '& .MuiSwitch-switchBase.Mui-checked + .MuiSwitch-track': {
                  backgroundColor: "#9c27b0",
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

        {/* No Data State */}
        <Box sx={{ display: "flex", justifyContent: "center", py: 4 }}>
          <Typography variant="body2" sx={{ color: "grey.400", textAlign: "center" }}>
            No {explorerType} games found for this position.
          </Typography>
        </Box>
      </Box>
    );
  }

  const whiteWinRate = ((currentData.white / totalGames) * 100).toFixed(1);
  const drawRate = ((currentData.draws / totalGames) * 100).toFixed(1);
  const blackWinRate = ((currentData.black / totalGames) * 100).toFixed(1);

  // Helper function to render result bar
  const renderResultBar = (move: Moves, moveTotal: number) => {
    const whitePercent = (move.white / moveTotal) * 100;
    const drawPercent = (move.draws / moveTotal) * 100;
    const blackPercent = (move.black / moveTotal) * 100;

    return (
      <Box sx={{ display: 'flex', width: '100%', height: 20, borderRadius: 1, overflow: 'hidden' }}>
        <Box
          sx={{
            width: `${whitePercent}%`,
            backgroundColor: '#f0f0f0',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            minWidth: whitePercent > 20 ? 'auto' : 0,
          }}
        >
          {whitePercent > 20 && (
            <Typography variant="caption" sx={{ color: '#333', fontWeight: 'bold', fontSize: '0.7rem' }}>
              {whitePercent.toFixed(0)}%
            </Typography>
          )}
        </Box>
        <Box
          sx={{
            width: `${drawPercent}%`,
            backgroundColor: '#888',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            minWidth: drawPercent > 20 ? 'auto' : 0,
          }}
        >
          {drawPercent > 20 && (
            <Typography variant="caption" sx={{ color: 'white', fontWeight: 'bold', fontSize: '0.7rem' }}>
              {drawPercent.toFixed(0)}%
            </Typography>
          )}
        </Box>
        <Box
          sx={{
            width: `${blackPercent}%`,
            backgroundColor: '#000',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            minWidth: blackPercent > 20 ? 'auto' : 0,
          }}
        >
          {blackPercent > 20 && (
            <Typography variant="caption" sx={{ color: 'white', fontWeight: 'bold', fontSize: '0.7rem' }}>
              {blackPercent.toFixed(0)}%
            </Typography>
          )}
        </Box>
      </Box>
    );
  };

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
              Opening Explorer On
            </Typography>
          </Box>
          <Switch
            checked={explorerEnabled}
            onChange={handleExplorerToggle}
            sx={{
              '& .MuiSwitch-switchBase.Mui-checked': {
                color: "#9c27b0",
              },
              '& .MuiSwitch-switchBase.Mui-checked + .MuiSwitch-track': {
                backgroundColor: "#9c27b0",
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

        {/* Database Info */}
        <Stack direction="row" alignItems="center" spacing={2} sx={{ mb: 2 }}>
          <Typography variant="body2" sx={{ color: "white", fontWeight: 500 }}>
            {explorerType === 'master' ? 'Master Database' : 'Lichess Database'}
          </Typography>
          <Chip 
            label={totalGames.toLocaleString()} 
            size="small" 
            sx={{ 
              backgroundColor: "rgba(255,255,255,0.1)", 
              color: "white",
              fontSize: "0.7rem"
            }} 
          />
          <Typography variant="caption" sx={{ color: "grey.400" }}>
            games
          </Typography>
        </Stack>

        {/* Opening Name */}
        {currentData.opening && (
          <Stack direction="row" alignItems="center" spacing={2}>
            <Typography variant="body2" sx={{ color: "white", fontWeight: 500 }}>
              {currentData.opening.name}
            </Typography>
            <Chip 
              label={currentData.opening.eco} 
              size="small" 
              sx={{ 
                backgroundColor: "#00d4aa", 
                color: "#000",
                fontSize: "0.7rem",
                fontWeight: 600
              }} 
            />
          </Stack>
        )}

        {/* Column Headers */}
        <Stack direction="row" spacing={2} sx={{ mt: 2, mb: 1 }}>
          <Typography variant="caption" sx={{ color: "grey.400", minWidth: "80px" }}>
            Move
          </Typography>
          <Typography variant="caption" sx={{ color: "grey.400", minWidth: "60px" }}>
            Games
          </Typography>
          <Typography variant="caption" sx={{ color: "grey.400", minWidth: "40px" }}>
            %
          </Typography>
          <Typography variant="caption" sx={{ color: "grey.400", flex: 1 }}>
            Results
          </Typography>
        </Stack>
      </Paper>

      {/* Moves List */}
      <Stack spacing={0}>
        {currentData.moves && currentData.moves.slice(0, maxMoves).map((move, index) => {
          const moveTotal = (move.white ?? 0) + (move.draws ?? 0) + (move.black ?? 0);
          const playedPercentage = ((moveTotal / totalGames) * 100).toFixed(1);

          return (
            <Paper
              key={`${move.uci}-${index}`}
              onClick={() => handleOpeningMoveClick(move)}
              sx={{
                p: 2,
                backgroundColor: "#1a1a1a",
                borderRadius: 0,
                borderBottom: index < currentData.moves.slice(0, maxMoves).length - 1 ? "1px solid rgba(255,255,255,0.1)" : "none",
                cursor: llmLoading ? "not-allowed" : "pointer",
                transition: "background-color 0.2s ease",
                "&:hover": {
                  backgroundColor: llmLoading ? "#1a1a1a" : "#2a2a2a",
                },
                filter: llmLoading ? "grayscale(50%)" : "none",
              }}
            >
              <Stack direction="row" alignItems="center" spacing={2}>
                {/* Move */}
                <Typography
                  variant="body2"
                  sx={{
                    color: "#00d4aa",
                    fontWeight: "bold",
                    minWidth: "80px",
                    fontFamily: "monospace",
                    fontSize: "0.9rem"
                  }}
                >
                  {move.san}
                </Typography>

                {/* Games Count */}
                <Typography
                  variant="body2"
                  sx={{
                    color: "grey.300",
                    minWidth: "60px",
                    fontFamily: "monospace",
                    fontSize: "0.85rem"
                  }}
                >
                  {moveTotal.toLocaleString()}
                </Typography>

                {/* Percentage */}
                <Typography
                  variant="body2"
                  sx={{
                    color: "grey.300",
                    minWidth: "40px",
                    fontFamily: "monospace",
                    fontSize: "0.85rem"
                  }}
                >
                  {playedPercentage}%
                </Typography>

                {/* Result Bar */}
                <Box sx={{ flex: 1 }}>
                  {renderResultBar(move, moveTotal)}
                </Box>
              </Stack>
            </Paper>
          );
        })}

        {/* Total Summary */}
        <Paper
          sx={{
            p: 2,
            backgroundColor: "#1a1a1a",
            borderTop: "2px solid rgba(255,255,255,0.2)",
            borderRadius: 0,
          }}
        >
          <Stack direction="row" alignItems="center" spacing={2}>
            <Typography
              variant="body2"
              sx={{
                color: "white",
                fontWeight: "bold",
                minWidth: "80px",
                fontSize: "0.9rem"
              }}
            >
              Total
            </Typography>
            <Typography
              variant="body2"
              sx={{
                color: "white",
                fontWeight: "bold",
                minWidth: "60px",
                fontFamily: "monospace",
                fontSize: "0.85rem"
              }}
            >
              {totalGames.toLocaleString()}
            </Typography>
            <Typography
              variant="body2"
              sx={{
                color: "white",
                fontWeight: "bold",
                minWidth: "40px",
                fontSize: "0.85rem"
              }}
            >
              100%
            </Typography>
            <Box sx={{ flex: 1 }}>
              <Box sx={{ display: 'flex', width: '100%', height: 20, borderRadius: 1, overflow: 'hidden' }}>
                <Box
                  sx={{
                    width: `${whiteWinRate}%`,
                    backgroundColor: '#f0f0f0',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}
                >
                  <Typography variant="caption" sx={{ color: '#333', fontWeight: 'bold', fontSize: '0.7rem' }}>
                    {whiteWinRate}%
                  </Typography>
                </Box>
                <Box
                  sx={{
                    width: `${drawRate}%`,
                    backgroundColor: '#888',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}
                >
                  <Typography variant="caption" sx={{ color: 'white', fontWeight: 'bold', fontSize: '0.7rem' }}>
                    {drawRate}%
                  </Typography>
                </Box>
                <Box
                  sx={{
                    width: `${blackWinRate}%`,
                    backgroundColor: '#000',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}
                >
                  <Typography variant="caption" sx={{ color: 'white', fontWeight: 'bold', fontSize: '0.7rem' }}>
                    {blackWinRate}%
                  </Typography>
                </Box>
              </Box>
            </Box>
          </Stack>
        </Paper>
      </Stack>

      {/* Top Games */}
      {showTopGames && currentData.topGames && currentData.topGames.length > 0 && (
        <Paper
          sx={{
            p: 2,
            backgroundColor: "#1a1a1a",
            borderRadius: 2,
            mt: 2
          }}
        >
          <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 2 }}>
            <TrendingUp fontSize="small" sx={{ color: "#00d4aa" }} />
            <Typography variant="subtitle2" sx={{ color: "white", fontWeight: 600 }}>
              Notable Games
            </Typography>
          </Stack>
          <Stack spacing={1}>
            {currentData.topGames.slice(0, 3).map((game, index) => (
              <Box
                key={`${game.id}-${index}`}
                sx={{
                  p: 1.5,
                  backgroundColor: "rgba(255,255,255,0.05)",
                  borderRadius: 1,
                  borderLeft: "3px solid #00d4aa"
                }}
              >
                <Stack direction="row" justifyContent="space-between" alignItems="center">
                  <Box>
                    <Typography variant="body2" sx={{ color: "white", fontSize: "0.85rem" }}>
                      {game.white?.name} ({game.white?.rating}) vs {game.black?.name} ({game.black?.rating})
                    </Typography>
                    <Typography variant="caption" sx={{ color: "grey.400" }}>
                      {game.month} {game.year}
                    </Typography>
                  </Box>
                  <Link
                    href={`https://lichess.org/${game.id}`}
                    target="_blank"
                    rel="noopener"
                    sx={{ 
                      color: "#00d4aa", 
                      textDecoration: "none",
                      fontSize: "0.8rem",
                      "&:hover": {
                        textDecoration: "underline"
                      }
                    }}
                  >
                    View
                  </Link>
                </Stack>
              </Box>
            ))}
          </Stack>
        </Paper>
      )}

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
        <DialogTitle>Opening Explorer Settings</DialogTitle>
        <DialogContent>
          <Stack spacing={3} sx={{ pt: 1 }}>
            <Box>
              <Typography variant="body2" sx={{ color: "grey.300", mb: 2 }}>
                Database Source
              </Typography>
              <ToggleButtonGroup
                value={explorerType}
                exclusive
                onChange={handleExplorerChange}
                size="small"
                sx={{
                  '& .MuiToggleButton-root': {
                    color: 'grey.300',
                    borderColor: '#444',
                    '&.Mui-selected': {
                      backgroundColor: "#9c27b0",
                      color: '#000',
                      '&:hover': {
                        backgroundColor: "#9c27b0",
                      }
                    },
                    '&:hover': {
                      backgroundColor: '#333',
                    }
                  }
                }}
              >
                <ToggleButton value="master">Master Games</ToggleButton>
                <ToggleButton value="lichess">Lichess Games</ToggleButton>
              </ToggleButtonGroup>
            </Box>
            <Box>
              <Typography variant="body2" sx={{ color: "grey.300", mb: 1 }}>
                Show Top Games
              </Typography>
              <Typography variant="caption" sx={{ color: "grey.400", mb: 2, display: "block" }}>
                Display notable games from this position
              </Typography>
              <Switch
                checked={showTopGames}
                onChange={(e) => setShowTopGames(e.target.checked)}
                sx={{
                  '& .MuiSwitch-switchBase.Mui-checked': {
                    color: "#9c27b0",
                  },
                  '& .MuiSwitch-switchBase.Mui-checked + .MuiSwitch-track': {
                    backgroundColor: "#9c27b0",
                  },
                }}
              />
            </Box>
            <Box>
              <Typography variant="body2" sx={{ color: "grey.300", mb: 1 }}>
                Max Moves to Display: {maxMoves}
              </Typography>
              <Typography variant="caption" sx={{ color: "grey.400", mb: 2, display: "block" }}>
                Number of candidate moves to show
              </Typography>
              <Box sx={{ px: 1 }}>
                <input
                  type="range"
                  min={5}
                  max={12}
                  value={maxMoves}
                  onChange={(e) => setMaxMoves(Number(e.target.value))}
                  style={{
                    width: '100%',
                    accentColor: "#9c27b0"
                  }}
                />
              </Box>
            </Box>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleSettingsClose} sx={{ color: "#00d4aa" }}>
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
          💡 Click on any move above to get AI analysis of that continuation
        </Typography>
      </Box>
    </Box>
  );
};

export default OpeningExplorer;