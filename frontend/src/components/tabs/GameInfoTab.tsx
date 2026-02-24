"use client";

import { useState } from "react";
import {
  Box,
  Stack,
  Typography,
  IconButton,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
} from "@mui/material";
import { User, Clock, Calendar, Trophy, Info } from "lucide-react";
import GameReviewTab from "@/components/tabs/GameReviewTab";
import { MoveAnalysis } from "@/hooks/useGameReview";
import { GameReviewTheme } from "@/libs/themes/helper";

export interface GameInfoTabProp {
  moves: string[];
  currentMoveIndex: number;
  goToMove: (index: number) => void;
  comment: string;
  gameReviewTheme: GameReviewTheme | null;
  generateGameReview: (moves: string[]) => void;
  gameReviewLoading: boolean;
  gameReview: MoveAnalysis[];
  gameReviewProgress: number;
  gameInfo: Record<string, string>;
  chatLoading: boolean;
  handleMoveCoachClick: (gameReview: MoveAnalysis) => void;
  handleMoveAnnontateClick: (review: MoveAnalysis, customQuery?: string) => void;
  handleGameReviewClick: (gameReview: MoveAnalysis[], gameInfo: string) => void;
}

function GameInfoTab({
  moves,
  currentMoveIndex,
  goToMove,
  comment,
  gameInfo,
  generateGameReview,
  gameReviewLoading,
  gameReview,
  gameReviewTheme,
  handleMoveCoachClick,
  handleMoveAnnontateClick,
  handleGameReviewClick,
  gameReviewProgress,
  chatLoading,
}: GameInfoTabProp) {
  const [gameInfoOpen, setGameInfoOpen] = useState(false);

  const formatTimeControl = (timeControl: string) => {
    const tc = timeControl.split("+");
    const time = tc[0];
    const inc = tc[1];
    const numberTime = parseInt(time);
    return `${Math.round(numberTime / 60)}+${inc}`;
  };

  function generateGameInfoPrompt(gameInfo: Record<string, string>): string {
    const lines: string[] = [];
    if (gameInfo.White || gameInfo.WhiteElo)
      lines.push(
        `White: ${gameInfo.White || "Unknown"}${gameInfo.WhiteElo ? ` (${gameInfo.WhiteElo})` : ""}`
      );
    if (gameInfo.Black || gameInfo.BlackElo)
      lines.push(
        `Black: ${gameInfo.Black || "Unknown"}${gameInfo.BlackElo ? ` (${gameInfo.BlackElo})` : ""}`
      );
    if (gameInfo.Date) lines.push(`Date: ${gameInfo.Date}`);
    if (gameInfo.Event) lines.push(`Event: ${gameInfo.Event}`);
    if (gameInfo.Site) lines.push(`Site: ${gameInfo.Site}`);
    if (gameInfo.Result) lines.push(`Result: ${gameInfo.Result}`);
    if (gameInfo.TimeControl) lines.push(`Time Control: ${formatTimeControl(gameInfo.TimeControl)}`);
    if (gameInfo.ECO) lines.push(`ECO: ${gameInfo.ECO}`);
    if (gameInfo.Opening) lines.push(`Opening: ${gameInfo.Opening}`);
    return lines.join("\n");
  }

  return (
    <Box sx={{ bgcolor: "background.paper"}}>
      <Stack spacing={3}>
        
        <Box sx={{ display: "flex", justifyContent: "flex-start", p: 2 }}>
          <IconButton
            onClick={() => setGameInfoOpen(true)}
            sx={{
              color: "text.primary",
              bgcolor: "action.selected",
              border: 1, borderColor: 'divider',
              "&:hover": { bgcolor: "action.hover" },
            }}
          >
            <Info size={20} />
          </IconButton>
        </Box>

        {/* Game Information Dialog */}
        <Dialog
          open={gameInfoOpen}
          onClose={() => setGameInfoOpen(false)}
          maxWidth="md"
          fullWidth
          PaperProps={{
            sx: {
              bgcolor: "background.paper",
              color: "text.primary",
              border: 1, borderColor: 'divider',
            }
          }}
        >
          <DialogTitle sx={{ 
            display: "flex", 
            alignItems: "center", 
            gap: 1,
            bgcolor: "background.default",
            color: "text.primary",
            borderBottom: 1, borderColor: 'divider'
          }}>
            <Trophy size={20} />
            Game Information
          </DialogTitle>
          <DialogContent sx={{ bgcolor: "background.paper", color: "text.primary" }}>
            <Stack spacing={2} sx={{ mt: 2 }}>
              {/* Players */}
              <Stack direction={{ xs: "column", sm: "row" }} spacing={4}>
                <Stack spacing={0.5} flex={1}>
                  <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                    <User size={16} />
                    <Typography variant="subtitle2" sx={{ color: "text.primary" }}>
                      Players
                    </Typography>
                  </Box>
                  <Typography variant="body2" sx={{ color: "text.primary" }}>
                    <strong>White:</strong> {gameInfo.White || "Unknown"}
                    {gameInfo.WhiteElo && ` (${gameInfo.WhiteElo})`}
                  </Typography>
                  <Typography variant="body2" sx={{ color: "text.primary" }}>
                    <strong>Black:</strong> {gameInfo.Black || "Unknown"}
                    {gameInfo.BlackElo && ` (${gameInfo.BlackElo})`}
                  </Typography>
                </Stack>
                <Stack spacing={0.5} flex={1}>
                  <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                    <Calendar size={16} />
                    <Typography variant="subtitle2" sx={{ color: "text.primary" }}>
                      Game Details
                    </Typography>
                  </Box>
                  {gameInfo.Date && (
                    <Typography variant="body2" sx={{ color: "text.primary" }}>
                      <strong>Date:</strong> {gameInfo.Date}
                    </Typography>
                  )}
                  {gameInfo.Event && (
                    <Typography variant="body2" sx={{ color: "text.primary" }}>
                      <strong>Event:</strong> {gameInfo.Event}
                    </Typography>
                  )}
                  {gameInfo.Site && (
                    <Typography variant="body2" sx={{ color: "text.primary" }}>
                      <strong>Site:</strong> {gameInfo.Site}
                    </Typography>
                  )}
                  {gameInfo.Result && (
                    <Typography variant="body2" sx={{ color: "text.primary" }}>
                      <strong>Result:</strong> {gameInfo.Result}
                    </Typography>
                  )}
                </Stack>
              </Stack>

              {/* Time Control */}
              {gameInfo.TimeControl && (
                <Stack spacing={0.5}>
                  <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                    <Clock size={16} />
                    <Typography variant="subtitle2" sx={{ color: "text.primary" }}>
                      Time Control
                    </Typography>
                  </Box>
                  <Typography variant="body2" sx={{ color: "text.primary" }}>
                    {formatTimeControl(gameInfo.TimeControl)}
                  </Typography>
                </Stack>
              )}

              {/* Additional Info */}
              {(gameInfo.Opening || gameInfo.ECO) && (
                <Stack spacing={0.5}>
                  <Typography variant="subtitle2" sx={{ color: "text.primary" }}>
                    Opening
                  </Typography>
                  {gameInfo.ECO && (
                    <Typography variant="body2" sx={{ color: "text.primary" }}>
                      <strong>ECO:</strong> {gameInfo.ECO}
                    </Typography>
                  )}
                  {gameInfo.Opening && (
                    <Typography variant="body2" sx={{ color: "text.primary" }}>
                      <strong>Opening:</strong> {gameInfo.Opening}
                    </Typography>
                  )}
                </Stack>
              )}
            </Stack>
          </DialogContent>
          <DialogActions sx={{ 
            bgcolor: "background.default", 
            borderTop: 1, borderColor: 'divider',
            color: "text.primary"
          }}>
            <Button 
              onClick={() => setGameInfoOpen(false)} 
              sx={{ 
                color: "text.primary",
                "&:hover": { bgcolor: "action.selected" }
              }}
            >
              Close
            </Button>
          </DialogActions>
        </Dialog>

        {/* Game Review Tab - Always Visible */}
        <GameReviewTab
          gameReview={gameReview}
          generateGameReview={async () => generateGameReview(moves)}
          moves={moves}
          gameReviewTheme={gameReviewTheme}
          handleMoveCoachClick={handleMoveCoachClick}
          chatLoading={chatLoading}
          gameReviewProgress={gameReviewProgress}
          comment={comment}
          whiteTitle={gameInfo.WhiteTitle || ''}
          blackTitle={gameInfo.BlackTitle || ''}
          whitePlayer={gameInfo.White || "Unknown"}
          blackPlayer={gameInfo.Black || "Unknown"}
          gameInfo={generateGameInfoPrompt(gameInfo)}
          handleMoveAnnontateClick={handleMoveAnnontateClick}
          handleGameReviewClick={handleGameReviewClick}
          gameReviewLoading={gameReviewLoading}
          goToMove={goToMove}
          currentMoveIndex={currentMoveIndex}
        />
      </Stack>
    </Box>
  );
}

export default GameInfoTab;