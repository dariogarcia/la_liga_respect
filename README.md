# 🏆 Respect Rank: La Liga Coach Edition

Respect Rank is an agentic system designed to monitor and rank La Liga football managers based on their level of respect for referees during post-game interviews.

## 🌟 Overview

The system transforms qualitative interview data into a quantitative leaderboard, mimicking the structure of official league standings. It allows users to track which coaches maintain professionalism and which are frequently critical of officiating.

## 🛠️ Core Functionalities

### 1. Data Collection
The system identifies pending matches from the calendar and searches for post-game comments from both the home and away coaches.
- **Output**: A `Collection Report` detailing how many quotes were successfully retrieved.

### 2. Dual Grading Systems
To provide a comprehensive view, the system implements two distinct scoring methodologies:
- **Separate Mode (Absolute)**: Each coach is graded independently.
    - `3 pts`: Respectful/Empathetic.
    - `1 pt`: Neutral/Objective.
    - `0 pts`: Disrespectful/Aggressive.
- **Competitive Mode (Relative)**: Coaches are compared head-to-head for each match.
    - The more respectful coach wins `3 pts`.
    - If both are equally respectful/disrespectful, both receive `1 pt`.
    - The less respectful coach receives `0 pts`.

### 3. Professional Standings
Displays a formatted leaderboard including:
- **Position (Pos)**: Rank based on total points.
- **Team**: The coach's team.
- **Total**: Cumulative points.
- **Games Played (GP)**: Total games processed for that team.
- **Home/Away**: Points earned specifically in home or away matches.

## 🚀 Getting Started

### Prerequisites
- Python 3.x
- External Dependencies: `requests` (install via `pip install -r requirements.txt`)

### Setup
Clone the repository and ensure your `PYTHONPATH` is set to the root directory:
```bash
export PYTHONPATH=$PYTHONPATH:$(pwd)
```

## 🔄 Operational Guide: Keeping the Leaderboard Updated

To keep the rankings current as the season progresses, follow these steps:

### Step 1: Update the Calendar
Add new upcoming or completed games to `data/games.json`. Ensure you include the correct `game_id`, `home_coach`, and `away_coach`.

### Step 2: Run the Update Pipeline
Execute the main script to collect new interviews and recalculate the scores:
```bash
python3 src/main.py
```
This command will:
1. Scan `data/games.json` for new matches.
2. Fetch quotes for the coaches.
3. Update both the **Separate** and **Competitive** leaderboards in `data/`.

### Step 3: View the Standings
Use the display tool to see the current rankings.

**For the Separate Leaderboard:**
```bash
python3 src/display.py separate
```

**For the Competitive Leaderboard:**
```bash
python3 src/display.py competitive
```

## 📂 Project Structure
- `src/collection/`: Logic for interview retrieval.
- `src/grading/`: Scoring algorithms and ranking logic.
- `src/data/`: JSON database management.
- `src/display.py`: CLI visualization tool.
- `data/`: JSON files (`games.json`, `teams.json`, `comments.json`, etc.).
- `docs/`: Design specifications and usage guides.
