"use client";

import React, { useState } from "react";
import {
  Box,
  Button,
  TextField,
  FormControl,
  FormLabel,
  FormGroup,
  FormControlLabel,
  Checkbox,
  Radio,
  RadioGroup,
  Typography,
  Paper,
  CircularProgress,
  LinearProgress,
  Alert,
} from "@mui/material";
import DownloadIcon from "@mui/icons-material/Download";
import { purpleTheme } from "@/theme/theme";
import {
  GameFilters,
  DEFAULT_FILTERS,
  Platform,
  DownloadProgress,
  filterGames,
  generatePGN,
  downloadPGNFile,
} from "./GameDownloaderTypes";
import { fetchUserArchives } from "../chessdotcom/ChessDotComTypes";

interface GameDownloaderProps {
  onGamesLoaded?: (pgn: string) => void;
}

const GameDownloader: React.FC<GameDownloaderProps> = ({ onGamesLoaded }) => {
  const [filters, setFilters] = useState<GameFilters>(DEFAULT_FILTERS);
  const [progress, setProgress] = useState<DownloadProgress>({
    currentMonth: "",
    totalGames: 0,
    processedGames: 0,
    percentage: 0,
    status: "idle",
  });

  const handlePlatformChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    setFilters({ ...filters, platform: event.target.value as Platform });
  };

  const handleUsernameChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    setFilters({ ...filters, username: event.target.value });
  };

  const handleDownloadAllChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    setFilters({ ...filters, downloadAll: event.target.value === "all" });
  };

  const handleCheckboxChange = (field: keyof GameFilters) => (
    event: React.ChangeEvent<HTMLInputElement>
  ) => {
    setFilters({ ...filters, [field]: event.target.checked });
  };

  const handleDateFilterChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    setFilters({
      ...filters,
      dateFilterType: event.target.value as "all" | "past18months" | "between",
    });
  };

  const handleDateChange = (field: "startDate" | "endDate") => (
    event: React.ChangeEvent<HTMLInputElement>
  ) => {
    setFilters({ ...filters, [field]: event.target.value });
  };

  const fetchChessDotComGames = async (): Promise<any[]> => {
    const archives = await fetchUserArchives(filters.username);
    let allGames: any[] = [];

    setProgress({
      ...progress,
      status: "downloading",
      totalGames: archives.length,
    });

    for (let i = 0; i < archives.length; i++) {
      const archiveUrl = archives[i];
      const response = await fetch(archiveUrl);
      const data = await response.json();

      allGames = [...allGames, ...data.games];

      setProgress({
        currentMonth: archiveUrl.split("/").slice(-2).join("/"),
        totalGames: archives.length,
        processedGames: i + 1,
        percentage: Math.round(((i + 1) / archives.length) * 100),
        status: "downloading",
      });
    }

    return allGames;
  };

  const fetchLichessGames = async (): Promise<any[]> => {
    setProgress({
      ...progress,
      status: "downloading",
    });

    const params = new URLSearchParams({
      pgnInJson: "true",
      sort: "dateDesc",
      max: filters.downloadAll ? "10000" : "1000",
    });

    const response = await fetch(
      `https://lichess.org/api/games/user/${filters.username}?${params}`,
      {
        headers: {
          Accept: "application/x-ndjson",
        },
      }
    );

    const text = await response.text();
    const games = text
      .trim()
      .split("\n")
      .filter((line) => line)
      .map((line) => JSON.parse(line));

    return games;
  };

  const handleDownload = async () => {
    if (!filters.username.trim()) {
      setProgress({
        ...progress,
        status: "error",
        errorMessage: "Please enter a username",
      });
      return;
    }

    try {
      setProgress({
        currentMonth: "",
        totalGames: 0,
        processedGames: 0,
        percentage: 0,
        status: "downloading",
      });

      // Fetch games based on platform
      let games: any[] = [];
      if (filters.platform === "chessdotcom") {
        games = await fetchChessDotComGames();
      } else {
        games = await fetchLichessGames();
      }

      // Apply filters
      setProgress({ ...progress, status: "processing" });
      const filteredGames = filterGames(games, filters, filters.platform);

      if (filteredGames.length === 0) {
        setProgress({
          ...progress,
          status: "error",
          errorMessage: "No games found matching your filters",
        });
        return;
      }

      // Generate PGN
      const pgn = generatePGN(filteredGames, filters.platform);

      // Download file
      const filename = `${filters.username}_${filters.platform}_${new Date().toISOString().split("T")[0]}.pgn`;
      downloadPGNFile(pgn, filename);

      // Load into Games Database if callback provided
      if (onGamesLoaded) {
        onGamesLoaded(pgn);
      }

      setProgress({
        ...progress,
        status: "complete",
        processedGames: filteredGames.length,
        totalGames: filteredGames.length,
        percentage: 100,
      });
    } catch (error) {
      console.error("Download error:", error);
      setProgress({
        ...progress,
        status: "error",
        errorMessage: error instanceof Error ? error.message : "Download failed",
      });
    }
  };

  return (
    <Paper
      sx={{
        p: 3,
        backgroundColor: purpleTheme.background.card,
        border: `1px solid ${purpleTheme.secondary}`,
        borderRadius: 2,
      }}
    >
      <Typography
        variant="h5"
        sx={{
          color: purpleTheme.text.primary,
          fontWeight: "bold",
          mb: 3,
        }}
      >
        Download Chess Games
      </Typography>

      {/* Platform Selection */}
      <FormControl component="fieldset" sx={{ mb: 3, width: "100%" }}>
        <FormLabel
          sx={{
            color: purpleTheme.text.primary,
            fontWeight: "bold",
            mb: 1,
          }}
        >
          Platform
        </FormLabel>
        <RadioGroup
          row
          value={filters.platform}
          onChange={handlePlatformChange}
        >
          <FormControlLabel
            value="lichess"
            control={
              <Radio
                sx={{
                  color: purpleTheme.text.secondary,
                  "&.Mui-checked": { color: purpleTheme.primary },
                }}
              />
            }
            label="Lichess"
            sx={{ color: purpleTheme.text.primary }}
          />
          <FormControlLabel
            value="chessdotcom"
            control={
              <Radio
                sx={{
                  color: purpleTheme.text.secondary,
                  "&.Mui-checked": { color: purpleTheme.primary },
                }}
              />
            }
            label="Chess.com"
            sx={{ color: purpleTheme.text.primary }}
          />
        </RadioGroup>
      </FormControl>

      {/* Username Input */}
      <TextField
        fullWidth
        label={`${filters.platform === "lichess" ? "Lichess" : "Chess.com"} username`}
        value={filters.username}
        onChange={handleUsernameChange}
        sx={{
          mb: 3,
          "& .MuiOutlinedInput-root": {
            color: purpleTheme.text.primary,
            "& fieldset": { borderColor: purpleTheme.secondary },
            "&:hover fieldset": { borderColor: purpleTheme.primary },
            "&.Mui-focused fieldset": { borderColor: purpleTheme.primary },
          },
          "& .MuiInputLabel-root": {
            color: purpleTheme.text.secondary,
            "&.Mui-focused": { color: purpleTheme.primary },
          },
        }}
      />

      {/* Download All vs Subset */}
      <FormControl component="fieldset" sx={{ mb: 3, width: "100%" }}>
        <FormLabel
          sx={{
            color: purpleTheme.text.primary,
            fontWeight: "bold",
            mb: 1,
          }}
        >
          Download Options
        </FormLabel>
        <RadioGroup
          value={filters.downloadAll ? "all" : "subset"}
          onChange={handleDownloadAllChange}
        >
          <FormControlLabel
            value="all"
            control={
              <Radio
                sx={{
                  color: purpleTheme.text.secondary,
                  "&.Mui-checked": { color: purpleTheme.primary },
                }}
              />
            }
            label="Download all games"
            sx={{ color: purpleTheme.text.primary }}
          />
          <FormControlLabel
            value="subset"
            control={
              <Radio
                sx={{
                  color: purpleTheme.text.secondary,
                  "&.Mui-checked": { color: purpleTheme.primary },
                }}
              />
            }
            label="Download a subset (with filters below)"
            sx={{ color: purpleTheme.text.primary }}
          />
        </RadioGroup>
      </FormControl>

      {/* Filters - Only show if subset is selected */}
      {!filters.downloadAll && (
        <>
          {/* Color Filter */}
          <FormControl component="fieldset" sx={{ mb: 3, width: "100%" }}>
            <FormLabel
              sx={{
                color: purpleTheme.text.primary,
                fontWeight: "bold",
                mb: 1,
              }}
            >
              Include when playing as
            </FormLabel>
            <FormGroup row>
              <FormControlLabel
                control={
                  <Checkbox
                    checked={filters.includeWhite}
                    onChange={handleCheckboxChange("includeWhite")}
                    sx={{
                      color: purpleTheme.text.secondary,
                      "&.Mui-checked": { color: purpleTheme.primary },
                    }}
                  />
                }
                label="White"
                sx={{ color: purpleTheme.text.primary }}
              />
              <FormControlLabel
                control={
                  <Checkbox
                    checked={filters.includeBlack}
                    onChange={handleCheckboxChange("includeBlack")}
                    sx={{
                      color: purpleTheme.text.secondary,
                      "&.Mui-checked": { color: purpleTheme.primary },
                    }}
                  />
                }
                label="Black"
                sx={{ color: purpleTheme.text.primary }}
              />
            </FormGroup>
          </FormControl>

          {/* Variant Filter */}
          <FormControl component="fieldset" sx={{ mb: 3, width: "100%" }}>
            <FormLabel
              sx={{
                color: purpleTheme.text.primary,
                fontWeight: "bold",
                mb: 1,
              }}
            >
              Include these variants
            </FormLabel>
            <FormGroup row>
              <FormControlLabel
                control={
                  <Checkbox
                    checked={filters.includeChess}
                    onChange={handleCheckboxChange("includeChess")}
                    sx={{
                      color: purpleTheme.text.secondary,
                      "&.Mui-checked": { color: purpleTheme.primary },
                    }}
                  />
                }
                label="Chess"
                sx={{ color: purpleTheme.text.primary, minWidth: "150px" }}
              />
              <FormControlLabel
                control={
                  <Checkbox
                    checked={filters.includeChess960}
                    onChange={handleCheckboxChange("includeChess960")}
                    sx={{
                      color: purpleTheme.text.secondary,
                      "&.Mui-checked": { color: purpleTheme.primary },
                    }}
                  />
                }
                label="Chess960"
                sx={{ color: purpleTheme.text.primary, minWidth: "150px" }}
              />
              <FormControlLabel
                control={
                  <Checkbox
                    checked={filters.includeBugHouse}
                    onChange={handleCheckboxChange("includeBugHouse")}
                    sx={{
                      color: purpleTheme.text.secondary,
                      "&.Mui-checked": { color: purpleTheme.primary },
                    }}
                  />
                }
                label="Bug House"
                sx={{ color: purpleTheme.text.primary, minWidth: "150px" }}
              />
              <FormControlLabel
                control={
                  <Checkbox
                    checked={filters.includeKingOfTheHill}
                    onChange={handleCheckboxChange("includeKingOfTheHill")}
                    sx={{
                      color: purpleTheme.text.secondary,
                      "&.Mui-checked": { color: purpleTheme.primary },
                    }}
                  />
                }
                label="King of the Hill"
                sx={{ color: purpleTheme.text.primary, minWidth: "150px" }}
              />
              <FormControlLabel
                control={
                  <Checkbox
                    checked={filters.includeThreeCheck}
                    onChange={handleCheckboxChange("includeThreeCheck")}
                    sx={{
                      color: purpleTheme.text.secondary,
                      "&.Mui-checked": { color: purpleTheme.primary },
                    }}
                  />
                }
                label="Three Check"
                sx={{ color: purpleTheme.text.primary, minWidth: "150px" }}
              />
              <FormControlLabel
                control={
                  <Checkbox
                    checked={filters.includeCrazyHouse}
                    onChange={handleCheckboxChange("includeCrazyHouse")}
                    sx={{
                      color: purpleTheme.text.secondary,
                      "&.Mui-checked": { color: purpleTheme.primary },
                    }}
                  />
                }
                label="Crazy House"
                sx={{ color: purpleTheme.text.primary, minWidth: "150px" }}
              />
            </FormGroup>
          </FormControl>

          {/* Time Control Filter */}
          <FormControl component="fieldset" sx={{ mb: 3, width: "100%" }}>
            <FormLabel
              sx={{
                color: purpleTheme.text.primary,
                fontWeight: "bold",
                mb: 1,
              }}
            >
              And game types
            </FormLabel>
            <FormGroup row>
              <FormControlLabel
                control={
                  <Checkbox
                    checked={filters.includeUltraBullet}
                    onChange={handleCheckboxChange("includeUltraBullet")}
                    sx={{
                      color: purpleTheme.text.secondary,
                      "&.Mui-checked": { color: purpleTheme.primary },
                    }}
                  />
                }
                label="Ultra Bullet"
                sx={{ color: purpleTheme.text.primary, minWidth: "150px" }}
              />
              <FormControlLabel
                control={
                  <Checkbox
                    checked={filters.includeBullet}
                    onChange={handleCheckboxChange("includeBullet")}
                    sx={{
                      color: purpleTheme.text.secondary,
                      "&.Mui-checked": { color: purpleTheme.primary },
                    }}
                  />
                }
                label="Bullet"
                sx={{ color: purpleTheme.text.primary, minWidth: "150px" }}
              />
              <FormControlLabel
                control={
                  <Checkbox
                    checked={filters.includeBlitz}
                    onChange={handleCheckboxChange("includeBlitz")}
                    sx={{
                      color: purpleTheme.text.secondary,
                      "&.Mui-checked": { color: purpleTheme.primary },
                    }}
                  />
                }
                label="Blitz"
                sx={{ color: purpleTheme.text.primary, minWidth: "150px" }}
              />
              <FormControlLabel
                control={
                  <Checkbox
                    checked={filters.includeRapid}
                    onChange={handleCheckboxChange("includeRapid")}
                    sx={{
                      color: purpleTheme.text.secondary,
                      "&.Mui-checked": { color: purpleTheme.primary },
                    }}
                  />
                }
                label="Rapid"
                sx={{ color: purpleTheme.text.primary, minWidth: "150px" }}
              />
              <FormControlLabel
                control={
                  <Checkbox
                    checked={filters.includeClassical}
                    onChange={handleCheckboxChange("includeClassical")}
                    sx={{
                      color: purpleTheme.text.secondary,
                      "&.Mui-checked": { color: purpleTheme.primary },
                    }}
                  />
                }
                label="Classical"
                sx={{ color: purpleTheme.text.primary, minWidth: "150px" }}
              />
              <FormControlLabel
                control={
                  <Checkbox
                    checked={filters.includeDaily}
                    onChange={handleCheckboxChange("includeDaily")}
                    sx={{
                      color: purpleTheme.text.secondary,
                      "&.Mui-checked": { color: purpleTheme.primary },
                    }}
                  />
                }
                label="Daily/Correspondence"
                sx={{ color: purpleTheme.text.primary, minWidth: "150px" }}
              />
            </FormGroup>
          </FormControl>

          {/* Date Range Filter */}
          <FormControl component="fieldset" sx={{ mb: 3, width: "100%" }}>
            <FormLabel
              sx={{
                color: purpleTheme.text.primary,
                fontWeight: "bold",
                mb: 1,
              }}
            >
              Date Range
            </FormLabel>
            <RadioGroup
              value={filters.dateFilterType}
              onChange={handleDateFilterChange}
            >
              <FormControlLabel
                value="all"
                control={
                  <Radio
                    sx={{
                      color: purpleTheme.text.secondary,
                      "&.Mui-checked": { color: purpleTheme.primary },
                    }}
                  />
                }
                label="All dates"
                sx={{ color: purpleTheme.text.primary }}
              />
              <FormControlLabel
                value="past18months"
                control={
                  <Radio
                    sx={{
                      color: purpleTheme.text.secondary,
                      "&.Mui-checked": { color: purpleTheme.primary },
                    }}
                  />
                }
                label="Past 18 months"
                sx={{ color: purpleTheme.text.primary }}
              />
              <FormControlLabel
                value="between"
                control={
                  <Radio
                    sx={{
                      color: purpleTheme.text.secondary,
                      "&.Mui-checked": { color: purpleTheme.primary },
                    }}
                  />
                }
                label="Between the following dates"
                sx={{ color: purpleTheme.text.primary }}
              />
            </RadioGroup>

            {filters.dateFilterType === "between" && (
              <Box sx={{ mt: 2, display: "flex", gap: 2 }}>
                <TextField
                  type="date"
                  label="Start Date"
                  value={filters.startDate || ""}
                  onChange={handleDateChange("startDate")}
                  InputLabelProps={{ shrink: true }}
                  sx={{
                    flex: 1,
                    "& .MuiOutlinedInput-root": {
                      color: purpleTheme.text.primary,
                      "& fieldset": { borderColor: purpleTheme.secondary },
                      "&:hover fieldset": { borderColor: purpleTheme.primary },
                      "&.Mui-focused fieldset": {
                        borderColor: purpleTheme.primary,
                      },
                    },
                    "& .MuiInputLabel-root": {
                      color: purpleTheme.text.secondary,
                      "&.Mui-focused": { color: purpleTheme.primary },
                    },
                  }}
                />
                <TextField
                  type="date"
                  label="End Date"
                  value={filters.endDate || ""}
                  onChange={handleDateChange("endDate")}
                  InputLabelProps={{ shrink: true }}
                  sx={{
                    flex: 1,
                    "& .MuiOutlinedInput-root": {
                      color: purpleTheme.text.primary,
                      "& fieldset": { borderColor: purpleTheme.secondary },
                      "&:hover fieldset": { borderColor: purpleTheme.primary },
                      "&.Mui-focused fieldset": {
                        borderColor: purpleTheme.primary,
                      },
                    },
                    "& .MuiInputLabel-root": {
                      color: purpleTheme.text.secondary,
                      "&.Mui-focused": { color: purpleTheme.primary },
                    },
                  }}
                />
              </Box>
            )}
          </FormControl>

          {/* Rated Only Filter */}
          <FormControl component="fieldset" sx={{ mb: 3, width: "100%" }}>
            <FormGroup>
              <FormControlLabel
                control={
                  <Checkbox
                    checked={filters.ratedOnly}
                    onChange={handleCheckboxChange("ratedOnly")}
                    sx={{
                      color: purpleTheme.text.secondary,
                      "&.Mui-checked": { color: purpleTheme.primary },
                    }}
                  />
                }
                label="Only include rated games"
                sx={{ color: purpleTheme.text.primary }}
              />
            </FormGroup>
          </FormControl>
        </>
      )}

      {/* Progress Display */}
      {progress.status !== "idle" && (
        <Box sx={{ mb: 3 }}>
          {progress.status === "downloading" && (
            <>
              <Typography
                sx={{ color: purpleTheme.text.secondary, mb: 1 }}
              >
                Downloading games... {progress.currentMonth}
              </Typography>
              <LinearProgress
                variant="determinate"
                value={progress.percentage}
                sx={{
                  backgroundColor: purpleTheme.background.main,
                  "& .MuiLinearProgress-bar": {
                    backgroundColor: purpleTheme.primary,
                  },
                }}
              />
            </>
          )}

          {progress.status === "processing" && (
            <Box sx={{ display: "flex", alignItems: "center", gap: 2 }}>
              <CircularProgress
                size={24}
                sx={{ color: purpleTheme.primary }}
              />
              <Typography sx={{ color: purpleTheme.text.secondary }}>
                Processing and filtering games...
              </Typography>
            </Box>
          )}

          {progress.status === "complete" && (
            <Alert severity="success" sx={{ mb: 2 }}>
              Successfully downloaded {progress.processedGames} games!
            </Alert>
          )}

          {progress.status === "error" && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {progress.errorMessage}
            </Alert>
          )}
        </Box>
      )}

      {/* Download Button */}
      <Button
        variant="contained"
        fullWidth
        startIcon={
          progress.status === "downloading" ||
          progress.status === "processing" ? (
            <CircularProgress size={20} sx={{ color: "white" }} />
          ) : (
            <DownloadIcon />
          )
        }
        onClick={handleDownload}
        disabled={
          !filters.username.trim() ||
          progress.status === "downloading" ||
          progress.status === "processing"
        }
        sx={{
          backgroundColor: purpleTheme.primary,
          color: "white",
          py: 1.5,
          fontWeight: "bold",
          "&:hover": {
            backgroundColor: purpleTheme.accent,
          },
          "&:disabled": {
            backgroundColor: purpleTheme.background.main,
            color: purpleTheme.text.secondary,
          },
        }}
      >
        {progress.status === "downloading" || progress.status === "processing"
          ? "Downloading..."
          : "Download Games"}
      </Button>
    </Paper>
  );
};

export default GameDownloader;
