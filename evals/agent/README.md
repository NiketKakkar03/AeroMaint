# Agent evaluation

`tests/contract/agent/test_workflow.py` executes the golden classifications,
tool selections, grounding/citation audit, prompt-injection refusals, budget
limits, and approval state transitions. Numerical claims are accepted only when
their evidence was captured from a tool registered as `trusted_numeric`.

Current documented gap: the default repository persists for the lifetime of one
API process. Its interface is intentionally replaceable with a database adapter
when the production database contract is selected.
