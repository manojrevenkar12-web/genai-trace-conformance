# 3. Measure the checks with planted faults and harmless changes

**Status:** accepted

The checks are only useful if they catch the bugs integrations really ship and stay quiet otherwise. Each fault kind is
a class of real Langfuse integration issue, planted into clean traces captured from the real SDKs. Recall on the kinds
the checks were written for is high by construction, so two real kinds without a check (zero latency, a missing
completion start time) are planted too, to show where the lab stops. Harmless changes (reordered exports, extra HTTP
client spans, extra attributes, renamed spans, 3 ms clock skew) must raise no alarm; the first version of the matching
raised two on clock noise, which led to the one-to-one matching in ADR 2. Clock error is modelled as one offset per host: independent noise larger than the gap between two identical calls makes them indistinguishable to any backend, which a first CI run on a faster machine showed.
