# Typical user value chains

These examples mirror Table 4 of the revised SoftwareX manuscript. OSM Scientific Converter ends at auditable thematic data preparation; substantive modelling remains downstream.

## 1. Infrastructure/environmental study

**Workflow:** dated regional PBF → input-specific inventory → reviewed power/pipeline profile → deterministic process audit → GeoPackage.

**Output value:** a thematic layer tied to input/profile hashes, explicit rules, OSM representation, and export provenance.

**Downstream task (outside converter):** exposure, proximity, hazard, or environmental modelling in GIS/Python/R.

## 2. Aeroway/transport study

**Workflow:** national PBF → aeroway profile → category selection → preview/audit → GeoJSON or GeoPackage.

**Output value:** consistent extraction across OSM representations with lifecycle provenance.

**Downstream task (outside converter):** network, accessibility, airport, or transport analysis.

## 3. Custom niche theme

**Workflow:** snapshot → inspect observed keys/values → domain/OSM review → custom JSON profile → audit/export.

**Output value:** an archived semantic definition tied to the vocabulary actually present in the snapshot.

**Downstream task (outside converter):** domain-specific analysis designed by the research team.
