"use client";

import React, { useState, useCallback, useEffect, useMemo } from "react";
import { useTranslations } from "next-intl";
import { Chessboard } from "react-chessboard";
import { useRouter, useSearchParams } from "next/navigation";
import SparePieces from "./SparePieces";
import EditorControls from "./EditorControls";
import {
  EditorPieces,
  PieceCode,
  CastlingRights,
  STARTING_FEN,
  EMPTY_FEN,
  fenToPieces,
  piecesToFen,
  togglePieceColor,
  computeCastlingAvailability,
  getPieceImageSrc,
} from "@/lib/chess/fenEditor";
import { useLocalStorage } from "usehooks-ts";
import { getCurrentThemeColors, BOARD_THEMES } from "@/libs/setting/helper";

type BoardPieceMap = Record<string, string>;

export interface EditorState {
  turn: "w" | "b";
  castling: CastlingRights;
  enPassant: string;
  pieces: EditorPieces;
  onTurnChange: (turn: "w" | "b") => void;
  onCastlingChange: (castling: CastlingRights) => void;
  onEnPassantChange: (ep: string) => void;
  onPreset: (fen: string) => void;
  onStartingPosition: () => void;
  onClearBoard: () => void;
  onFlipBoard: () => void;
  onAnalysisBoard: () => void;
  onContinueFromHere: () => void;
  onStudy: () => void;
  photoPreview?: string | null;
  photoLoading?: boolean;
  photoError?: string;
  onUploadPhoto?: (event: React.ChangeEvent<HTMLInputElement>) => void;
}

interface BoardEditorProps {
  /** Override initial FEN (used in embedded mode instead of URL param) */
  initialFen?: string;
  /** Callback when "Analysis Board" is clicked — switches back to analysis mode with this FEN */
  onAnalyze?: (fen: string) => void;
  /** When true, hides page-level chrome (URL field) and fits within parent panel */
  embedded?: boolean;
  /** Board width override for embedded mode */
  boardWidth?: number;
  /** When true, don't render EditorControls inline (they'll be rendered externally) */
  hideControls?: boolean;
  /** Callback to expose editor state for external EditorControls rendering */
  onEditorStateChange?: (state: EditorState) => void;
  /** Photo upload state and handlers */
  photoPreview?: string | null;
  photoLoading?: boolean;
  photoError?: string;
  onPhotoUpload?: (event: React.ChangeEvent<HTMLInputElement>) => void;
}

