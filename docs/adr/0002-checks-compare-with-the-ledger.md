# 2. Checks compare what a backend would show with what the provider charged

**Status:** accepted

A trace can look plausible and still be wrong: two generations for one call, cache reads billed as fresh input. The
checks therefore compare the mapped observations with the server's ledger, call by call. Generations are matched to calls
by the time window they enclose, one per call first (closest pairs), and only then are leftovers attached as duplicates,
so two calls a few milliseconds apart cannot swap.

The mapping from spans to observations is a reference written from the specifications (OpenTelemetry GenAI conventions,
OpenInference, Langfuse's usage_details keys), not Langfuse's server code. Where the specifications leave room, the lab
reports the ambiguity (non-standard attribute names, several names for one quantity) rather than guessing.
