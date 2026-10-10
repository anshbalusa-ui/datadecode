# Interview Prep - DECODE Competition Intelligence Project

## 30-second explanation

I built a Python pipeline that cleans the scouting data, aggregates each team's six matches, and creates separate rankings for overall robot strength and compatibility with Team 3470. I intentionally did not use machine learning because the dataset is small and an explainable percentile-based model is easier to defend. The biggest 3470 finding is that we're fast and mechanically reliable, but our scoring volume is only mid-field and our cycle time gets worse late in the sample, which matches repeated notes about the overflow mechanism slowing down.

## The 11 things you need to know cold

1. **109 raw rows became 108.** `M23-T09-4` was an exact duplicate, so I removed one copy.
2. **I did not blindly delete outliers.** I flagged them and kept the raw values unless the data gave a strong reason not to use them analytically.
3. **The big suspicious row is T05, M14-T05-3.** It says 28 CL while T05's other usable CL values are 6-7, and scout confidence is only 2/5. I kept 28 in the cleaned data but excluded that CL value from the composite.
4. **T12 speed is uncertain.** Two cycle times are missing and one is an extreme 7.5 s observation.
5. **Alliance score/wins are NOT in the robot-strength score.** They include teammate and opponent effects, so using them as individual performance would be misleading.
6. **Overall score = 45% scoring volume + 15% objectives + 15% speed + 15% reliability + 10% defense.** Each input is converted to a field percentile first.
7. **T08 is #1 overall.** It is #1 in all three sensitivity weightings, which is why confidence is high.
8. **3470 is #6 overall.** Strengths: 88th-percentile speed, zero breakdowns, 100% auto leave. Weaknesses: CL 41st percentile, depot 35th, defense 41st, motif 50%.
9. **3470's cycle time gets ~41.5% slower from the first two matches to the last two:** 12.40 s -> 17.55 s. The note `overflow mechanism slows late event` appears 3/6 times.
10. **Best partners for 3470:** T08, T14, T17, T02, T06. Compatibility is a separate model, not just a copy of overall rank.
11. **Match-prefix ambiguity:** All 36 `M##` prefixes are reused across three observations and have different scorelines for the same alliance color. Six prefixes even contain three observations with the same color. That does **not** prove which row is wrong; the prefix may not be a global match ID. We therefore do not group rows by `M##`, and win-context over/underrating labels are provisional.

## Likely questions + clean answers

### Why did you use percentiles?
The columns use different units: seconds, counts, rates, and 1-5 ratings. Percentiles put them on a common 0-100 scale without pretending one raw unit is directly comparable to another.

### Why those weights?
I wanted offense to matter most, so scoring volume is 45%. Objectives, speed, and reliability are each 15%, and defense is 10%. I also tested offense-heavy and reliability-heavy alternatives. T08 stays #1 in all three, while teams like T14/T02 move more, which is why their rank confidence is lower.

### Why no ML?
There are only six observations per team and 18 teams. A model would be harder to explain and more likely to overfit. The rubric also says not to use ML if a simpler explainable method is better.

### What does reliability actually mean?
It combines five signals: low breakdown rate, high driver consistency, low penalties, low scoring-action variability, and low cycle-time variability. Lower variability/penalties/breakdowns are converted so higher percentile is always better.

### Why is T08 #1 if its cycles are slow?
Because it makes up for that with high scoring volume, the best defense rating in the field, strong objectives, zero breakdowns, and a very high action floor. The model still penalizes its slower cycles and low driver consistency.

### Why isn't the best overall team automatically the best 3470 partner?
Because the partner model asks a different question: what fills 3470's gaps. It gives extra weight to CL, depot, defense, motif, reliability, flexibility, and risk. In this dataset T08 happens to be #1 in both because its scoring and defense complement 3470 really well.

### What's the strongest evidence behind the 3470 recommendation?
Cycle time goes from an average 12.40 s in matches 1-2 to 17.55 s in matches 5-6, and the exact same overflow-slowdown note appears three times late in the sample. That is why I would test that subsystem first.

### Could the overflow mechanism conclusion be wrong?
Yes. Defense, traffic, battery state, or match strategy could also explain the slowdown. That's why I label the causal claim Medium confidence and recommend testing/telemetry before redesigning.

### What's the weirdest data issue?
T05's 28 CL row. It is a huge outlier and has the lowest scout confidence in the dataset. I did not erase it; I preserved the raw observation, flagged it, and prevented it from distorting the CL aggregate.

### What team looks underrated?
T14. It is #2 on underlying robot metrics but only #13 on the separate result-context ranking. That suggests its raw match outcomes undersell its individual profile, although partner/opponent information would be needed to prove why.

### What team looks overrated by results?
T11. It is #18 in the individual robot composite but #8 in result context. That is exactly why I refused to use win rate as individual robot strength.

### What about conflicting match identifiers?
The identifier `M02-3470-1` contains an `M02` prefix, but other rows with `M02` and the same alliance color show different scores. Without a verified event schedule, I can't claim that prefix means a single official match. I wrote a dataset-level diagnostic and did not merge those rows, because robot-level counts are otherwise independently identified. I would ask the organizer for the official match-key definition and score sheet before making strong win-context claims.

### What would you collect next?
Official global match IDs and score sheets, alliance partner/opponent identities, official action point values, complete cycle timestamps, multiple scouts per match, match video for the T05 outlier and 3470 slowdown, and phase-specific telemetry/jam counts.

## 5-minute verification you should do before the interview/submission

- Open `data/DECODE_Candidate_1_cleaned.xlsx` and find `M23-T09-4`: confirm there is only one copy.
- Find `M14-T05-3`: confirm raw `cl_scored = 28`, `analysis_excluded_from_cl = 1`, and scout confidence = 2.
- Open `outputs/team_rankings.csv`: confirm T08 #1 and 3470 #6.
- Open `outputs/compatibility_ranking_3470.csv`: confirm the top five are T08, T14, T17, T02, T06.
- Open the six 3470 rows and personally verify the cycle times: 11.9, 12.9, 16.3, 14.0, 16.5, 18.6.

Once you've done those checks, you can truthfully say you personally verified the major cleaning decisions, rankings, and Team 3470 trend.
