# 2. Checks compare what a backend would show with what the provider charged

**Status:** accepted

A trace can look plausible and still be wrong: two generations for one call, cache reads billed as fresh input. The
checks therefore compare the mapped observations with the server's ledger, call by call. A generation should enclose
the request it represents, so generations are matched to calls by how far each call falls outside a generation's span,
one generation per call, with the assignment chosen for the whole run at once; only then are leftover generations
attached as duplicates. Closest-pair matching was tried first and swapped two calls a few milliseconds apart once a
3 ms clock skew was applied; the whole-run assignment does not.

The mapping from spans to observations is a reference written from the specifications (OpenTelemetry GenAI conventions,
OpenInference, Langfuse's usage_details keys), not Langfuse's server code. Where the specifications leave room, the lab
reports the ambiguity (non-standard attribute names, several names for one quantity) rather than guessing.
