from osm_scientific_converter.core.scanner import _merge_performance_metrics


def test_overall_peak_includes_import_peak() -> None:
    metrics = _merge_performance_metrics(
        {"import_peak_rss_bytes": 542_789_632, "import_wall_time_seconds": 86.6},
        {"overall_peak_rss_bytes": 465_137_664, "working_disk_peak_bytes": 3_002_737_412},
    )

    assert metrics["overall_peak_rss_bytes"] == 542_789_632
    assert metrics["working_disk_peak_bytes"] == 3_002_737_412


def test_missing_import_peak_preserves_monitor_peak() -> None:
    metrics = _merge_performance_metrics(
        {"import_peak_rss_bytes": None},
        {"overall_peak_rss_bytes": 123},
    )

    assert metrics["overall_peak_rss_bytes"] == 123
