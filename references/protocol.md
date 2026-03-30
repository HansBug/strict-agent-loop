# Protocol

Use this protocol when the current task is large enough, ambiguous enough, or quality-sensitive enough that Codex might otherwise compress the middle.

## Controller and Executor

- Keep the current agent as the controller.
- Keep exactly one persistent executor subagent per active loop.
- Let the controller decide scope, stop conditions, verification, and recovery.
- Let the executor do only one atomic task at a time.

## Loop Contract

Define the contract before iteration 1:

- `goal`
- `global_stop_condition`
- `workspace_root`
- `success_evidence`
- `blocker_definition`
- `hard_limits`

Do not continue if any of those fields is missing or materially unclear.

## Atomicity Rules

A task is atomic only if all of these are true:

- it has one clear output
- it can be verified with one short check
- failure is easy to localize
- recovery does not require replaying the whole loop

If a proposed iteration sounds like a milestone, it is too large.
If it sounds like one command, one file change, or one bounded diagnosis, it is probably fine.

## Required User-Facing Announcement

Before dispatching each round, tell the user:

- `Iteration N`
- `This round`
- `Local done condition`
- `Global stop condition`
- `Stop after this round if`

This is mandatory. Do not hide the current loop state.

## Required Controller Actions After Each Round

1. Inspect the changed files or command output yourself.
2. Verify the result.
3. Append one history entry to the state file.
4. Refresh the compact snapshot if needed.
5. Re-check whether the loop should stop.

## Hard Stop Conditions

Stop the loop immediately if:

- the global stop condition is met
- `max_iterations` is reached
- `max_no_progress_rounds` is reached
- the user changes scope
- a real blocker makes safe progress impossible

## Recovery

If the executor disappears or loses context:

1. compact the state
2. spawn a replacement executor
3. send the compact snapshot plus the current task
4. keep the same controller and the same state file

Do not silently restart from iteration 1.
