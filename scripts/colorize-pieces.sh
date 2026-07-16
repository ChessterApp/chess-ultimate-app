#!/bin/bash

# Script to colorize Lichess Alpha pieces with vibrant palette
# Based on docs/prd/ANIMATED_BOARD_PRD.md color scheme

SOURCE_DIR="../frontend/public/pieces/alpha"
OUTPUT_DIR="../frontend/public/pieces/alpha-vibrant"

# Color definitions
WHITE_FILL="#FFD93D"      # Bright yellow
WHITE_OUTLINE="#F59E0B"   # Amber/orange
BLACK_FILL="#6BCB77"      # Vibrant green
BLACK_OUTLINE="#10B981"   # Emerald

echo "🎨 Colorizing Lichess Alpha pieces..."
echo "Source: $SOURCE_DIR"
echo "Output: $OUTPUT_DIR"
echo ""

mkdir -p "$OUTPUT_DIR"

# Process white pieces
for piece in wK wQ wR wB wN wP; do
  echo "Processing ${piece}.svg (white)..."
  sed -e "s/#f9f9f9/${WHITE_FILL}/g" \
      -e "s/#101010/${WHITE_OUTLINE}/g" \
      -e "s/<path fill=\"${WHITE_OUTLINE}\"/<path fill=\"${WHITE_OUTLINE}\" stroke=\"${WHITE_OUTLINE}\" stroke-width=\"8\"/g" \
      "$SOURCE_DIR/${piece}.svg" > "$OUTPUT_DIR/${piece}.svg"
done

# Process black pieces
for piece in bK bQ bR bB bN bP; do
  echo "Processing ${piece}.svg (black)..."
  sed -e "s/#f9f9f9/${BLACK_FILL}/g" \
      -e "s/#101010/${BLACK_OUTLINE}/g" \
      -e "s/<path fill=\"${BLACK_OUTLINE}\"/<path fill=\"${BLACK_OUTLINE}\" stroke=\"${BLACK_OUTLINE}\" stroke-width=\"8\"/g" \
      "$SOURCE_DIR/${piece}.svg" > "$OUTPUT_DIR/${piece}.svg"
done

echo ""
echo "✅ Done! Vibrant pieces created in $OUTPUT_DIR"
echo ""
echo "Piece count:"
ls -1 "$OUTPUT_DIR" | wc -l
echo ""
echo "File sizes:"
du -sh "$OUTPUT_DIR"
