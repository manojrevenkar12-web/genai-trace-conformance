# 4. Score the triage agent on the maintainers' own labels, split by date

**Status:** accepted

The triage agent is scored against the `integration-*` labels Langfuse's maintainers put on their issues, not labels
written for this project. Its rules were written on issues created before the split date in `config/triage.json`; the
issues after it are the held-out set. The labels are incomplete (some LangChain-handler issues carry no integration
label), so precision against them is a lower bound. The baseline is "label it if the framework is mentioned anywhere".
