## Last State (when I stopped)
- What I was working on: Implementing per-project run counters and "Run N / Step M" PR + branch naming.
- What I last ran/tested: No new tests run after the naming update.
- What broke or scared me: None observed.
- What question I was trying to answer: Are run numbers persisted and reflected in PR titles/branches across multiple runs?

## Next Safe Step (≤30 min)
- Run the same project twice and verify PR titles show Run 1 / Step 1 then Run 2 / Step 1, and branch names include run numbers.

## Things I explicitly decided NOT to solve yet
- Automating additional PR metadata beyond run/step naming.
- Adding additional run state fields beyond run_number.
