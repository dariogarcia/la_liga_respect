# Respect Rank: La Liga Coach Edition

## Overview
A system to rank La Liga managers based on their respect for referees during post-game interviews.

## Data Acquisition Pipeline
To ensure accuracy and avoid noise, the system follows a specific retrieval and trimming process:

### 1. Sources
The system targets sources that provide verbatim or near-verbatim post-game quotes:
- **Official La Liga Website**: Primary source for official press conference transcripts.
- **Major Spanish Sports Press**: AS.com, Marca.com, Sport.es, and Mundo Deportivo.
- **Club Official Channels**: Social media and official team websites.

### 2. Gathering Mechanism
The gathering is performed by an agentic process:
1. **Query Construction**: The agent builds queries using the format `"[Coach Name]" interview la liga [Match ID/Opponent] referee`.
2. **Source Filtering**: Only articles published within 48 hours of the match are considered.
3. **Quote Extraction**: An LLM scans the text to find specific sentences where the coach refers to the referee, officiating, or a specific decision.

### 3. Text Trimming & Cleaning
To prevent the grader from being biased by context or irrelevant noise, the text is trimmed as follows:
- **Isolation**: Only the specific quote referring to the referee is extracted (e.g., removing the journalist's question).
- **De-noising**: Removal of filler words and irrelevant anecdotes that do not impact the respect level.
- **Concatenation**: If a coach makes multiple remarks about the referee in one interview, these are merged into a single block of text for that specific game.

## Grading System
We implement two scoring systems: **Separate** (absolute) and **Competitive** (relative).

### Separate Mode Points Allocation
- **3 Points (Respectful):** The coach acknowledges the referee's difficulty, avoids blaming them for the result, or praises the officiating.
- **1 Point (Neutral):** The coach mentions the referee neutrally or expresses disagreement without aggression or accusations of bias.
- **0 Points (Disrespectful):** The coach openly criticizes the referee, implies bias, uses aggressive language, or calls for sanctions.

### Competitive Mode Points Allocation
- **Win (3 pts)**: The coach's quote is more respectful than their opponent's.
- **Draw (1 pt)**: Both coaches' quotes are similarly respectful or disrespectful.
- **Loss (0 pts)**: The coach's quote is less respectful than their opponent's.

## System Architecture
1. **Collection Agent:** Searches for and trims post-game interviews.
2. **Database:** Stores match data, trimmed quotes, and assigned scores.
3. **Grading Engine:** An LLM-based grader that evaluates trimmed text against the criteria.
4. **Leaderboard:** A processed view of the database calculating total points.

## Data Schema
- `games.json`: List of games, dates, and participating teams/coaches.
- `comments.json`: Collection of coach quotes linked to a game ID.
- `leaderboard.json`: Current ranking (Separate).
- `leaderboard_competitive.json`: Current ranking (Competitive).
