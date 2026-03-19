#!/bin/bash
# Test: Verify landing page serves pre-rendered HTML content on localhost

set -e

echo "Testing pre-rendered HTML on localhost..."

# Check if service is running
if ! curl -s localhost:3000 > /dev/null; then
  echo "❌ FAIL: Service not running on localhost:3000"
  exit 1
fi

# Fetch the landing page
HTML=$(curl -s localhost:3000 | head -100)

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

# Check 5: Verify actual content is pre-rendered (not just an empty div)
FULL_HTML=$(curl -s localhost:3000)

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

# Should NOT be just a loading div
if echo "$FULL_HTML" | grep -q '<div id="__next"></div>' && ! echo "$FULL_HTML" | grep -q "chesster works"; then
  echo "❌ FAIL: Page appears to be client-side only (empty div)"
  exit 1
fi

echo "✅ PASS: All localhost pre-render checks passed"
echo ""
echo "Summary:"
echo "  - Service running on port 3000"
echo "  - DOCTYPE present"
echo "  - Meta tags present"
echo "  - Title tag correct"
echo "  - Content pre-rendered (not empty div)"
echo ""
echo "The landing page is successfully serving pre-rendered HTML content!"