export default function BoardEditor({
  initialFen: propFen,
  onAnalyze,
  embedded = false,
  boardWidth: propBoardWidth,
  hideControls = false,
  onEditorStateChange,
  photoPreview,
  photoLoading,
  photoError,
  onPhotoUpload,
}: BoardEditorProps = {}) {
  const t = useTranslations("editor");
  const router = useRouter();
  const searchParams = useSearchParams();

  // User settings from localStorage
  const [pieceSet] = useLocalStorage<string>("board_piece_type", "Fritz");
  const [boardTheme] = useLocalStorage<string>("board_theme", "chessbase");

  // Initialize from prop, URL param, or starting position
  const startFen = propFen || searchParams?.get("fen") || STARTING_FEN;
  const initialState = fenToPieces(startFen);

  const [pieces, setPieces] = useState<EditorPieces>(initialState.pieces);
  const [turn, setTurn] = useState<"w" | "b">(initialState.turn);
  const [castling, setCastling] = useState<CastlingRights>(initialState.castling);
  const [enPassant, setEnPassant] = useState<string>(initialState.enPassant);
  const [orientation, setOrientation] = useState<"white" | "black">("white");
  const [selected, setSelected] = useState<"pointer" | "trash" | PieceCode>("pointer");
  const [fenInput, setFenInput] = useState<string>(startFen);
  const [copied, setCopied] = useState(false);

  // Generate current FEN
  const currentFen = useMemo(
    () => piecesToFen(pieces, turn, castling, enPassant),
    [pieces, turn, castling, enPassant]
  );

  // Sync FEN input when board changes
  useEffect(() => {
    setFenInput(currentFen);
  }, [currentFen]);

  // Auto-disable castling when pieces move away from starting squares
  useEffect(() => {
    const avail = computeCastlingAvailability(pieces);
    setCastling((prev) => ({
      whiteOO: prev.whiteOO && avail.whiteOOPossible,
      whiteOOO: prev.whiteOOO && avail.whiteOOOPossible,
      blackOO: prev.blackOO && avail.blackOOPossible,
      blackOOO: prev.blackOOO && avail.blackOOOPossible,
    }));
  }, [pieces]);

  // Generate URL for the current position
  const editorUrl = useMemo(() => {
    if (typeof window === "undefined") return "";
    return `${window.location.origin}/editor?fen=${encodeURIComponent(currentFen)}`;
  }, [currentFen]);

  // Convert EditorPieces to react-chessboard position format
  const boardPosition: BoardPieceMap = useMemo(() => {
    const pos: BoardPieceMap = {};
    for (const [sq, piece] of Object.entries(pieces)) {
      pos[sq] = piece;
    }
    return pos;
  }, [pieces]);

  // Custom pieces renderer for the board
  const customPieces = useMemo(() => {
    const allPieces = ["P", "N", "B", "R", "Q", "K"];
    const colors = ["w", "b"];
    const result: Record<
      string,
      ({ squareWidth }: { squareWidth: number }) => React.JSX.Element
    > = {};

    colors.forEach((color) => {
      allPieces.forEach((p) => {
        const key = `${color}${p}`;
        const src = getPieceImageSrc(key as PieceCode, pieceSet);
        result[key] = ({ squareWidth }) => (
          <img
            src={src}
            style={{ width: squareWidth, height: squareWidth }}
            draggable={false}
            onError={(e) => {
              const img = e.currentTarget;
              if (!img.dataset.retried) {
                img.dataset.retried = '1';
                img.src = src + '&t=' + Date.now();
              }
            }}
          />
        );
      });
    });

    return result;
  }, [pieceSet]);

  // Handle clicking on a square
  const handleSquareClick = useCallback(
    (square: string) => {
      if (selected === "pointer") return;
      if (selected === "trash") {
        setPieces((prev) => {
          const next = { ...prev };
          delete next[square];
          return next;
        });
      } else {
        // Place selected piece
        setPieces((prev) => ({ ...prev, [square]: selected }));
      }
    },
    [selected]
  );

  // Handle right-click to toggle piece color
  const handleSquareRightClick = useCallback(
    (square: string) => {
      setPieces((prev) => {
        const piece = prev[square];
        if (!piece) return prev;
        return { ...prev, [square]: togglePieceColor(piece) };
      });
    },
    []
  );

  // Handle piece drop on the board (moving existing piece)
  const handlePieceDrop = useCallback(
    (sourceSquare: string, targetSquare: string, piece: string) => {
      setPieces((prev) => {
        const next = { ...prev };
        delete next[sourceSquare];
        next[targetSquare] = piece as PieceCode;
        return next;
      });
      return true;
    },
    []
  );

  // Handle spare piece drop onto the board
  const handlePieceDropOutsideBoard = useCallback(() => {
    // react-chessboard calls this when a piece is dragged off the board — remove it
    // We handle this via onPieceDrop returning false for off-board drops
  }, []);

  // Handle drag from spare pieces
  const handleSpareDragStart = useCallback(
    (piece: PieceCode, e: React.DragEvent) => {
      e.dataTransfer.setData("text/plain", piece);
      e.dataTransfer.effectAllowed = "copy";
    },
    []
  );

  // Handle drop on square (from spare pieces via HTML5 drag)
  const handleSquareDrop = useCallback((e: React.DragEvent, square: string) => {
    e.preventDefault();
    const piece = e.dataTransfer.getData("text/plain") as PieceCode;
    if (piece && piece.length === 2) {
      setPieces((prev) => ({ ...prev, [square]: piece }));
    }
  }, []);

  // Load FEN from input field
  const handleFenSubmit = useCallback((fenStr: string) => {
    try {
      const parsed = fenToPieces(fenStr);
      setPieces(parsed.pieces);
      setTurn(parsed.turn);
      setCastling(parsed.castling);
      setEnPassant(parsed.enPassant);
    } catch {
      // Invalid FEN — ignore
    }
  }, []);

  // Preset / action handlers
  const handlePreset = useCallback((fen: string) => {
    const parsed = fenToPieces(fen);
    setPieces(parsed.pieces);
    setTurn(parsed.turn);
    setCastling(parsed.castling);
    setEnPassant(parsed.enPassant);
  }, []);

  const handleStartingPosition = useCallback(() => handlePreset(STARTING_FEN), [handlePreset]);
  const handleClearBoard = useCallback(() => handlePreset(EMPTY_FEN), [handlePreset]);
  const handleFlipBoard = useCallback(
    () => setOrientation((prev) => (prev === "white" ? "black" : "white")),
    []
  );

  const handleAnalysisBoard = useCallback(() => {
    if (onAnalyze) {
      onAnalyze(currentFen);
    } else {
      router.push(`/position?fen=${encodeURIComponent(currentFen)}`);
    }
  }, [router, currentFen, onAnalyze]);

  const handleContinueFromHere = useCallback(() => {
    router.push(`/opponent?fen=${encodeURIComponent(currentFen)}`);
  }, [router, currentFen]);

  const handleStudy = useCallback(() => {
    router.push(`/learn?fen=${encodeURIComponent(currentFen)}`);
  }, [router, currentFen]);

  const handleCopyUrl = useCallback(() => {
    navigator.clipboard.writeText(editorUrl).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }, [editorUrl]);

  // Expose editor state to parent for external controls rendering
  useEffect(() => {
    if (onEditorStateChange) {
      onEditorStateChange({
        turn,
        castling,
        enPassant,
        pieces,
        onTurnChange: setTurn,
        onCastlingChange: setCastling,
        onEnPassantChange: setEnPassant,
        onPreset: handlePreset,
        onStartingPosition: handleStartingPosition,
        onClearBoard: handleClearBoard,
        onFlipBoard: handleFlipBoard,
        onAnalysisBoard: handleAnalysisBoard,
        onContinueFromHere: handleContinueFromHere,
        onStudy: handleStudy,
        photoPreview,
        photoLoading,
        photoError,
        onUploadPhoto: onPhotoUpload,
      });
    }
  }, [turn, castling, enPassant, pieces, onEditorStateChange, handlePreset, handleStartingPosition, handleClearBoard, handleFlipBoard, handleAnalysisBoard, handleContinueFromHere, handleStudy, photoPreview, photoLoading, photoError, onPhotoUpload]);

  const themeColors = getCurrentThemeColors(boardTheme);

  const boardSize = propBoardWidth || (embedded ? 400 : 480);

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "8px",
        maxWidth: embedded ? "100%" : "900px",
        margin: "0 auto",
        padding: embedded ? "8px 0" : "16px",
      }}
    >
      {/* White spare pieces (top) */}
      <SparePieces
        color="white"
        pieceSet={pieceSet}
        selected={selected}
        onSelect={setSelected}
        onDragStart={handleSpareDragStart}
      />

      {/* Board + Controls */}
      <div
        style={{
          display: "flex",
          gap: "16px",
          alignItems: "flex-start",
          flexWrap: "wrap",
        }}
      >
        {/* Board */}
        <div
          style={{ flex: "0 0 auto" }}
          onDragOver={(e) => e.preventDefault()}
        >
          <Chessboard
            id="board-editor"
            position={boardPosition}
            boardWidth={boardSize}
            boardOrientation={orientation}
            arePiecesDraggable={true}
            onPieceDrop={handlePieceDrop}
            onSquareClick={handleSquareClick}
            onSquareRightClick={handleSquareRightClick}
            customBoardStyle={{
              borderRadius: "4px",
            }}
            customDarkSquareStyle={{
              backgroundColor: themeColors.darkSquareColor,
            }}
            customLightSquareStyle={{
              backgroundColor: themeColors.lightSquareColor,
            }}
            customPieces={customPieces}
            animationDuration={0}
          />
        </div>

        {/* Controls panel (hidden when rendered externally) */}
        {!hideControls && (
          <div style={{ flex: "1 1 220px", minWidth: "220px" }}>
            <EditorControls
              turn={turn}
              castling={castling}
              enPassant={enPassant}
              pieces={pieces}
              onTurnChange={setTurn}
              onCastlingChange={setCastling}
              onEnPassantChange={setEnPassant}
              onPreset={handlePreset}
              onStartingPosition={handleStartingPosition}
              onClearBoard={handleClearBoard}
              onFlipBoard={handleFlipBoard}
              onAnalysisBoard={handleAnalysisBoard}
              onContinueFromHere={handleContinueFromHere}
              onStudy={handleStudy}
            />
          </div>
        )}
      </div>

      {/* Black spare pieces (bottom) */}
      <SparePieces
        color="black"
        pieceSet={pieceSet}
        selected={selected}
        onSelect={setSelected}
        onDragStart={handleSpareDragStart}
      />

      {/* FEN input */}
      <div
        style={{
          display: "flex",
          gap: "8px",
          alignItems: "center",
          backgroundColor: "#1e1e1e",
          padding: "8px 12px",
          borderRadius: "4px",
          border: "1px solid #333",
        }}
      >
        <label style={{ color: "#999", fontSize: "12px", flexShrink: 0 }}>
          {t("fen")}
        </label>
        <input
          type="text"
          value={fenInput}
          onChange={(e) => setFenInput(e.target.value)}
          onBlur={() => handleFenSubmit(fenInput)}
          onKeyDown={(e) => {
            if (e.key === "Enter") handleFenSubmit(fenInput);
          }}
          style={{
            flex: 1,
            backgroundColor: "#2a2a2a",
            color: "#ddd",
            border: "1px solid #444",
            borderRadius: "4px",
            padding: "6px 8px",
            fontSize: "13px",
            fontFamily: "monospace",
          }}
        />
      </div>

      {/* URL field (hidden in embedded mode) */}
      {!embedded && <div
        style={{
          display: "flex",
          gap: "8px",
          alignItems: "center",
          backgroundColor: "#1e1e1e",
          padding: "8px 12px",
          borderRadius: "4px",
          border: "1px solid #333",
        }}
      >
        <label style={{ color: "#999", fontSize: "12px", flexShrink: 0 }}>
          {t("url")}
        </label>
        <input
          type="text"
          value={editorUrl}
          readOnly
          style={{
            flex: 1,
            backgroundColor: "#2a2a2a",
            color: "#888",
            border: "1px solid #444",
            borderRadius: "4px",
            padding: "6px 8px",
            fontSize: "13px",
            fontFamily: "monospace",
          }}
        />
        <button
          onClick={handleCopyUrl}
          style={{
            padding: "6px 12px",
            backgroundColor: copied ? "#2e7d32" : "#333",
            color: "#ddd",
            border: "1px solid #555",
            borderRadius: "4px",
            cursor: "pointer",
            fontSize: "12px",
            transition: "background-color 0.15s",
          }}
        >
          {copied ? t("copied") : t("copy")}
        </button>
      </div>}
    </div>
  );
}
