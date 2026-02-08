## Demo 1 Voiceover Script (TTS-friendly)

**Video:** browser-use + SentienceDebugger (sidecar verification)  
**Recording modes:** `DEMO_MODE=fail` then `DEMO_MODE=fix`  

### Scene 0 — Hook (10–15s)
Browser agents do not usually crash.  
They drift into the wrong state.  
In this demo, I will attach SentienceDebugger to a browser-use agent.  
Then I will show a failure in Sentience Studio, and fix it with deterministic verification.

### Scene 1 — What SentienceDebugger is (15–25s)
SentienceDebugger is a verifier-only sidecar.  
Your agent still plans and executes actions.  
SentienceDebugger takes snapshots, runs assertions, and uploads a trace you can inspect in Sentience Studio.

### Scene 2 — Run the agent with a failing verification (20–35s)
First, I run the agent in fail mode.  
This forces a required assertion to fail.  
The goal is to generate a trace that clearly shows what happened.

Key idea: the vision-based agent can finish and still be wrong.  
Sentience does not trust completion.  
Sentience requires proof.

### Scene 3 — Open the trace in Sentience Studio (45–75s)
Now I open the run in Sentience Studio using the run_id.  
I can see each step, the recorded actions, the snapshot state, and the verification results.  
Instead of guessing, I can prove why the step failed.

In the trace, notice this contrast:  
the agent claims success, but the required verification fails.  
That is how we prevent silent drift.

### Scene 4 — Fix: make success conditions explicit (30–45s)
The fix is not a sleep.  
The fix is to verify the correct outcome.  
For example: confirm we are on the results page and we can extract five items in the expected shape.

### Scene 5 — Rerun in fix mode (20–35s)
Now I rerun the exact same demo in fix mode.  
This time the required checks pass.  
The agent produces a deterministic output, and the trace is uploaded for review.

### Scene 6 — Takeaways + CTA (15–25s)
Three takeaways.  
One: snapshots reduce ambiguity.  
Two: assertions prove progress.  
Three: traces make failures actionable.  
If you build browser agents and care about reliability, start by adding verification to your loop.

