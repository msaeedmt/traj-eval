# Presentation Planning

## Must-Haves

- Build a 10-minute, two-part talk—five minutes on scientific-agent architecture and five minutes on trace-based failure analysis.
- Keep the architecture section concise—explain the Reasoner–Engineer–Critic workflow, tools, and validation boundary without implementation overload.
- Cover four observed Qwen 3.5 failure patterns—linear handoffs without revision, repeated retrieval until budget exhaustion, statement drift, and critic approval without independent validation.
- Ground every failure claim in a real trial and event—use trace IDs, exact excerpts, and evidence from the local Lean failure report.
- Use readable failure visuals—show the relevant trace or graph excerpt and pair it with one clear takeaway instead of dense prose.

## Presentation Ideas

- Reduce the deck to one message per slide—fewer slides and shorter copy will keep both speakers inside the 10-minute limit.
- Make the speaker handoff explicit—an architecture-to-evidence transition will clarify where the first five minutes end and the failure analysis begins.
- Reuse one visual grammar for all four failures—show Trigger → Agent action → Missing check → Consequence so patterns are easy to compare.
- Add compact evidence footers—trial ID, event number, outcome, and source make claims verifiable without distracting from the story.
- Rewrite titles as conclusions—takeaway headlines will let the audience follow the argument even when technical details move quickly.

## Fun

- Animate one trace step by step—progressive reveal could make the handoff failure intuitive without adding more text.
- Add a “what should have happened” path beside the observed trace—a counterfactual route can turn each failure into an architecture lesson.
- Keep full traces in an appendix—extra evidence will support questions without crowding the main talk.
- End with one redesign challenge—ask which control would prevent the most failures and use it to open discussion.
