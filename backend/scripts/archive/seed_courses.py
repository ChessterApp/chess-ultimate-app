"""
Seed Script for Chess Learning Platform
Populates courses, modules, and lessons tables with initial curriculum

Run with: python seed_courses.py
"""

import os
from datetime import datetime
from services.supabase_client import supabase

def seed_courses():
    """Seed the database with chess courses, modules, and lessons"""

    print("🌱 Starting database seeding...")

    # Course 1: Chess Fundamentals (Beginner)
    print("\n📚 Creating Course: Chess Fundamentals...")
    course_result = supabase.table('courses').insert({
        'title': 'Chess Fundamentals',
        'description': 'Master the essential building blocks of chess - from piece movement to basic tactics',
        'level': 'beginner',
        'order_index': 1,
        'estimated_hours': 8,
        'created_at': datetime.utcnow().isoformat(),
        'updated_at': datetime.utcnow().isoformat()
    }).execute()

    course_id = course_result.data[0]['id']
    print(f"✅ Course created with ID: {course_id}")

    # Module 1: Piece Mechanics
    print("\n📂 Creating Module: Piece Mechanics...")
    module_result = supabase.table('modules').insert({
        'course_id': course_id,
        'title': 'Piece Mechanics',
        'description': 'Learn how each chess piece moves and captures',
        'order_index': 1,
        'created_at': datetime.utcnow().isoformat(),
        'updated_at': datetime.utcnow().isoformat()
    }).execute()

    module_id = module_result.data[0]['id']
    print(f"✅ Module created with ID: {module_id}")

    # Lesson 1.1: The King
    print("\n📝 Creating Lesson: The King...")
    lesson_result = supabase.table('lessons').insert({
        'module_id': module_id,
        'title': 'The King - Royal Movement',
        'content': '''# The King

The King is the most important piece in chess - lose your king, lose the game!

## Movement
- Moves **one square** in any direction (horizontal, vertical, diagonal)
- Cannot move into check (a square attacked by an opponent's piece)

## Special Abilities
- **Castling**: The only move where the King moves two squares (we'll cover this later)

## Key Concept: Check vs. Checkmate
- **Check**: When the King is under attack
- **Checkmate**: When the King is in check and cannot escape - game over!

## Practice Exercise
The King starts on e1 (White) and e8 (Black). Try moving your King safely across the board while avoiding enemy pieces.
''',
        'lesson_type': 'theory',
        'order_index': 1,
        'exercise_fen': '8/8/8/3k4/8/8/8/3K4 w - - 0 1',
        'exercise_solution': ['Kd2', 'Kd3', 'Kd4'],
        'estimated_minutes': 10,
        'requires_lesson_id': None,
        'created_at': datetime.utcnow().isoformat(),
        'updated_at': datetime.utcnow().isoformat()
    }).execute()

    lesson_1_id = lesson_result.data[0]['id']
    print(f"✅ Lesson created with ID: {lesson_1_id}")

    # Lesson 1.2: The Queen
    print("\n📝 Creating Lesson: The Queen...")
    supabase.table('lessons').insert({
        'module_id': module_id,
        'title': 'The Queen - Most Powerful Piece',
        'content': '''# The Queen

The Queen is the most powerful piece on the board!

## Movement
- Moves **any number of squares** in any direction:
  - Horizontally (like a Rook)
  - Vertically (like a Rook)
  - Diagonally (like a Bishop)

## Key Points
- Cannot jump over other pieces
- Captures by landing on an opponent's square
- Usually worth about 9 pawns in value

## Strategy Tip
"Don't bring your Queen out too early!" - Beginners often develop the Queen first, but this makes it a target for opponent attacks. Develop Knights and Bishops first!

## Practice Exercise
Place your Queen on d4 and practice capturing pieces on different squares.
''',
        'lesson_type': 'theory',
        'order_index': 2,
        'exercise_fen': 'r1bqkbnr/pppp1ppp/2n5/4p3/3P4/8/PPP1PPPP/RNBQKBNR w KQkq - 0 1',
        'exercise_solution': ['Qd4', 'Qxe5+'],
        'estimated_minutes': 12,
        'requires_lesson_id': lesson_1_id,
        'created_at': datetime.utcnow().isoformat(),
        'updated_at': datetime.utcnow().isoformat()
    }).execute()

    print(f"✅ Lesson created")

    # Lesson 1.3: The Rook
    print("\n📝 Creating Lesson: The Rook...")
    supabase.table('lessons').insert({
        'module_id': module_id,
        'title': 'The Rook - The Tower',
        'content': '''# The Rook

The Rook (or Castle) is a powerful piece especially in endgames!

## Movement
- Moves **any number of squares** horizontally or vertically
- Cannot move diagonally
- Cannot jump over pieces

## Starting Position
- Each player has **two Rooks** in the corners (a1, h1 for White; a8, h8 for Black)

## Special Move: Castling
- The Rook participates in castling with the King
- King-side castling: Rook moves from h1 to f1 (White)
- Queen-side castling: Rook moves from a1 to d1 (White)

## Value
- Worth about 5 pawns
- Very strong in open positions and endgames

## Practice Exercise
Control open files with your Rooks - files with no pawns!
''',
        'lesson_type': 'theory',
        'order_index': 3,
        'exercise_fen': '4k3/8/8/8/8/8/8/R3K2R w KQ - 0 1',
        'exercise_solution': ['Ra8+', 'Kd7', 'Rh7+'],
        'estimated_minutes': 12,
        'requires_lesson_id': None,
        'created_at': datetime.utcnow().isoformat(),
        'updated_at': datetime.utcnow().isoformat()
    }).execute()

    print(f"✅ Lesson created")

    # Module 2: Basic Tactics
    print("\n📂 Creating Module: Basic Tactics...")
    module_result = supabase.table('modules').insert({
        'course_id': course_id,
        'title': 'Basic Tactics',
        'description': 'Learn fundamental tactical patterns to win material',
        'order_index': 2,
        'created_at': datetime.utcnow().isoformat(),
        'updated_at': datetime.utcnow().isoformat()
    }).execute()

    module_id = module_result.data[0]['id']
    print(f"✅ Module created with ID: {module_id}")

    # Lesson 2.1: The Fork
    print("\n📝 Creating Lesson: The Fork...")
    supabase.table('lessons').insert({
        'module_id': module_id,
        'title': 'The Fork - Attack Two at Once',
        'content': '''# The Fork

A fork is when one piece attacks two or more enemy pieces at the same time!

## How It Works
- Your piece attacks multiple targets simultaneously
- Opponent can only save one piece
- You win material!

## Common Forks
1. **Knight Fork**: Knights are fork masters! They can attack King and Queen simultaneously
2. **Pawn Fork**: Even pawns can fork two pieces
3. **Queen Fork**: The most powerful forks

## The Royal Fork
The **Knight fork on King and Queen** is called the "Royal Fork" - it wins the Queen!

## Example Pattern
```
Knight on e5 forks:
- King on g6
- Rook on c6
```

## Practice Exercise
Find the Knight move that forks the King and Rook!
''',
        'lesson_type': 'exercise',
        'order_index': 1,
        'exercise_fen': 'r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/3P1N2/PPP2PPP/RNBQK2R w KQkq - 0 1',
        'exercise_solution': ['Nxe5', 'Nxe5', 'Qe2'],
        'estimated_minutes': 15,
        'requires_lesson_id': None,
        'created_at': datetime.utcnow().isoformat(),
        'updated_at': datetime.utcnow().isoformat()
    }).execute()

    print(f"✅ Lesson created")

    # Lesson 2.2: The Pin
    print("\n📝 Creating Lesson: The Pin...")
    supabase.table('lessons').insert({
        'module_id': module_id,
        'title': 'The Pin - Restrict Movement',
        'content': '''# The Pin

A pin is when a piece cannot move without exposing a more valuable piece behind it!

## Types of Pins

### Absolute Pin
- The piece is pinned to the **King**
- Illegal to move (would put King in check)
- Example: Bishop pins Knight to King

### Relative Pin
- Pinned to a piece **more valuable** than itself
- Legal to move, but loses material
- Example: Bishop pins Knight to Queen

## Pin Masters
- **Bishops**: Pin along diagonals
- **Rooks**: Pin along files and ranks
- **Queens**: Pin in all directions

## How to Use Pins
1. Pin a piece to something valuable
2. Attack the pinned piece
3. It cannot move without losing material!

## Breaking Pins
- Move the piece behind the pin
- Block the pin with another piece
- Capture the pinning piece
- Counter-attack with a bigger threat

## Practice Exercise
Find the pin that wins material!
''',
        'lesson_type': 'exercise',
        'order_index': 2,
        'exercise_fen': 'r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 0 1',
        'exercise_solution': ['Bxf7+', 'Kxf7', 'Nxe5+'],
        'estimated_minutes': 15,
        'requires_lesson_id': None,
        'created_at': datetime.utcnow().isoformat(),
        'updated_at': datetime.utcnow().isoformat()
    }).execute()

    print(f"✅ Lesson created")

    # Course 2: Tactical Mastery (Intermediate)
    print("\n📚 Creating Course: Tactical Mastery...")
    course_result = supabase.table('courses').insert({
        'title': 'Tactical Mastery',
        'description': 'Sharpen your tactical vision with advanced patterns and combinations',
        'level': 'intermediate',
        'order_index': 2,
        'estimated_hours': 12,
        'created_at': datetime.utcnow().isoformat(),
        'updated_at': datetime.utcnow().isoformat()
    }).execute()

    course_id = course_result.data[0]['id']
    print(f"✅ Course created with ID: {course_id}")

    # Module 1: Advanced Patterns
    print("\n📂 Creating Module: Advanced Patterns...")
    module_result = supabase.table('modules').insert({
        'course_id': course_id,
        'title': 'Advanced Tactical Patterns',
        'description': 'Master sophisticated tactical motifs',
        'order_index': 1,
        'created_at': datetime.utcnow().isoformat(),
        'updated_at': datetime.utcnow().isoformat()
    }).execute()

    module_id = module_result.data[0]['id']
    print(f"✅ Module created with ID: {module_id}")

    # Lesson 1: Discovered Attack
    print("\n📝 Creating Lesson: Discovered Attack...")
    supabase.table('lessons').insert({
        'module_id': module_id,
        'title': 'Discovered Attack - Hidden Power',
        'content': '''# Discovered Attack

A discovered attack happens when moving one piece **reveals** an attack from another piece behind it!

## The Concept
```
1. Piece A blocks the line of attack from Piece B
2. Piece A moves away
3. Piece B's attack is "discovered" - revealed!
```

## Why It's Powerful
- Creates **two threats** with one move
- Opponent must deal with both threats
- Often wins material or delivers checkmate

## Special Types

### Discovered Check
- The discovered attack is a **check** on the King
- Most powerful type - opponent MUST respond to check
- Can win material freely with the moving piece

### Double Check
- Both the moving piece AND the discovered piece give check
- Only defense: move the King!
- Extremely powerful

## Example Pattern
```
White Bishop on c4, Queen on c1
White Knight on d3 blocks the diagonal
Knight moves to f4: Discovered attack on Black King!
```

## Practice Exercise
Find the discovered check that wins the Queen!
''',
        'lesson_type': 'exercise',
        'order_index': 1,
        'exercise_fen': 'r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/3P1N2/PPP2PPP/RNBQ1RK1 w kq - 0 1',
        'exercise_solution': ['Nxe5', 'd6', 'Nxc6'],
        'estimated_minutes': 20,
        'requires_lesson_id': None,
        'created_at': datetime.utcnow().isoformat(),
        'updated_at': datetime.utcnow().isoformat()
    }).execute()

    print(f"✅ Lesson created")

    print("\n✨ Database seeding completed successfully!")
    print(f"\n📊 Summary:")
    print(f"   - Courses: 2")
    print(f"   - Modules: 3")
    print(f"   - Lessons: 7")
    print(f"\n🚀 Your chess learning platform is ready to use!")

if __name__ == '__main__':
    try:
        seed_courses()
    except Exception as e:
        print(f"\n❌ Error during seeding: {str(e)}")
        print("\nMake sure:")
        print("1. Supabase credentials are set in .env")
        print("2. Database tables are created")
        print("3. You're running from the backend directory")
        exit(1)
