# Chesster Debut — Notation/Board Sync Fix Plan

> Investigation completed 2026-02-09. **No code changes made — plan only.**

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Lichess Architecture Study](#2-lichess-architecture-study)
3. [Current Chesster Architecture](#3-current-chesster-architecture)
4. [Full Data Flow Analysis](#4-full-data-flow-analysis)
5. [Root Causes Identified](#5-root-causes-identified)
6. [Fix Plan — Exact Changes](#6-fix-plan--exact-changes)
7. [Architecture Recommendations](#7-architecture-recommendations)

---

## 1. Executive Summary

The Chesster Debut page has a **state synchronization problem** between four subsystems:
1. The **board** (react-chessboard, FEN-driven)
2. The **move tree** (nested `OpeningNode` fetched from backend)
3. The **notation renderer** (`MoveNotation.tsx`)
4. The **selected node tracker** (`selectedNode` state in `page.tsx`)

The core issues are:
- **After `addNode` + `fetchTree`, the `selectedNode` reference becomes stale** — it points to the old tree object, not the newly-fetched one
- **Tree re-fetch replaces the entire tree object** but `selectedNode` still holds a reference to a node from the *previous* tree
- **`MoveNotation` uses `useMemo` keyed on `tree` and `selectedNodeId`**, but after tree refresh, it may match on ID while the tree structure has changed
- **Navigation (`handleNext`/`handlePrev`) traverses `selectedNode.children`** which is from the old tree after refresh

---

## 2. Lichess Architecture Study

### 2.1 Key Concepts from Lichess (`ui/lib/src/tree/`)

**Lichess uses a path-based addressing system, NOT node references.**

#### TreePath (string-based cursor)
```typescript
type TreePath = string;  // e.g., "" (root), "Uf" (first child), "UfQa" (grandchild)
```
- Each node has a 2-character `id` (e.g., `"Uf"`)
- A path is the concatenation of node IDs from root to current: `"UfQa3b"`
- Path operations: `head()` → first 2 chars, `tail()` → rest, `init()` → drop last 2, `last()` → last 2
- Comparing paths: `contains(p1, p2)` → does `p1` start with `p2`?

#### TreeWrapper (in-memory, mutable)
```typescript
interface TreeWrapper {
  root: TreeNode;
  nodeAtPath(path: TreePath): TreeNode;       // resolve path to node
  addNode(node: TreeNode, path: TreePath): TreePath | undefined;  // returns NEW path
  getNodeList(path: TreePath): TreeNode[];     // all nodes from root to path
  pathIsMainline(path: TreePath): boolean;
  deleteNodeAt(path: TreePath): void;
  // ... more operations
}
```

Key patterns:
- **`addNode` returns the new path** (parent path + new node ID)
- **If node already exists at that path, it merges** (doesn't duplicate)
- **Tree is mutated in-place**, not replaced. No re-fetch from server.
- **Navigation is done by changing the path**, then deriving `node` and `nodeList`

#### AnalyseCtrl — The State Machine
```typescript
class AnalyseCtrl {
  path: TreePath;            // THE source of truth for "where am I?"
  node: TreeNode;            // DERIVED from path (via tree.nodeAtPath)
  nodeList: TreeNode[];      // DERIVED from path (via tree.getNodeList)
  mainline: TreeNode[];      // DERIVED from root
  tree: TreeWrapper;         // in-memory mutable tree
}
```

The critical method:
```typescript
private setPath(path: TreePath): void {
  this.path = path;
  this.nodeList = this.tree.getNodeList(path);
  this.node = last(this.nodeList);         // ALWAYS derived from tree
  this.mainline = mainlineNodeList(this.tree.root);
}
```

**The path is the SINGLE SOURCE OF TRUTH. Everything else is derived.**

#### How Lichess Adds a Move
```typescript
// 1. User drops piece on board
userMove(orig, dest, capture) → sendMove(orig, dest, capture, prom)

// 2. sendMove creates a local node
private addNodeLocally(move: Move): void {
  const pos = this.node.pos().unwrap().clone();
  const san = makeSanAndPlay(pos, move);
  const node = completeNode({ ply, uci, san, fen, pos });
  this.addNode(node, this.path);   // ← uses CURRENT path
}

// 3. addNode adds to tree and jumps
addNode(node, path) {
  const newPath = this.tree.addNode(node, path);  // returns path+nodeId
  if (!newPath) return;
  this.jump(newPath);              // ← navigates to new position
  this.redraw();
}

// 4. jump() updates everything via setPath
jump(path) {
  this.setPath(path);    // path → node, nodeList, mainline
  this.showGround();     // updates chessground with node.fen
  this.onChange();        // emits events
}
```

**No server round-trip. No tree re-fetch. Purely in-memory mutation.**

#### How Lichess Renders the Notation
- The `TreeView` renders nodes by walking the tree from root
- Each move element has a `p` attribute set to its TreePath
- Clicking a move calls `ctrl.userJump(path)` which calls `setPath → jump → showGround`
- Active move is determined by comparing element's `p` attribute with `ctrl.path`

### 2.2 Key Takeaways

| Lichess Pattern | Chesster Current | Problem |
|---|---|---|
| Path is source of truth | `selectedNode` reference is source of truth | Reference goes stale after tree re-fetch |
| Tree mutated in-place | Tree replaced entirely via `setCurrentTree()` | All node references invalidated |
| `addNode` returns new path | `addNode` returns server response (flat node, no children) | Can't navigate tree with flat node |
| Node derived from path + tree | Node stored independently | Node ↔ tree desync |
| No server round-trip for moves | Full tree re-fetch after every move | Slow, causes race conditions |

---

## 3. Current Chesster Architecture

### 3.1 State Layout (`page.tsx`)

```
selectedRepertoireId  ─→ fetchTree(id) ─→ currentTree (nested root)
selectedNode          ─→ boardFen (set from node.fen)
                      ─→ MoveNotation (selectedNodeId for highlighting)
                      ─→ NodeDetailsPanel (shows notes, games)
```

### 3.2 Data Hook (`useOpeningRepertoire.ts`)

- `currentTree` → React state, set via `setCurrentTree(data.tree)` from server
- `fetchTree(id)` → GET `/api/openings/repertoires/{id}` → returns `{ repertoire, tree }` where tree is backend's `build_tree()` output
- `addNode(parentId, san, uci, fen)` → POST `/api/openings/nodes` → returns **flat node** (no `children` array)

### 3.3 Backend (`openings.py`)

- `build_tree(nodes)` — takes flat list from Supabase, builds nested tree with `children` arrays
- `add_node()` endpoint — checks for existing child (by SAN or UCI), returns existing or creates new. Returns **flat node** (no `children`)
- `get_repertoire()` — fetches all nodes, calls `build_tree()`, returns nested tree

### 3.4 Component Roles

- **DebutBoard** — Stateless display. Receives `fen`, calls `onMove(from, to, piece, newFen, moveSan, moveUci)`
- **MoveNotation** — Receives `tree` (root) and `selectedNodeId`. Recursively renders. Uses `useMemo` on `[tree, selectedNodeId, onNodeSelect]`
- **page.tsx** — Orchestrator. Holds all state. Passes handlers down.

---

## 4. Full Data Flow Analysis

### 4.1 User Plays a Move on the Board

```
1. User drags piece → DebutBoard.handleDrop()
2. Chess.js validates move, computes new FEN
3. Calls onMove(from, to, piece, newFen, moveSan, moveUci)
4. → handleBoardMove() in page.tsx

handleBoardMove():
  a. setBoardFen(newFen)                     // optimistic board update ✅
  b. Check selectedNode.children for existing child with matching FEN
     - If found: setSelectedNode(existingChild) → DONE ✅
  c. If not found:
     - addNode(selectedNode.id, moveSan, moveUci, newFen)  // POST to server
     - Returns flat node (no children!)
     - setSelectedNode(newNode)              // ⚠️ newNode has no children
     - await fetchTree(selectedRepertoireId) // replaces currentTree
                                              // ⚠️ selectedNode now stale!
```

### 4.2 What Happens After fetchTree

```
fetchTree() → setCurrentTree(data.tree)     // NEW tree object
                                              // OLD selectedNode is orphaned
                                              // selectedNode.children = undefined
                                              // (it was the flat API response)
```

The `useEffect` that would normally sync:
```javascript
useEffect(() => {
  if (currentTree && !selectedNode) {   // ← selectedNode IS set (stale),
    setSelectedNode(currentTree);        //    so this NEVER fires
    setBoardFen(currentTree.fen);
  }
}, [currentTree?.id]);                   // ← only triggers when root ID changes
                                          //    (it doesn't change on re-fetch)
```

### 4.3 Resulting Broken States

After adding a move:
- `selectedNode` = flat API response (no `children`, not in tree)
- `currentTree` = freshly fetched tree (has the new node nested properly)
- `handleNext()` tries `selectedNode.children[0]` → **undefined** (flat node has no children)
- `handlePrev()` tries `findNode(currentTree, selectedNode.parent_id)` → **works** (ID lookup)
- `MoveNotation` gets `tree=currentTree` (correct) and `selectedNodeId=selectedNode.id` (correct ID, but the `onNodeSelect` callback gives nodes from the NEW tree)

**So the notation RENDERS correctly but selectedNode is disconnected from the tree.**

### 4.4 Navigation After a Move

- **Clicking a move in notation**: `onNodeSelect(node)` passes a node FROM the current tree → **WORKS** (fixes the desync)
- **Arrow keys (Next)**: Uses `selectedNode.children[0]` → **BROKEN** (flat node)
- **Arrow keys (Prev)**: Uses `findNode(currentTree, selectedNode.parent_id)` → **WORKS** (ID-based lookup)
- **Playing another move**: Uses `selectedNode.children?.find(...)` → **BROKEN** (no children on flat node, always creates new)

### 4.5 Duplicate Node Creation Risk

Because `selectedNode` after `addNode` has no `children`, the FEN-comparison check:
```javascript
const existingChild = selectedNode.children?.find(c => {
  const cFenParts = c.fen.split(' ').slice(0, 4).join(' ');
  const newFenParts = newFen.split(' ').slice(0, 4).join(' ');
  return cFenParts === newFenParts;
});
```
Always returns `undefined` → **always tries to create a new node**. The backend's duplicate check (SAN + parent_id) saves us from actual duplicates, but it's an unnecessary round-trip and the returned "existing" node is again flat.

---

## 5. Root Causes Identified

### RC1: **selectedNode holds a stale object reference after tree re-fetch** ⭐ PRIMARY

After `fetchTree()` replaces `currentTree`, the `selectedNode` still points to either:
- The flat API response from `addNode` (no children), or
- A node from the previous tree object (orphaned)

**Fix**: After every `fetchTree`, re-resolve `selectedNode` from the new tree by ID.

### RC2: **addNode API returns a flat node, not a tree node**

The backend's POST `/nodes` returns the row as inserted, without `children: []`. The frontend treats this as a tree node with navigation capabilities.

**Fix**: Either (a) always re-resolve from tree, or (b) ensure returned node has `children: []`.

### RC3: **No mechanism to re-sync selectedNode after tree refresh**

The only `useEffect` that syncs selectedNode to tree:
```javascript
useEffect(() => {
  if (currentTree && !selectedNode) { ... }
}, [currentTree?.id]);
```
This only fires when `selectedNode` is null AND `currentTree.id` changes. Neither condition holds after a normal addNode→fetchTree cycle.

**Fix**: Add a proper sync mechanism.

### RC4: **FEN comparison for duplicate detection is fragile**

The move-number and halfmove-clock fields are stripped (`.slice(0, 4)`), but this comparison happens on `selectedNode.children` which may be empty/stale.

**Fix**: The backend already handles dedup by SAN+parent_id. The frontend check is a nice optimization but only works if `selectedNode` has correct children.

### RC5: **useEffect dependency on `currentTree?.id` never re-fires**

The root node's ID doesn't change between fetches of the same repertoire. So the effect that sets initial selectedNode only works on the very first load.

---

## 6. Fix Plan — Exact Changes

### Fix 6.1: Re-resolve selectedNode after fetchTree (CRITICAL)

**File**: `frontend/src/app/debut/page.tsx`

**Change the `handleBoardMove` function:**

```typescript
const handleBoardMove = useCallback(async (
  from: string, to: string, piece: string, newFen: string, moveSan: string, moveUci: string
) => {
  if (!selectedNode || !selectedRepertoireId) return;

  // Optimistic board update
  setBoardFen(newFen);

  // Check existing children (works when selectedNode is properly resolved)
  const existingChild = selectedNode.children?.find(c => {
    const cFen = c.fen.split(' ').slice(0, 4).join(' ');
    const nFen = newFen.split(' ').slice(0, 4).join(' ');
    return cFen === nFen;
  });

  if (existingChild) {
    setSelectedNode(existingChild);
    return;
  }

  try {
    const newNode = await addNode(selectedNode.id, moveSan, moveUci, newFen);
    const newNodeId = newNode.id;

    // Fetch fresh tree
    await fetchTree(selectedRepertoireId);

    // ⭐ RE-RESOLVE: find the new node in the FRESH tree
    // We can't use currentTree here because fetchTree updates it asynchronously.
    // Instead, use a callback pattern or ref.
    // SEE Fix 6.2 for the proper mechanism.

  } catch (e: any) {
    setBoardFen(selectedNode.fen);
    setSnackbar({ open: true, msg: e.message, severity: 'error' });
  }
}, [selectedNode, selectedRepertoireId, addNode, fetchTree]);
```

### Fix 6.2: Add selectedNodeId tracking + useEffect to re-resolve (CRITICAL)

**File**: `frontend/src/app/debut/page.tsx`

Add a new state variable that tracks the *desired* node ID:

```typescript
const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
```

Add a useEffect that resolves `selectedNode` from tree whenever tree or selectedNodeId changes:

```typescript
// Re-resolve selectedNode from tree whenever tree changes
useEffect(() => {
  if (!currentTree) {
    setSelectedNode(null);
    return;
  }
  if (!selectedNodeId) {
    // No specific node requested — select root
    setSelectedNode(currentTree);
    setBoardFen(currentTree.fen);
    return;
  }
  // Find node by ID in the fresh tree
  const resolved = findNode(currentTree, selectedNodeId);
  if (resolved) {
    setSelectedNode(resolved);
    setBoardFen(resolved.fen);
  } else {
    // Node was deleted or not found — fall back to root
    setSelectedNode(currentTree);
    setBoardFen(currentTree.fen);
    setSelectedNodeId(currentTree.id);
  }
}, [currentTree, selectedNodeId, findNode]);
```

Then update `handleBoardMove` to set `selectedNodeId` instead of `selectedNode`:

```typescript
// In handleBoardMove, after addNode:
const newNode = await addNode(selectedNode.id, moveSan, moveUci, newFen);
setSelectedNodeId(newNode.id);  // ← track by ID
await fetchTree(selectedRepertoireId);
// The useEffect above will resolve selectedNode from the fresh tree
```

And update `handleNodeSelect`:
```typescript
const handleNodeSelect = useCallback((node: OpeningNode) => {
  setSelectedNodeId(node.id);
  setSelectedNode(node);    // immediate update for responsiveness
  setBoardFen(node.fen);
}, []);
```

### Fix 6.3: Remove stale useEffect that only works on first load

**File**: `frontend/src/app/debut/page.tsx`

**Remove this:**
```typescript
useEffect(() => {
  if (currentTree && !selectedNode) {
    setSelectedNode(currentTree);
    setBoardFen(currentTree.fen);
  }
}, [currentTree?.id]);
```

**Replace with the useEffect from Fix 6.2** which handles all cases (initial load, tree refresh, node deletion).

### Fix 6.4: Update navigation handlers for robustness

**File**: `frontend/src/app/debut/page.tsx`

The existing `handleNext`, `handlePrev`, etc. already work correctly IF `selectedNode` is a proper tree node (with `children`). Fix 6.2 ensures this. No changes needed to these handlers, but for safety:

```typescript
const handleNext = useCallback(() => {
  if (!selectedNode?.children?.length) return;
  const next = selectedNode.children[0];
  setSelectedNodeId(next.id);
  setSelectedNode(next);
  setBoardFen(next.fen);
}, [selectedNode]);
```

### Fix 6.5: Ensure addNode API response includes children array

**File**: `backend/api/openings.py`, function `add_node()`

After the insert, return the node with `children: []`:

```python
if result.data:
    node = result.data[0]
    node['children'] = []  # ← Ensure frontend can treat this as a tree node
    return jsonify(node), 201
```

Also for the existing-node return paths:
```python
if existing.data:
    existing.data[0]['children'] = []
    return jsonify(existing.data[0])
```

This is a **defense-in-depth** fix. The primary fix (6.2) makes this unnecessary, but it prevents confusion.

### Fix 6.6: Update MoveNotation useMemo dependencies

**File**: `frontend/src/components/openings/MoveNotation.tsx`

Currently:
```typescript
const elements = useMemo(() => {
  if (!tree) return [];
  return renderTree(tree, selectedNodeId, onNodeSelect, selectedRef);
}, [tree, selectedNodeId, onNodeSelect]);
```

This is actually correct — it re-renders when tree reference changes (it will after fetchTree) and when selectedNodeId changes. **No change needed**, but verify that `tree` comparison works by reference (it does, since `setCurrentTree` creates a new object).

### Fix 6.7: Update fetchTree to not reset selectedNode on repertoire change

**File**: `frontend/src/app/debut/page.tsx`

The existing effect:
```typescript
useEffect(() => {
  if (selectedRepertoireId) {
    fetchTree(selectedRepertoireId);
    const rep = repertoires.find(r => r.id === selectedRepertoireId);
    if (rep) {
      setBoardOrientation(rep.color === 'b' ? 'black' : 'white');
      setBoardFen(rep.starting_fen || STARTING_FEN);
      setSelectedNode(null);     // ← clears selectedNode
    }
  }
}, [selectedRepertoireId, fetchTree, repertoires]);
```

**Change to also clear selectedNodeId:**
```typescript
setSelectedNode(null);
setSelectedNodeId(null);    // ← ADD THIS
```

This way, when the tree loads for a new repertoire, the useEffect from Fix 6.2 will select the root.

---

## 7. Architecture Recommendations

### 7.1 Adopt Lichess's Path-Based Navigation (Future Enhancement)

For a **phase 2** improvement, consider adopting Lichess's path-based system:

```typescript
// Instead of storing a node reference, store a path
const [currentPath, setCurrentPath] = useState<string>('');

// Derive everything from the path
const selectedNode = useMemo(() => {
  if (!currentTree || !currentPath) return currentTree;
  return nodeAtPath(currentTree, currentPath);
}, [currentTree, currentPath]);
```

A path would be the concatenation of node IDs from root to current position: `root.id + child.id + grandchild.id`.

**Benefits:**
- Path survives tree re-fetches (IDs don't change)
- Single source of truth (path), everything derived
- Easy prev/next: `path.slice(0, -UUID_LENGTH)` for prev
- But: UUID-based IDs make paths very long (vs Lichess's 2-char IDs)

**Mitigation for long paths:** Use a simplified path scheme: store an array of node IDs `[rootId, childId, grandchildId]` instead of a concatenated string.

### 7.2 Optimistic Tree Updates (Future Enhancement)

Instead of re-fetching the entire tree after every move:

```typescript
const handleBoardMove = async (...) => {
  // 1. Create the node via API
  const newNode = await addNode(parentId, san, uci, fen);
  newNode.children = [];

  // 2. Optimistically insert into local tree
  const updatedTree = cloneTree(currentTree);
  const parent = findNode(updatedTree, parentId);
  if (parent) {
    parent.children = parent.children || [];
    parent.children.push(newNode);
  }
  setCurrentTree(updatedTree);
  setSelectedNode(newNode);
  setSelectedNodeId(newNode.id);

  // 3. Background sync (optional, periodic)
  // Skip the immediate fetchTree
};
```

This eliminates the server round-trip for the tree and matches Lichess's approach.

### 7.3 Summary of Changes by Priority

| Priority | Fix | File(s) | Effort |
|---|---|---|---|
| 🔴 P0 | 6.2: `selectedNodeId` + re-resolve useEffect | `page.tsx` | 30 min |
| 🔴 P0 | 6.1: Update `handleBoardMove` to use `selectedNodeId` | `page.tsx` | 15 min |
| 🟡 P1 | 6.3: Remove stale first-load useEffect | `page.tsx` | 5 min |
| 🟡 P1 | 6.7: Clear `selectedNodeId` on repertoire change | `page.tsx` | 5 min |
| 🟢 P2 | 6.5: Backend returns `children: []` | `openings.py` | 10 min |
| 🟢 P2 | 6.4: Update navigation handlers | `page.tsx` | 10 min |
| ⚪ P3 | 7.2: Optimistic tree updates | `page.tsx`, hook | 2 hours |
| ⚪ P3 | 7.1: Path-based navigation | Full refactor | 1 day |

**Minimum viable fix: P0 items only (45 min) — fixes the core sync issue.**

---

## Appendix: Lichess Source Files Referenced

- `ui/lib/src/tree/tree.ts` — TreeWrapper with `addNode`, `nodeAtPath`, `getNodeList`
- `ui/lib/src/tree/path.ts` — Path operations: `head`, `tail`, `init`, `last`, `contains`
- `ui/lib/src/tree/ops.ts` — Tree operations: `childById`, `merge`, `mainlineNodeList`
- `ui/lib/src/tree/types.ts` — `TreeNode` interface (id, ply, fen, san, uci, children)
- `ui/analyse/src/ctrl.ts` — AnalyseCtrl with `setPath`, `jump`, `addNode`, `userMove`, `sendMove`
- `ui/analyse/src/treeView/treeView.ts` — Notation rendering with path-based click handling
