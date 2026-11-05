---
name: ui-ux-pro-max
description: >-
  UX heuristics and interaction patterns for an academic similarity-review tool: information hierarchy,
  progressive disclosure, feedback, forms, data tables, comparison views. Use for flow and usability decisions.
---

# UI/UX pro max — reviewer-centred design

## Users
Instructors and reviewers scanning batches (up to 50 files), and students checking one file. They need fast triage,
trustworthy evidence, and no accidental false accusations.

## Information hierarchy
1. Verdict level: flagged pairs ranked by similarity, per-document Similarity Index.
2. Evidence level: side-by-side `ComparisonInspector` with highlighted spans and match navigator.
3. Detail level: matrix heatmap, source breakdown, exports (CSV, HTML, PNG, PDF).
Show 1 by default; reveal 2 and 3 on demand (progressive disclosure).

## Interaction heuristics
- **Visibility of status:** upload progress, then processing, then ready; never an unexplained spinner.
- **Control and freedom:** cancel an in-flight scan; delete a saved scan with confirmation.
- **Error prevention:** validate file type/size/count at drop time with specific messages.
- **Recognition over recall:** the mode switch states which extensions it accepts.
- **Consistency:** one definition of "flagged" (`risk.ts`), same threshold everywhere.
- **Fairness:** wording says "similarity", not "plagiarism". Show what was excluded (`min_match_words`) so the score is explainable.

## Patterns
- Forms: label above input, helper text for units (threshold as %), inline validation after blur, primary action disabled only with a stated reason.
- Lists: sortable by score, keyboard row navigation, row click opens the inspector.
- Heatmap: cell = pair; hover/focus tooltip with names and score; click opens comparison.
- Empty / first run: one sentence plus a hint about the sample files.
- Mobile: results stack; inspector panes become tabs.

## Test with tasks
"Find the most similar pair in 20 files", "reopen last week's scan", "export evidence for one pair", "scan one reference against 10 candidates".
Each should take three clicks or fewer from landing.
