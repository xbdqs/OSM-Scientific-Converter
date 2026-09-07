# Scalability and limits

The v0.4.1 performance claims are empirical and bounded by the validated cases.

| Case | Input PBF | Reconstructed features | Unique key/value pairs | Complete-workflow peak RSS |
|---|---:|---:|---:|---:|
| Berlin power | 94.2 MiB | 2,525,682 | 445,244 | 481.1 MiB |
| South Korea aeroway | 271.3 MiB | 4,587,351 | 1,479,872 | 604.5 MiB |
| New York pipeline | 471.4 MiB | 11,434,477 | 6,576,398 | 633.1 MiB |
| Quebec power | 1.08 GiB | 12,382,811 | 595,209 | 616.4 MiB |

The disk-backed inventory removed the observed high-cardinality memory bottleneck of the obsolete New York in-memory prototype (approximately 13 GiB). It does **not** imply arbitrary scalability.

Runtime and storage remain dependent on GDAL reconstruction, storage throughput, feature count, tag cardinality, rule complexity, output size and temporary disk. The evidence supports regional workflows and the tested South Korea national extract on the documented workstation. Whole-planet imports are outside the validated scope; database-oriented software such as osm2pgsql is more appropriate for many such workflows.
