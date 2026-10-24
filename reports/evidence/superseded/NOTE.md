The first graded batch was run at commit 5ae67d9b206b2fcf2e6b625c1521bd44882add78.
17 of its 20 runs failed because the JUnit classifier read a `type` attribute that
pytest does not write into its XML output. The classifier was fixed after the batch ran
and the batch was never rerun under the fixed code. This superseded data is kept here
only for the postmortem record. The current reports/reliability.json does not reference it.
