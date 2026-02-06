import React, { useState, useMemo, useCallback } from "react";
import {
  Box,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  TextField,
  Typography,
  TableSortLabel,
  TablePagination,
  Tooltip,
  IconButton,
} from "@mui/material";
import { debounce } from "lodash";
import { Info as InfoIcon } from "@mui/icons-material";
import { purpleTheme } from "@/theme/theme";

export interface GameMetadata {
  index: number;
  year: string;
  white: string;
  whiteElo: string;
  black: string;
  blackElo: string;
  result: string;
  eco: string;
  date: string;
  time: string; // UTCTime for sorting games on same day
  pgn: string;
}

interface GamesDatabaseProps {
  games: GameMetadata[];
  onGameSelect: (game: GameMetadata) => void;
}

type SortField = "year" | "white" | "whiteElo" | "black" | "blackElo" | "result" | "eco" | "date";
type SortDirection = "asc" | "desc";

const GamesDatabase: React.FC<GamesDatabaseProps> = ({ games, onGameSelect }) => {
  // Filter states
  const [yearFilter, setYearFilter] = useState("");
  const [whiteFilter, setWhiteFilter] = useState("");
  const [blackFilter, setBlackFilter] = useState("");
  const [resultFilter, setResultFilter] = useState("");
  const [ecoFilter, setEcoFilter] = useState("");

  // Debounced filter states (actual values used for filtering)
  const [debouncedYearFilter, setDebouncedYearFilter] = useState("");
  const [debouncedWhiteFilter, setDebouncedWhiteFilter] = useState("");
  const [debouncedBlackFilter, setDebouncedBlackFilter] = useState("");
  const [debouncedResultFilter, setDebouncedResultFilter] = useState("");
  const [debouncedEcoFilter, setDebouncedEcoFilter] = useState("");

  // Pagination states
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(50);

  // Sort states - default sort by year/date (most recent first)
  const [sortField, setSortField] = useState<SortField>("year");
  const [sortDirection, setSortDirection] = useState<SortDirection>("desc");

  // Debounced filter setters (300ms delay)
  const debouncedSetYearFilter = useMemo(
    () => debounce((value: string) => setDebouncedYearFilter(value), 300),
    []
  );
  const debouncedSetWhiteFilter = useMemo(
    () => debounce((value: string) => setDebouncedWhiteFilter(value), 300),
    []
  );
  const debouncedSetBlackFilter = useMemo(
    () => debounce((value: string) => setDebouncedBlackFilter(value), 300),
    []
  );
  const debouncedSetResultFilter = useMemo(
    () => debounce((value: string) => setDebouncedResultFilter(value), 300),
    []
  );
  const debouncedSetEcoFilter = useMemo(
    () => debounce((value: string) => setDebouncedEcoFilter(value), 300),
    []
  );

  // Handle sort
  const handleSort = (field: SortField) => {
    console.log(`[Sort] Clicked field: ${field}, current: ${sortField}, direction: ${sortDirection}`);

    if (sortField === field) {
      const newDirection = sortDirection === "asc" ? "desc" : "asc";
      setSortDirection(newDirection);
      console.log(`[Sort] Toggling direction to: ${newDirection}`);
    } else {
      setSortField(field);
      // For Elo columns, default to descending (highest first)
      // For other columns, default to ascending
      const defaultDirection = (field === "whiteElo" || field === "blackElo") ? "desc" : "asc";
      setSortDirection(defaultDirection);
      console.log(`[Sort] Changing field to: ${field}, direction: ${defaultDirection}`);
    }
    setPage(0); // Reset to first page when sort changes
  };

  // Handle page change
  const handleChangePage = useCallback((_event: unknown, newPage: number) => {
    setPage(newPage);
  }, []);

  // Handle rows per page change
  const handleChangeRowsPerPage = useCallback((event: React.ChangeEvent<HTMLInputElement>) => {
    setRowsPerPage(parseInt(event.target.value, 10));
    setPage(0); // Reset to first page
  }, []);

  // OPTIMIZED: Pre-lowercase all filter values once
  const filterValues = useMemo(() => ({
    year: debouncedYearFilter.toLowerCase(),
    white: debouncedWhiteFilter.toLowerCase(),
    black: debouncedBlackFilter.toLowerCase(),
    result: debouncedResultFilter,
    eco: debouncedEcoFilter.toLowerCase(),
  }), [debouncedYearFilter, debouncedWhiteFilter, debouncedBlackFilter, debouncedResultFilter, debouncedEcoFilter]);

  // OPTIMIZED: Filtered and sorted games
  const filteredGames = useMemo(() => {
    let filtered = games;

    // Apply filters only if they have values
    if (filterValues.year) {
      filtered = filtered.filter((game) =>
        game.year.toLowerCase().includes(filterValues.year)
      );
    }
    if (filterValues.white) {
      filtered = filtered.filter((game) =>
        game.white.toLowerCase().includes(filterValues.white)
      );
    }
    if (filterValues.black) {
      filtered = filtered.filter((game) =>
        game.black.toLowerCase().includes(filterValues.black)
      );
    }
    if (filterValues.result) {
      filtered = filtered.filter((game) =>
        game.result.includes(filterValues.result)
      );
    }
    if (filterValues.eco) {
      filtered = filtered.filter((game) =>
        game.eco.toLowerCase().includes(filterValues.eco)
      );
    }

    // Sort - Create a new array copy to ensure React detects the change
    const sorted = [...filtered].sort((a, b) => {
      let aValue: string | number = a[sortField];
      let bValue: string | number = b[sortField];

      // Convert elo to numbers for proper sorting
      if (sortField === "whiteElo" || sortField === "blackElo") {
        aValue = parseInt(aValue) || 0;
        bValue = parseInt(bValue) || 0;
      }

      // Convert date to comparable format with time for proper chronological order
      // Combine date (YYYY.MM.DD) + time (HH:MM:SS) for sorting games on the same day
      if (sortField === "date" || sortField === "year") {
        // Create sortable datetime string: "YYYY.MM.DD HH:MM:SS"
        // This format naturally sorts correctly as strings (lexicographic = chronological)
        aValue = `${a.date} ${a.time}`;
        bValue = `${b.date} ${b.time}`;
      }

      if (aValue < bValue) return sortDirection === "asc" ? -1 : 1;
      if (aValue > bValue) return sortDirection === "asc" ? 1 : -1;
      return 0;
    });

    console.log(`[Sort] After sorting by ${sortField} ${sortDirection}:`);
    if (sortField === "whiteElo" || sortField === "blackElo") {
      console.log(`[Sort] First 3 games:`, sorted.slice(0, 3).map(g => ({
        white: g.white, whiteElo: g.whiteElo, black: g.black, blackElo: g.blackElo
      })));
      console.log(`[Sort] Last 3 games:`, sorted.slice(-3).map(g => ({
        white: g.white, whiteElo: g.whiteElo, black: g.black, blackElo: g.blackElo
      })));
    } else {
      console.log(`[Sort] First 3 games:`, sorted.slice(0, 3).map(g => ({ date: g.date, time: g.time, white: g.white })));
      console.log(`[Sort] Last 3 games:`, sorted.slice(-3).map(g => ({ date: g.date, time: g.time, white: g.white })));
    }

    return sorted;
  }, [games, filterValues, sortField, sortDirection]);

  // OPTIMIZED: Paginated games (only render current page)
  const paginatedGames = useMemo(() => {
    const startIndex = page * rowsPerPage;
    return filteredGames.slice(startIndex, startIndex + rowsPerPage);
  }, [filteredGames, page, rowsPerPage]);

  return (
    <Box sx={{ p: 3 }}>
      <Box sx={{ display: "flex", alignItems: "center", mb: 3, gap: 2 }}>
        <Typography
          variant="h5"
          sx={{
            color: purpleTheme.text.primary,
            fontWeight: 600,
          }}
        >
          Games Database
        </Typography>
        <Tooltip title="Performance optimized: Uses pagination and debounced filtering for smooth browsing of large game collections">
          <IconButton size="small">
            <InfoIcon sx={{ color: purpleTheme.accent, fontSize: 20 }} />
          </IconButton>
        </Tooltip>
        <Typography
          variant="body2"
          sx={{
            color: purpleTheme.text.secondary,
            ml: "auto",
          }}
        >
          Showing {paginatedGames.length} of {filteredGames.length} games
          {filteredGames.length !== games.length && ` (filtered from ${games.length} total)`}
        </Typography>
      </Box>

      <TableContainer
        component={Paper}
        sx={{
          backgroundColor: purpleTheme.background.paper,
          maxHeight: "calc(70vh - 100px)",
        }}
      >
        <Table stickyHeader>
          <TableHead>
            <TableRow>
              <TableCell
                sx={{
                  backgroundColor: purpleTheme.background.card,
                  color: purpleTheme.text.primary,
                  fontWeight: 600,
                  minWidth: 100,
                }}
              >
                <TableSortLabel
                  active={sortField === "year"}
                  direction={sortField === "year" ? sortDirection : "asc"}
                  onClick={() => handleSort("year")}
                  sx={{
                    color: `${purpleTheme.text.primary} !important`,
                    "&.Mui-active": {
                      color: `${purpleTheme.accent} !important`,
                    },
                    "& .MuiTableSortLabel-icon": {
                      color: `${purpleTheme.accent} !important`,
                    },
                  }}
                >
                  Year
                </TableSortLabel>
                <TextField
                  size="small"
                  placeholder="Filter..."
                  value={yearFilter}
                  onChange={(e) => {
                    setYearFilter(e.target.value);
                    debouncedSetYearFilter(e.target.value);
                  }}
                  sx={{
                    mt: 1,
                    width: "100%",
                    "& .MuiInputBase-input": {
                      color: purpleTheme.text.primary,
                      fontSize: "0.875rem",
                    },
                    "& .MuiOutlinedInput-root": {
                      "& fieldset": {
                        borderColor: purpleTheme.secondary,
                      },
                      "&:hover fieldset": {
                        borderColor: purpleTheme.accent,
                      },
                    },
                  }}
                />
              </TableCell>

              <TableCell
                sx={{
                  backgroundColor: purpleTheme.background.card,
                  color: purpleTheme.text.primary,
                  fontWeight: 600,
                  minWidth: 150,
                }}
              >
                <TableSortLabel
                  active={sortField === "white"}
                  direction={sortField === "white" ? sortDirection : "asc"}
                  onClick={() => handleSort("white")}
                  sx={{
                    color: `${purpleTheme.text.primary} !important`,
                    "&.Mui-active": {
                      color: `${purpleTheme.accent} !important`,
                    },
                    "& .MuiTableSortLabel-icon": {
                      color: `${purpleTheme.accent} !important`,
                    },
                  }}
                >
                  White
                </TableSortLabel>
                <TextField
                  size="small"
                  placeholder="Filter..."
                  value={whiteFilter}
                  onChange={(e) => {
                    setWhiteFilter(e.target.value);
                    debouncedSetWhiteFilter(e.target.value);
                  }}
                  sx={{
                    mt: 1,
                    width: "100%",
                    "& .MuiInputBase-input": {
                      color: purpleTheme.text.primary,
                      fontSize: "0.875rem",
                    },
                    "& .MuiOutlinedInput-root": {
                      "& fieldset": {
                        borderColor: purpleTheme.secondary,
                      },
                      "&:hover fieldset": {
                        borderColor: purpleTheme.accent,
                      },
                    },
                  }}
                />
              </TableCell>

              <TableCell
                sx={{
                  backgroundColor: purpleTheme.background.card,
                  color: purpleTheme.text.primary,
                  fontWeight: 600,
                  minWidth: 80,
                }}
              >
                <TableSortLabel
                  active={sortField === "whiteElo"}
                  direction={sortField === "whiteElo" ? sortDirection : "asc"}
                  onClick={() => handleSort("whiteElo")}
                  sx={{
                    color: `${purpleTheme.text.primary} !important`,
                    "&.Mui-active": {
                      color: `${purpleTheme.accent} !important`,
                    },
                    "& .MuiTableSortLabel-icon": {
                      color: `${purpleTheme.accent} !important`,
                    },
                  }}
                >
                  Elo
                </TableSortLabel>
              </TableCell>

              <TableCell
                sx={{
                  backgroundColor: purpleTheme.background.card,
                  color: purpleTheme.text.primary,
                  fontWeight: 600,
                  minWidth: 150,
                }}
              >
                <TableSortLabel
                  active={sortField === "black"}
                  direction={sortField === "black" ? sortDirection : "asc"}
                  onClick={() => handleSort("black")}
                  sx={{
                    color: `${purpleTheme.text.primary} !important`,
                    "&.Mui-active": {
                      color: `${purpleTheme.accent} !important`,
                    },
                    "& .MuiTableSortLabel-icon": {
                      color: `${purpleTheme.accent} !important`,
                    },
                  }}
                >
                  Black
                </TableSortLabel>
                <TextField
                  size="small"
                  placeholder="Filter..."
                  value={blackFilter}
                  onChange={(e) => {
                    setBlackFilter(e.target.value);
                    debouncedSetBlackFilter(e.target.value);
                  }}
                  sx={{
                    mt: 1,
                    width: "100%",
                    "& .MuiInputBase-input": {
                      color: purpleTheme.text.primary,
                      fontSize: "0.875rem",
                    },
                    "& .MuiOutlinedInput-root": {
                      "& fieldset": {
                        borderColor: purpleTheme.secondary,
                      },
                      "&:hover fieldset": {
                        borderColor: purpleTheme.accent,
                      },
                    },
                  }}
                />
              </TableCell>

              <TableCell
                sx={{
                  backgroundColor: purpleTheme.background.card,
                  color: purpleTheme.text.primary,
                  fontWeight: 600,
                  minWidth: 80,
                }}
              >
                <TableSortLabel
                  active={sortField === "blackElo"}
                  direction={sortField === "blackElo" ? sortDirection : "asc"}
                  onClick={() => handleSort("blackElo")}
                  sx={{
                    color: `${purpleTheme.text.primary} !important`,
                    "&.Mui-active": {
                      color: `${purpleTheme.accent} !important`,
                    },
                    "& .MuiTableSortLabel-icon": {
                      color: `${purpleTheme.accent} !important`,
                    },
                  }}
                >
                  Elo
                </TableSortLabel>
              </TableCell>

              <TableCell
                sx={{
                  backgroundColor: purpleTheme.background.card,
                  color: purpleTheme.text.primary,
                  fontWeight: 600,
                  minWidth: 100,
                }}
              >
                <TableSortLabel
                  active={sortField === "result"}
                  direction={sortField === "result" ? sortDirection : "asc"}
                  onClick={() => handleSort("result")}
                  sx={{
                    color: `${purpleTheme.text.primary} !important`,
                    "&.Mui-active": {
                      color: `${purpleTheme.accent} !important`,
                    },
                    "& .MuiTableSortLabel-icon": {
                      color: `${purpleTheme.accent} !important`,
                    },
                  }}
                >
                  Result
                </TableSortLabel>
                <TextField
                  size="small"
                  placeholder="Filter..."
                  value={resultFilter}
                  onChange={(e) => {
                    setResultFilter(e.target.value);
                    debouncedSetResultFilter(e.target.value);
                  }}
                  sx={{
                    mt: 1,
                    width: "100%",
                    "& .MuiInputBase-input": {
                      color: purpleTheme.text.primary,
                      fontSize: "0.875rem",
                    },
                    "& .MuiOutlinedInput-root": {
                      "& fieldset": {
                        borderColor: purpleTheme.secondary,
                      },
                      "&:hover fieldset": {
                        borderColor: purpleTheme.accent,
                      },
                    },
                  }}
                />
              </TableCell>

              <TableCell
                sx={{
                  backgroundColor: purpleTheme.background.card,
                  color: purpleTheme.text.primary,
                  fontWeight: 600,
                  minWidth: 100,
                }}
              >
                <TableSortLabel
                  active={sortField === "eco"}
                  direction={sortField === "eco" ? sortDirection : "asc"}
                  onClick={() => handleSort("eco")}
                  sx={{
                    color: `${purpleTheme.text.primary} !important`,
                    "&.Mui-active": {
                      color: `${purpleTheme.accent} !important`,
                    },
                    "& .MuiTableSortLabel-icon": {
                      color: `${purpleTheme.accent} !important`,
                    },
                  }}
                >
                  ECO
                </TableSortLabel>
                <TextField
                  size="small"
                  placeholder="Filter..."
                  value={ecoFilter}
                  onChange={(e) => {
                    setEcoFilter(e.target.value);
                    debouncedSetEcoFilter(e.target.value);
                  }}
                  sx={{
                    mt: 1,
                    width: "100%",
                    "& .MuiInputBase-input": {
                      color: purpleTheme.text.primary,
                      fontSize: "0.875rem",
                    },
                    "& .MuiOutlinedInput-root": {
                      "& fieldset": {
                        borderColor: purpleTheme.secondary,
                      },
                      "&:hover fieldset": {
                        borderColor: purpleTheme.accent,
                      },
                    },
                  }}
                />
              </TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {paginatedGames.map((game) => (
              <TableRow
                key={game.index}
                onClick={() => onGameSelect(game)}
                sx={{
                  cursor: "pointer",
                  "&:hover": {
                    backgroundColor: `${purpleTheme.accent}20`,
                  },
                  transition: "background-color 0.2s",
                }}
              >
                <TableCell sx={{ color: purpleTheme.text.primary }}>
                  {game.year}
                </TableCell>
                <TableCell sx={{ color: purpleTheme.text.primary }}>
                  {game.white}
                </TableCell>
                <TableCell sx={{ color: purpleTheme.text.secondary }}>
                  {game.whiteElo}
                </TableCell>
                <TableCell sx={{ color: purpleTheme.text.primary }}>
                  {game.black}
                </TableCell>
                <TableCell sx={{ color: purpleTheme.text.secondary }}>
                  {game.blackElo}
                </TableCell>
                <TableCell
                  sx={{
                    color:
                      game.result === "1-0"
                        ? "#4caf50"
                        : game.result === "0-1"
                        ? "#f44336"
                        : purpleTheme.text.secondary,
                    fontWeight: 600,
                  }}
                >
                  {game.result}
                </TableCell>
                <TableCell sx={{ color: purpleTheme.text.accent }}>
                  {game.eco}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>

      <TablePagination
        rowsPerPageOptions={[25, 50, 100, 200]}
        component="div"
        count={filteredGames.length}
        rowsPerPage={rowsPerPage}
        page={page}
        onPageChange={handleChangePage}
        onRowsPerPageChange={handleChangeRowsPerPage}
        sx={{
          color: purpleTheme.text.primary,
          "& .MuiTablePagination-select": {
            color: purpleTheme.text.primary,
          },
          "& .MuiTablePagination-selectIcon": {
            color: purpleTheme.text.primary,
          },
          "& .MuiTablePagination-actions button": {
            color: purpleTheme.text.primary,
          },
        }}
      />
    </Box>
  );
};

export default GamesDatabase;
