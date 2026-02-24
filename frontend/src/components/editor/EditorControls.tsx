"use client";

import React from "react";
import { useTranslations } from "next-intl";
import {
  CastlingRights,
  EditorPieces,
  PRESET_POSITIONS,
  getEnPassantOptions,
  computeCastlingAvailability,
} from "@/lib/chess/fenEditor";

interface EditorControlsProps {
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

const sectionStyle: React.CSSProperties = {
  marginBottom: "12px",
};

const labelStyle: React.CSSProperties = {
  color: "var(--text-secondary)",
  fontSize: "12px",
  textTransform: "uppercase",
  letterSpacing: "0.5px",
  marginBottom: "6px",
  display: "block",
};

const btnStyle: React.CSSProperties = {
  width: "100%",
  padding: "8px 12px",
  marginBottom: "6px",
  border: "1px solid var(--border-default)",
  borderRadius: "4px",
  backgroundColor: "var(--surface-raised)",
  color: "var(--text-primary)",
  fontSize: "13px",
  cursor: "pointer",
  textAlign: "center",
  fontWeight: 500,
  textTransform: "uppercase",
  letterSpacing: "0.5px",
  transition: "background-color 0.15s",
};

const selectStyle: React.CSSProperties = {
  width: "100%",
  padding: "6px 8px",
  backgroundColor: "var(--surface-raised)",
  color: "var(--text-primary)",
  border: "1px solid var(--border-default)",
  borderRadius: "4px",
  fontSize: "13px",
  marginBottom: "4px",
};

export default function EditorControls({
  turn,
  castling,
  enPassant,
  pieces,
  onTurnChange,
  onCastlingChange,
  onEnPassantChange,
  onPreset,
  onStartingPosition,
  onClearBoard,
  onFlipBoard,
  onAnalysisBoard,
  onContinueFromHere,
  onStudy,
  photoPreview,
  photoLoading,
  photoError,
  onUploadPhoto,
}: EditorControlsProps) {
  const t = useTranslations("editor");
  const epOptions = getEnPassantOptions(pieces, turn);
  const castlingAvail = computeCastlingAvailability(pieces);

  return (
    <div
      style={{
        padding: "12px",
        backgroundColor: "var(--surface-card)",
        borderRadius: "6px",
        border: "1px solid var(--border-default)",
        minWidth: "220px",
      }}
    >
      {/* Set the board */}
      <div style={sectionStyle}>
        <label style={labelStyle}>{t("setTheBoard")}</label>
        <select
          style={selectStyle}
          onChange={(e) => {
            const fen = PRESET_POSITIONS[e.target.value];
            if (fen) onPreset(fen);
          }}
          defaultValue=""
        >
          <option value="" disabled>
            {t("choosePosition")}
          </option>
          {Object.keys(PRESET_POSITIONS).map((key) => (
            <option key={key} value={key}>
              {t(key)}
            </option>
          ))}
        </select>
      </div>

      {/* Variant */}
      <div style={sectionStyle}>
        <label style={labelStyle}>{t("variant")}</label>
        <select style={selectStyle} value="standard" disabled>
          <option value="standard">{t("standard")}</option>
        </select>
      </div>

      {/* Color to play */}
      <div style={sectionStyle}>
        <label style={labelStyle}>{t("colorToPlay")}</label>
        <div style={{ display: "flex", gap: "12px" }}>
          <label
            style={{
              color: "var(--text-primary)",
              fontSize: "13px",
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              gap: "4px",
            }}
          >
            <input
              type="radio"
              name="turn"
              checked={turn === "w"}
              onChange={() => onTurnChange("w")}
            />
            {t("white")}
          </label>
          <label
            style={{
              color: "var(--text-primary)",
              fontSize: "13px",
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              gap: "4px",
            }}
          >
            <input
              type="radio"
              name="turn"
              checked={turn === "b"}
              onChange={() => onTurnChange("b")}
            />
            {t("black")}
          </label>
        </div>
      </div>

      {/* Castling */}
      <div style={sectionStyle}>
        <label style={labelStyle}>{t("castling")}</label>

        {/* White castling */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "8px",
            marginBottom: "4px",
          }}
        >
          <span style={{ color: "var(--text-secondary)", fontSize: "12px", width: "40px" }}>
            {t("white")}
          </span>
          <label
            style={{
              color: castlingAvail.whiteOOPossible ? "var(--text-primary)" : "var(--text-secondary)",
              fontSize: "13px",
              cursor: castlingAvail.whiteOOPossible ? "pointer" : "default",
              display: "flex",
              alignItems: "center",
              gap: "3px",
            }}
          >
            <input
              type="checkbox"
              checked={castling.whiteOO}
              disabled={!castlingAvail.whiteOOPossible}
              onChange={(e) =>
                onCastlingChange({ ...castling, whiteOO: e.target.checked })
              }
            />
            O-O
          </label>
          <label
            style={{
              color: castlingAvail.whiteOOOPossible ? "var(--text-primary)" : "var(--text-secondary)",
              fontSize: "13px",
              cursor: castlingAvail.whiteOOOPossible ? "pointer" : "default",
              display: "flex",
              alignItems: "center",
              gap: "3px",
            }}
          >
            <input
              type="checkbox"
              checked={castling.whiteOOO}
              disabled={!castlingAvail.whiteOOOPossible}
              onChange={(e) =>
                onCastlingChange({ ...castling, whiteOOO: e.target.checked })
              }
            />
            O-O-O
          </label>
        </div>

        {/* Black castling */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "8px",
          }}
        >
          <span style={{ color: "var(--text-secondary)", fontSize: "12px", width: "40px" }}>
            {t("black")}
          </span>
          <label
            style={{
              color: castlingAvail.blackOOPossible ? "var(--text-primary)" : "var(--text-secondary)",
              fontSize: "13px",
              cursor: castlingAvail.blackOOPossible ? "pointer" : "default",
              display: "flex",
              alignItems: "center",
              gap: "3px",
            }}
          >
            <input
              type="checkbox"
              checked={castling.blackOO}
              disabled={!castlingAvail.blackOOPossible}
              onChange={(e) =>
                onCastlingChange({ ...castling, blackOO: e.target.checked })
              }
            />
            O-O
          </label>
          <label
            style={{
              color: castlingAvail.blackOOOPossible ? "var(--text-primary)" : "var(--text-secondary)",
              fontSize: "13px",
              cursor: castlingAvail.blackOOOPossible ? "pointer" : "default",
              display: "flex",
              alignItems: "center",
              gap: "3px",
            }}
          >
            <input
              type="checkbox"
              checked={castling.blackOOO}
              disabled={!castlingAvail.blackOOOPossible}
              onChange={(e) =>
                onCastlingChange({ ...castling, blackOOO: e.target.checked })
              }
            />
            O-O-O
          </label>
        </div>
      </div>

