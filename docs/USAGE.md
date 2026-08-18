# Respect Rank Usage Guide

This guide describes the functionalities of the Respect Rank system and how to use them.

## Quick Start
To run the complete pipeline (Collect $\rightarrow$ Grade $\rightarrow$ Rank), execute the main script:

```bash
export PYTHONPATH=$PYTHONPATH:$(pwd)
python3 src/main.py
```

To display the standings:
```bash
python3 src/display.py [separate|competitive]
```

## Functional Components

### 1. Data Collection (`src.collection.collector`)
Gathers post-game coach interviews and stores them in `data/comments.json`.

- **Function:** `collect_matchday_comments()`
- **Output:** A "Collection Report" showing matches processed, comments sought, and found.

### 2. Grading & Ranking (`src.grading.grader`)
Analyzes quotes and updates two types of leaderboards.

- **Function:** `update_leaderboard()`
- **Grading Modes**:
    - **Separate**: Absolute grading (0, 1, 3) based on quote content.
    - **Competitive**: Relative grading (winner gets 3, draw gets 1).
- **Output:** A "Grading Report" showing total quotes processed.

### 3. Visualization (`src.display`)
Displays a formatted table of the standings.

- **Script:** `src/display.py`
- **Columns**: Position, Team, Total Points, Games Played (GP), Home Points, Away Points.

### 4. Data Management (`src.data.manager`)
Utility layer for JSON storage.

- **Files**: `games.json`, `teams.json`, `comments.json`, `leaderboard.json`, `leaderboard_competitive.json`.

## Grading Criteria
- **3 Points**: Respectful/Empathetic towards referees.
- **1 Point**: Neutral/Objective disagreement.
- **0 Points**: Disrespectful/Aggressive/Accusatory.
