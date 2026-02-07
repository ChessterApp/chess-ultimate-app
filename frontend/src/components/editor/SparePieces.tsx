"use client";

import React from "react";
import { useTranslations } from "next-intl";
import { PieceCode, getPieceImageSrc } from "@/lib/chess/fenEditor";

const WHITE_PIECES: PieceCode[] = ["wK", "wQ", "wR", "wB", "wN", "wP"];
const BLACK_PIECES: PieceCode[] = ["bK", "bQ", "bR", "bB", "bN", "bP"];

interface SparePiecesProps {
  color: "white" | "black";
  pieceSet: string;
  selected: "pointer" | "trash" | PieceCode;
  onSelect: (selected: "pointer" | "trash" | PieceCode) => void;
  onDragStart: (piece: PieceCode, e: React.DragEvent) => void;
}

export default function SparePieces({
  color,
  pieceSet,
  selected,
  onSelect,
  onDragStart,
}: SparePiecesProps) {
  const t = useTranslations("editor");
  const pieces = color === "white" ? WHITE_PIECES : BLACK_PIECES;

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: "2px",
        padding: "4px 8px",
        backgroundColor: "#2a2a2a",
        borderRadius: "4px",
        flexWrap: "wrap",
      }}
    >
      {pieces.map((piece) => (
        <div
          key={piece}
          onClick={() => onSelect(piece)}
          draggable
          onDragStart={(e) => onDragStart(piece, e)}
          style={{
            width: 48,
            height: 48,
            cursor: "grab",
            borderRadius: "4px",
            border:
              selected === piece
                ? "2px solid #4fc3f7"
                : "2px solid transparent",
            backgroundColor:
              selected === piece ? "rgba(79, 195, 247, 0.15)" : "transparent",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            transition: "border-color 0.15s, background-color 0.15s",
          }}
        >
          <img
            src={getPieceImageSrc(piece, pieceSet)}
            alt={piece}
            style={{ width: 40, height: 40, pointerEvents: "none" }}
            draggable={false}
            onError={(e) => {
              const img = e.currentTarget;
              if (!img.dataset.retried) {
                img.dataset.retried = '1';
                const base = getPieceImageSrc(piece, pieceSet);
                img.src = base + '&t=' + Date.now();
              }
            }}
          />
        </div>
      ))}

      {/* Pointer tool */}
      <div
        onClick={() => onSelect("pointer")}
        style={{
          width: 48,
          height: 48,
          cursor: "pointer",
          borderRadius: "4px",
          border:
            selected === "pointer"
              ? "2px solid #4fc3f7"
              : "2px solid transparent",
          backgroundColor:
            selected === "pointer"
              ? "rgba(79, 195, 247, 0.15)"
              : "transparent",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
        title={t("pointerTool")}
      >
        <svg
          width="24"
          height="24"
          viewBox="0 0 24 24"
          fill="none"
          stroke="#ccc"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M3 3l7.07 16.97 2.51-7.39 7.39-2.51L3 3z" />
        </svg>
      </div>

      {/* Trash tool */}
      <div
        onClick={() => onSelect("trash")}
        style={{
          width: 48,
          height: 48,
          cursor: "pointer",
          borderRadius: "4px",
          border:
            selected === "trash"
              ? "2px solid #ef5350"
              : "2px solid transparent",
          backgroundColor:
            selected === "trash"
              ? "rgba(239, 83, 80, 0.15)"
              : "transparent",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
        title={t("deleteTool")}
      >
        <svg
          width="24"
          height="24"
          viewBox="0 0 24 24"
          fill="none"
          stroke="#ef5350"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <polyline points="3 6 5 6 21 6" />
          <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
          <line x1="10" y1="11" x2="10" y2="17" />
          <line x1="14" y1="11" x2="14" y2="17" />
        </svg>
      </div>
    </div>
  );
}
