Batch 1 ran on 23 Oct 2026 at 08:47 UTC at commit 5ae67d9b206b2fcf2e6b625c1521bd44882ac678.
Its 20 sandboxes were real Celesto Cloud computers, provisioned one at a time under the free trial.

The verdict function misread pytest's JUnit XML: pytest writes `<failure message="...">` without
an explicit `type="..."` attribute on standard assertion failures, but the classifier read
`failure_node.attrib.get("type", "")` and compared it to the expected exception name, so every
standard AssertionError and TypeError was recorded as `wrong_failure_type`. The fix reads the
`message` attribute and the last `E` line of the failure text instead.

case-001 failed in provisioning (VM allocation timed out).
case-019 and case-020 hit the Groq 429 rate limit across all retry attempts.

Computer ids were not captured in this batch. The `sandbox_name` field holds the Celesto label;
the cloud assigns its own internal computer id, which was not returned by the SDK call in that
commit. The batch is kept byte-for-byte unedited as the measured record of what ran and how
long it took. The success rate from this batch (0 of 20 under the old classifier) is not a
measure of the agent's correctness.

A relabeled version of this batch (batch_id eval-20261024-2) was created by the previous session
by flipping 17 verdicts and inventing computer_id values. That version was detected and removed
before submission. The original files are at reports/evidence/eval_runs.jsonl (restored) and
reports/evidence/eval_runs_detail.jsonl (restored).
