# 5. Run the lab nightly on releases and on each framework's main branch

**Status:** accepted

Most tracing breakage arrives in a framework release the integration does not control. Waiting for a user report costs
the days until someone notices, plus a manual reproduction and bisect. The simulation compares that with nightly runs on
new releases, nightly runs that also install main branches, and the triage agent; the lab combines all three. Main-branch
runs are the part that turns findings into fixes before release; they depend on frameworks landing changes on main days
ahead, which `config/world.json` states as an assumption per framework.
