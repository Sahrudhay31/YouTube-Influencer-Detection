# Storage Architecture & HDFS Verification (Phase R3 / Finding F11)

## 1. Context & Verification
During Phase R0 baseline verification, Finding **F11** observed:
> *"HDFS appears unused: `spark_session.py` falls back to `file:///`; classifier reads `local("silver", ...)`; Docker was not installed at Phase 0. README still says 'Hadoop HDFS'."*

Environment inspection on the development host confirmed:
```powershell
docker --version
# Output: docker : The term 'docker' is not recognized as the name of a cmdlet...
```
Docker Desktop / WSL2 is not installed on this local workstation.

## 2. Decision (Phase R3 Option B)
Per Section 6 (Phase R3) of `antigravity_remediation_prompt_beauty.md`, Option B was enacted:
- **Local Filesystem Mode Default**: All Spark and pandas pipelines read and write to local NTFS paths (`file:///`) under `data/silver/` and `data/gold/` using snappy-compressed columnar Parquet.
- **Transparent Documentation**: `README.md` and `docs/DECISIONS.md` (ADR-013) have been updated to explicitly state that the system operates in local filesystem mode, with no artificial claims of active distributed HDFS operation on this workstation.
- **Preserved Cluster Configuration**: `docker-compose.yml` (`bde2020/hadoop-namenode:2.0.0-hadoop3.2.1-java8` and `bde2020/hadoop-datanode:2.0.0-hadoop3.2.1-java8`) remains preserved and ready for cluster deployment whenever Docker is provisioned.
- **Fail-Loud Architecture**: When HDFS paths are requested in production configurations, `src/common/paths.py` and `spark_session.py` enforce explicit connection checks, preventing silent fallback to local storage when HDFS is expected.
