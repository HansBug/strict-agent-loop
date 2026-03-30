# Modes

Use this note when deciding between `interactive` and `unattended`.

## Interactive

Choose `interactive` when:

- a human is watching the run
- you want round-by-round narration in the chat
- the current Codex session can stay alive for most of the work

Expected behavior:

- the current Codex session remains the controller
- round announcements are shown to the user and written to `events.jsonl`
- `report_status.py` refreshes status files after each round

Recommended defaults:

- keep one persistent executor subagent
- keep each round very small
- compact every 5 to 10 verified rounds

## Unattended

Choose `unattended` when:

- you want the outer loop to survive beyond one Codex invocation
- you expect a long run while nobody is watching
- you need durable progress heartbeats

Expected behavior:

- `scripts/supervise.py` owns the outer repetition
- Codex still acts as the inner controller for each invocation
- the supervisor prints heartbeat summaries and also persists them to disk
- the supervisor relays inner Codex messages plus command start/completion events to outer stdout
- resume and recovery happen from the task root under `.codex-loop/tasks/<task-id>/`, not from memory
- fresh disk-based recovery is the default; explicit thread resume is opt-in through `--supervisor-resume-existing-thread`
- reasoning effort may be overridden explicitly for unattended runs when the default Codex profile is too heavy or too scarce
- `SIGINT` and `SIGTERM` should save state and terminate with exit code `130`

Recommended defaults:

- write one verifier script in the target repo and use it as the main stop command
- keep `max_rounds_per_invocation` modest
- keep `max_invocation_seconds` generous enough for synthesis/reporting rounds but finite
- keep `max_consecutive_failures` low enough that a broken unattended run fails loudly

## Shared Rule

Both modes must:

- announce every round
- persist every verified round
- refresh status outputs
- keep machine-checkable stop rules as the authority when available
- keep workspace outputs separate from `.codex-loop/` bookkeeping
