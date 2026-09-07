# Profile authoring protocol

A thematic profile is an explicit, reviewable semantic definition for one snapshot/workflow. It is not assumed to be globally complete.

Recommended process:

1. **Scan the target snapshot.** Build the input-specific key/value, geometry, layer and lifecycle inventory.
2. **Inspect observed distributions.** Search relevant keys/values and their counts instead of beginning only from a fixed tag list.
3. **Consult domain and OSM knowledge.** Use OSM documentation, domain expertise and, when useful, external services such as Taginfo or ohsome as contextual evidence.
4. **Encode explicit rules.** Separate confirmed, lifecycle, exclusion and contextual-candidate logic. Avoid silently promoting weak contextual objects into confirmed classes.
5. **Review outcomes.** Inspect category totals, geometry distribution, deterministic quality samples and representative complete tags. Revise over-broad or over-narrow rules when evidence supports doing so.
6. **Freeze and identify.** Validate the resolved JSON profile, copy it into the project and record its SHA-256.

This process reduces unexamined omissions by exposing vocabulary present in the supplied snapshot, but it cannot guarantee semantic completeness. Completeness remains conditional on the OSM snapshot, the reviewed profile and any external validation relevant to the research question.
