#!/bin/bash
# Test: Verify landing page serves pre-rendered HTML content

set -e

echo "Testing pre-rendered HTML on production..."

# Fetch the landing page
HTML=$(curl -s https://vps.chesster.io/ | head -100)

# Check 1: HTML should not be empty
if [ -z "$HTML" ]; then
  echo "❌ FAIL: HTML response is empty"
  exit 1
fi

# Check 2: Should contain DOCTYPE
if ! echo "$HTML" | grep -q "<!DOCTYPE html>"; then
  echo "❌ FAIL: Missing DOCTYPE"
  exit 1
fi

# Check 3: Should contain pre-rendered meta tags
if ! echo "$HTML" | grep -q 'meta name="description"'; then
  echo "❌ FAIL: Missing meta description tag"
  exit 1
fi

# Check 4: Should contain title tag
if ! echo "$HTML" | grep -q '<title>Chesster - AI-Powered Chess Training</title>'; then
  echo "❌ FAIL: Missing or incorrect title tag"
  exit 1
fi

# Check 5: Should contain Open Graph meta tags
if ! echo "$HTML" | grep -q 'property="og:title"'; then
  echo "❌ FAIL: Missing Open Graph title"
  exit 1
fi

# Check 6: Verify actual content is pre-rendered (not just an empty div)
FULL_HTML=$(curl -s https://vps.chesster.io/)

# Should contain hero headline
if ! echo "$FULL_HTML" | grep -q "the free, fun, and effective way to master chess"; then
  echo "❌ FAIL: Missing hero headline in pre-rendered HTML"
  exit 1
fi

# Should contain section headings
if ! echo "$FULL_HTML" | grep -q "why chesster works"; then
  echo "❌ FAIL: Missing section headings in pre-rendered HTML"
  exit 1
fi

# Should contain feature content
if ! echo "$FULL_HTML" | grep -q "start learning in minutes"; then
  echo "❌ FAIL: Missing feature sections in pre-rendered HTML"
  exit 1
fi

# Should contain footer CTA
if ! echo "$FULL_HTML" | grep -q "ready to become a chess master"; then
  echo "❌ FAIL: Missing footer CTA in pre-rendered HTML"
  exit 1
fi

echo "✅ PASS: All pre-render checks passed"
echo ""
echo "Summary:"
echo "  - DOCTYPE present"
echo "  - Meta tags present (description, og:title, etc.)"
echo "  - Title tag correct"
echo "  - Hero headline pre-rendered"
echo "  - Section headings pre-rendered"
echo "  - Feature sections pre-rendered"
echo "  - Footer CTA pre-rendered"
echo ""
echo "The landing page is successfully serving pre-rendered HTML content!"
