# Respect Rank: La Liga Coach Edition

## Overview
A system to rank La Liga managers based on their respect for referees during post-game interviews.

## Grading System
We will use a **Separate** scoring system. Each coach's score is independent of their rival.

### Points Allocation
- **3 Points (Respectful):** The coach acknowledges the referee's difficulty, avoids blaming them for the result, or praises the officiating.
- **1 Point (Neutral):** The coach mentions the referee neutrally or expresses disagreement without aggression or accusations of bias.
- **0 Points (Disrespectful):** The coach openly criticizes the referee, implies bias, uses aggressive language, or calls for sanctions.

## Data Sources
- Official La Liga website (interviews)
- Sport.es / Mundo Deportivo (Spanish sports press)
- AS.com / Marca.com
- Official team social media/websites

## System Architecture
1. **Collection Agent:** A tool that searches for post-game interviews for specific match-days.
2. **Database:** Stores match data, interview transcripts, and assigned scores.
3. **Grading Engine:** An LLM-based grader that evaluates text against the grading criteria.
4. **Leaderboard:** A processed view of the database calculating total points.

## Data Schema
- `games.json`: List of games, dates, and participating teams/coaches.
- `comments.json`: Collection of coach quotes linked to a game ID.
- `leaderboard.json`: Current ranking.
