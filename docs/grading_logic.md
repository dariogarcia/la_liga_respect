# LLM Grading Mechanism: Respect Level

This document details the logic and the specific prompt used by the LLM agent to grade coach comments.

## 1. The Agentic Grading Workflow

Unlike automated keyword matching, the system relies on an **LLM Agent-in-the-Loop**. The Python codebase handles the mathematical aggregation of scores, but the semantic analysis is performed by the Agent.

### The Process:
1. **Extraction**: The Agent identifies pending quotes in `data/pending_requests.json` and fetches the text.
2. **Analysis**: The Agent applies the Rubric (below) to each quote, detecting nuance, sarcasm, and sentiment.
3. **Assignment**: The Agent writes a `score` (0, 1, or 3) directly into the `comments.json` object for each entry.
4. **Aggregation**: `src/grading/grader.py` reads these pre-assigned scores to generate the rankings.

### Scoring Rubric
- **3 Points (Respectful)**: 
    - Coach acknowledges the difficulty of the job.
    - Explicitly states that the referee's decisions are final/respectable.
    - Avoids blaming the referee for the match outcome.
- **1 Point (Neutral)**:
    - Mentions the referee but without emotional charge.
    - Expresses a difference of opinion on a decision without using aggressive language.
    - The tone is professional and objective.
- **0 Points (Disrespectful)**:
    - Accuses the referee of bias or incompetence.
    - Uses sarcastic or aggressive language.
    - Claims the match was "stolen" or "robbed".
    - Calls for sanctions against the officiating crew.

## 2. The System Prompt for Agents
When an agent is tasked with grading, it should follow this internal logic:

> **System Prompt:**
> You are an expert analyst of sports psychology and a specialist in La Liga football. Your task is to evaluate the level of respect a coach shows toward the referee in a post-game interview.
>
> **Instructions:**
> 1. Analyze the provided text for tone, sentiment, and specific keywords.
> 2. Assign a score based on the strict rubric above.
> 3. You MUST NOT assign any value other than 0, 1, or 3.
> 4. If a coach does not mention the referee at all, the quote is ignored and not graded.
> 5. **Sarcasm Detection**: A statement like "The referee did a *fantastic* job of ruining our game" is graded as **0**, not **3**.
> 6. **Precedence**: If a coach is respectful in one sentence but aggressive in another, the **lowest score** takes precedence.

## 3. Competitive Mode Derivation
The Competitive Leaderboard takes the absolute scores assigned by the agent for two coaches in the same game:
- `Coach A (3) vs Coach B (1)` $\rightarrow$ Coach A wins (3 pts), Coach B loses (0 pts).
- `Coach A (1) vs Coach B (1)` $\rightarrow$ Draw (1 pt each).
- `Coach A (0) vs Coach B (0)` $\rightarrow$ Draw (1 pt each).