      {/* En passant */}
      <div style={sectionStyle}>
        <label style={labelStyle}>{t("enPassant")}</label>
        <select
          style={selectStyle}
          value={enPassant}
          onChange={(e) => onEnPassantChange(e.target.value)}
        >
          <option value="-">{t("none")}</option>
          {epOptions.map((sq) => (
            <option key={sq} value={sq}>
              {sq}
            </option>
          ))}
        </select>
      </div>

      {/* Action buttons */}
      <div style={{ marginTop: "16px" }}>
        <button
          style={btnStyle}
          onClick={onStartingPosition}
          onMouseEnter={(e) =>
            (e.currentTarget.style.backgroundColor = "var(--surface-card-hover)")
          }
          onMouseLeave={(e) =>
            (e.currentTarget.style.backgroundColor = "var(--surface-raised)")
          }
        >
          {t("startingPosition")}
        </button>
        <button
          style={btnStyle}
          onClick={onClearBoard}
          onMouseEnter={(e) =>
            (e.currentTarget.style.backgroundColor = "var(--surface-card-hover)")
          }
          onMouseLeave={(e) =>
            (e.currentTarget.style.backgroundColor = "var(--surface-raised)")
          }
        >
          {t("clearBoard")}
        </button>
        <button
          style={btnStyle}
          onClick={onFlipBoard}
          onMouseEnter={(e) =>
            (e.currentTarget.style.backgroundColor = "var(--surface-card-hover)")
          }
          onMouseLeave={(e) =>
            (e.currentTarget.style.backgroundColor = "var(--surface-raised)")
          }
        >
          {t("flipBoard")}
        </button>
        <button
          style={{
            ...btnStyle,
            backgroundColor: "#1b5e20",
            borderColor: "#2e7d32",
          }}
          onClick={onAnalysisBoard}
          onMouseEnter={(e) =>
            (e.currentTarget.style.backgroundColor = "#2e7d32")
          }
          onMouseLeave={(e) =>
            (e.currentTarget.style.backgroundColor = "#1b5e20")
          }
        >
          {t("analysisBoard")} &rarr;
        </button>
        <button
          style={{
            ...btnStyle,
            backgroundColor: "#0d47a1",
            borderColor: "#1565c0",
          }}
          onClick={onContinueFromHere}
          onMouseEnter={(e) =>
            (e.currentTarget.style.backgroundColor = "#1565c0")
          }
          onMouseLeave={(e) =>
            (e.currentTarget.style.backgroundColor = "#0d47a1")
          }
        >
          {t("continueFromHere")} &rarr;
        </button>
        <button
          style={{
            ...btnStyle,
            backgroundColor: "#4a148c",
            borderColor: "#6a1b9a",
          }}
          onClick={onStudy}
          onMouseEnter={(e) =>
            (e.currentTarget.style.backgroundColor = "#6a1b9a")
          }
          onMouseLeave={(e) =>
            (e.currentTarget.style.backgroundColor = "#4a148c")
          }
        >
          {t("study")} &rarr;
        </button>

