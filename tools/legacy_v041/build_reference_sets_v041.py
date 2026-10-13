from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, Callable

from osm_scientific_converter.core.lifecycle import detect_lifecycle
from osm_scientific_converter.core.profiles import load_builtin_profile
from osm_scientific_converter.core.rules import evaluate_expression, rule_context_matches
from osm_scientific_converter.core.tag_scanner import parse_tags


LAYERS = {
    "points": "point",
    "lines": "line",
    "multilinestrings": "relation",
    "multipolygons": "polygon",
    "other_relations": "relation",
}
PROJECTS = {
    "Berlin": "berlin_power",
    "South Korea": "south_korea_aeroway",
    "New York": "new_york_pipeline",
    "Quebec": "quebec_power",
}
POWER_VALUES = {"line", "minor_line", "cable", "tower", "pole", "portal", "substation", "plant", "generator", "transformer", "converter", "switchgear"}
AEROWAY_VALUES = {"aerodrome", "airstrip", "runway", "taxiway", "taxilane", "apron", "terminal", "hangar", "helipad", "gate", "parking_position", "navigationaid"}
LIFECYCLE_PREFIXES = {"proposed", "planned", "construction", "disused", "abandoned", "demolished", "removed", "razed"}


def stable_key(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def identity(layer: str, fid: int, osm_id: Any, osm_way_id: Any) -> tuple[str, str]:
    if layer == "multipolygons":
        if osm_id not in (None, ""):
            return f"relation/{osm_id}", "relation"
        if osm_way_id not in (None, ""):
            return f"way/{osm_way_id}", "way"
        return f"unknown/{fid}", "unknown"
    if layer == "points":
        return (f"node/{osm_id}", "node") if osm_id not in (None, "") else (f"unknown/{fid}", "unknown")
    if layer == "lines":
        return (f"way/{osm_id}", "way") if osm_id not in (None, "") else (f"unknown/{fid}", "unknown")
    return (f"relation/{osm_id}", "relation") if osm_id not in (None, "") else (f"unknown/{fid}", "unknown")


def lifecycle_topic(tags: dict[str, str], key: str, accepted: set[str]) -> bool:
    for raw_key, value in tags.items():
        parts = raw_key.split(":", 1)
        if len(parts) == 2 and parts[0] in LIFECYCLE_PREFIXES and parts[1] == key and value in accepted:
            return True
    return False


def label_power(tags: dict[str, str]) -> tuple[bool, str]:
    active = tags.get("power") in POWER_VALUES
    lifecycle = lifecycle_topic(tags, "power", POWER_VALUES) or (tags.get("power") in LIFECYCLE_PREFIXES and tags.get("construction") in POWER_VALUES)
    return active or lifecycle, "explicit active/lifecycle power tag semantics" if active or lifecycle else "related tags without an explicit supported power object"


def label_aeroway(tags: dict[str, str]) -> tuple[bool, str]:
    active = tags.get("aeroway") in AEROWAY_VALUES or "navigationaid" in tags
    lifecycle = lifecycle_topic(tags, "aeroway", AEROWAY_VALUES)
    return active or lifecycle, "explicit active/lifecycle aeroway or navigation-aid tag semantics" if active or lifecycle else "aviation-related tags without an explicit supported aeroway object"


def pipeline_context(tags: dict[str, str]) -> bool:
    return tags.get("man_made") == "pipeline" or "pipeline" in tags or tags.get("route") == "pipeline"


def label_pipeline(tags: dict[str, str]) -> tuple[bool, str]:
    context = pipeline_context(tags)
    facility = tags.get("pipeline") in {"valve", "pumping_station", "pump", "compressor", "compressor_station", "storage"}
    contextual_facility = tags.get("man_made") in {"pumping_station", "compressor_station", "storage_tank", "gasometer"} and any(
        key in tags for key in ("substance", "product", "utility", "pipeline")
    )
    lifecycle = lifecycle_topic(tags, "man_made", {"pipeline"})
    positive = context or facility or contextual_facility or lifecycle
    return positive, "explicit pipeline context/facility/lifecycle tag semantics" if positive else "pipeline-adjacent facility or substance without explicit pipeline context"


LABELERS: dict[str, Callable[[dict[str, str]], tuple[bool, str]]] = {
    "power": label_power,
    "aeroway": label_aeroway,
    "pipeline": label_pipeline,
}
PATTERNS = {
    "power": ["%power%", "%generator:source%", "%voltage%"],
    "aeroway": ["%aeroway%", "%navigationaid%", "%icao%", "%iata%"],
    "pipeline": ["%pipeline%", "%pumping_station%", "%compressor_station%", "%storage_tank%", "%substance%"],
}


def predicted(topic: str, tags: dict[str, str], context: dict[str, Any]) -> tuple[bool, list[str]]:
    profile = load_builtin_profile(topic)
    categories = []
    for rule in profile.data["rules"]:
        if rule_context_matches(rule, context) and evaluate_expression(rule["expression"], tags, context).matched:
            categories.append(str(rule["category"]))
    return bool(categories), sorted(set(categories))


def candidates(project_root: Path, topic: str) -> list[dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for region, project_name in PROJECTS.items():
        database = project_root / project_name / "data" / "raw_master.gpkg"
        with sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True) as connection:
            for layer, geometry in LAYERS.items():
                columns = {row[1] for row in connection.execute(f'PRAGMA table_info("{layer}")')}
                if not {"fid", "osm_id", "all_tags"}.issubset(columns):
                    continue
                osm_way = '"osm_way_id"' if "osm_way_id" in columns else "NULL"
                clauses = " OR ".join('"all_tags" LIKE ?' for _ in PATTERNS[topic])
                query = f'SELECT "fid","osm_id",{osm_way},"all_tags" FROM "{layer}" WHERE {clauses} ORDER BY "fid" LIMIT 5000'
                for fid, osm_id, osm_way_id, raw_tags in connection.execute(query, PATTERNS[topic]):
                    tags, anomaly = parse_tags(raw_tags)
                    if anomaly or not tags:
                        continue
                    sid, osm_type = identity(layer, int(fid), osm_id, osm_way_id)
                    states = sorted({state for state, _ in detect_lifecycle(tags)})
                    context = {"source_layer": layer, "geometry_group": geometry, "osm_type": osm_type, "lifecycle": states}
                    truth, rationale = LABELERS[topic](tags)
                    prediction, categories = predicted(topic, tags, context)
                    result[f"{region}:{sid}"] = {
                        "region": region,
                        "osm_id": sid,
                        "osm_type": osm_type,
                        "source_layer": layer,
                        "geometry_group": geometry,
                        "lifecycle": states,
                        "tags": tags,
                        "reference_positive": truth,
                        "label_rationale": rationale,
                        "predicted_positive": prediction,
                        "predicted_categories": categories,
                    }
    return list(result.values())


def select_balanced(items: list[dict[str, Any]], positive: bool, count: int, topic: str) -> list[dict[str, Any]]:
    pool = [item for item in items if item["reference_positive"] is positive]
    pool.sort(key=lambda item: stable_key(f"{topic}|{positive}|{item['region']}|{item['osm_id']}"))
    selected: list[dict[str, Any]] = []
    seen: set[tuple[str, str, bool]] = set()
    for item in pool:
        stratum = (item["region"], item["geometry_group"], bool(item["lifecycle"]))
        if stratum not in seen:
            selected.append(item)
            seen.add(stratum)
            if len(selected) == count:
                return selected
    for item in pool:
        if item not in selected:
            selected.append(item)
            if len(selected) == count:
                return selected
    raise ValueError(f"Insufficient {topic} {'positive' if positive else 'negative'} cases: {len(selected)} < {count}")


def metrics(cases: list[dict[str, Any]]) -> dict[str, Any]:
    tp = sum(item["reference_positive"] and item["predicted_positive"] for item in cases)
    fp = sum(not item["reference_positive"] and item["predicted_positive"] for item in cases)
    fn = sum(item["reference_positive"] and not item["predicted_positive"] for item in cases)
    tn = sum(not item["reference_positive"] and not item["predicted_positive"] for item in cases)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return {
        "confusion": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "f1": round(2 * precision * recall / (precision + recall), 6) if precision + recall else 0.0,
        "false_positive_types": sorted({item["label_rationale"] for item in cases if not item["reference_positive"] and item["predicted_positive"]}),
        "false_negative_types": sorted({item["label_rationale"] for item in cases if item["reference_positive"] and not item["predicted_positive"]}),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--projects", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    summary: dict[str, Any] = {
        "schema_version": "1.0",
        "status": "provisional_agent_adjudication_complete_independent_human_review_pending",
        "label_scope": "OSM tag-semantic classification, not physical real-world asset truth",
        "review_provenance": {
            "agent_tag_semantic_adjudication": True,
            "independent_author_domain_review": False,
            "publication_use_permitted_before_independent_review": False,
        },
        "selection_method": {
            "candidate_source": "read-only raw_master.gpkg files created from the dated local PBF snapshots",
            "candidate_query_limit_per_layer_per_region": 5000,
            "selection_order": "SHA-256 of topic, reference label, region, and OSM identity",
            "balancing": "first include each available region × geometry_group × lifecycle-presence stratum, then fill deterministically",
        },
        "inputs": {},
        "topics": {},
    }
    for region, project_name in PROJECTS.items():
        metadata_path = args.projects / project_name / "input_metadata.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8-sig"))
        summary["inputs"][region] = {
            "file": Path(metadata["path"]).name,
            "bytes": metadata["size_bytes"],
            "sha256": metadata["sha256"],
        }
    all_coverage_passed = True
    for topic in ("power", "aeroway", "pipeline"):
        pool = candidates(args.projects, topic)
        cases = select_balanced(pool, True, 50, topic) + select_balanced(pool, False, 30, topic)
        cases.sort(key=lambda item: (not item["reference_positive"], stable_key(f"{topic}|{item['region']}|{item['osm_id']}")))
        profile = load_builtin_profile(topic)
        document = {
            "schema_version": "1.0",
            "topic": topic,
            "profile": {"id": profile.id, "sha256": profile.sha256},
            "counts": {"positive": 50, "negative": 30, "total": 80},
            "coverage": {
                "regions": sorted({item["region"] for item in cases}),
                "geometry_groups": sorted({item["geometry_group"] for item in cases}),
                "osm_types": sorted({item["osm_type"] for item in cases}),
                "lifecycle_cases": sum(bool(item["lifecycle"]) for item in cases),
            },
            "metrics": metrics(cases),
            "review_provenance": summary["review_provenance"],
            "cases": cases,
        }
        document["coverage"]["active_cases"] = sum(not bool(item["lifecycle"]) for item in cases)
        document["coverage_checks"] = {
            "positive_at_least_50": sum(item["reference_positive"] for item in cases) >= 50,
            "negative_at_least_30": sum(not item["reference_positive"] for item in cases) >= 30,
            "point_line_polygon_relation": set(document["coverage"]["geometry_groups"]) == {"point", "line", "polygon", "relation"},
            "active_and_lifecycle": document["coverage"]["active_cases"] > 0 and document["coverage"]["lifecycle_cases"] > 0,
            "multiple_regions": len(document["coverage"]["regions"]) >= 2,
        }
        document["coverage_status"] = "success" if all(document["coverage_checks"].values()) else "failed"
        all_coverage_passed = all_coverage_passed and document["coverage_status"] == "success"
        path = args.output / f"{topic}_reference_set_v041.json"
        path.write_text(json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        summary["topics"][topic] = {"file": path.name, "profile": document["profile"], "counts": document["counts"], "coverage": document["coverage"], "coverage_checks": document["coverage_checks"], "coverage_status": document["coverage_status"], "metrics": document["metrics"]}
    if not all_coverage_passed:
        summary["status"] = "failed_required_coverage"
    (args.output / "REFERENCE_SET_SUMMARY_V041.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": summary["status"], "topics": list(summary["topics"])}, ensure_ascii=False))
    return 0 if all_coverage_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