        {/* Upload Board Photo button */}
        {onUploadPhoto && (
          <label
            style={{
              ...btnStyle,
              backgroundColor: "#00838f",
              borderColor: "#00acc1",
              cursor: photoLoading ? "default" : "pointer",
              opacity: photoLoading ? 0.7 : 1,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
            onMouseEnter={(e) => {
              if (!photoLoading) {
                e.currentTarget.style.backgroundColor = "#00acc1";
              }
            }}
            onMouseLeave={(e) => {
              if (!photoLoading) {
                e.currentTarget.style.backgroundColor = "#00838f";
              }
            }}
          >
            {photoLoading ? t("analyzingPhoto") : t("uploadBoardPhoto")}
            <input
              type="file"
              hidden
              accept="image/*"
              onChange={onUploadPhoto}
              disabled={photoLoading}
            />
          </label>
        )}

        {/* Photo Preview */}
        {photoPreview && (
          <div
            style={{
              position: "relative",
              marginTop: "8px",
              marginBottom: "8px",
              borderRadius: "4px",
              border: "1px solid var(--border-default)",
              overflow: "hidden",
            }}
          >
            <img
              src={photoPreview}
              alt="Board preview"
              style={{
                width: "100%",
                maxHeight: "150px",
                objectFit: "contain",
                display: "block",
              }}
            />
          </div>
        )}

        {/* Photo Error */}
        {photoError && (
          <div
            style={{
              color: "var(--error, #f44336)",
              fontSize: "12px",
              marginTop: "4px",
              marginBottom: "8px",
              padding: "8px",
              backgroundColor: "rgba(244, 67, 54, 0.1)",
              borderRadius: "4px",
              border: "1px solid var(--error, #f44336)",
              lineHeight: "1.4",
            }}
          >
            {photoError}
          </div>
        )}
      </div>
    </div>
  );
}
