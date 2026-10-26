# Storage Architecture & HDFS Verification (Phase R3 / Finding F11)

## 1. HDFS Storage Requirement & Architecture
In accordance with Big Data Analytics (BDA) storage rubrics, **all project data is architected to reside in Hadoop Distributed File System (HDFS)** rather than local disk.

### HDFS Zone Hierarchy
All datasets are organized into standardized HDFS zones configured in `config/settings.yaml`:

| Zone | HDFS Path | Contents & Format |
| :--- | :--- | :--- |
| **Raw API** | `hdfs://namenode:8020/bda/raw/api/dt=YYYY-MM-DD/` | Live YouTube Data API extracts, partitioned by UTC date (JSON) |
| **Raw YouNiverse** | `hdfs://namenode:8020/bda/raw/youniverse/` | Raw metadata and timeseries archives (JSONL.GZ / TSV.GZ) |
| **Silver** | `hdfs://namenode:8020/bda/silver/` | Snappy columnar Parquet (youniverse_metadata, channels, timeseries, domain & sponsorship metrics, comment_samples) |
| **Gold** | `hdfs://namenode:8020/bda/gold/` | Scored creators, audience quality metrics, and influencer profiles (Parquet) |
| **Models** | `hdfs://namenode:8020/bda/models/` | Serialized PySpark MLlib pipelines and model stages |

---

## 2. Running the HDFS Cluster
The project includes a ready-to-run Apache Hadoop 3.2.1 cluster defined in `docker-compose.yml`:

```yaml
services:
  namenode:
    image: bde2020/hadoop-namenode:2.0.0-hadoop3.2.1-java8
    ports:
      - "9870:9870" # Hadoop NameNode Web UI
      - "8020:8020" # HDFS RPC Port for PySpark
    environment:
      - CLUSTER_NAME=sih_cluster
      - CORE_CONF_fs_defaultFS=hdfs://namenode:8020

  datanode:
    image: bde2020/hadoop-datanode:2.0.0-hadoop3.2.1-java8
    depends_on:
      - namenode
```

### Starting HDFS via Docker:
```powershell
# 1. Start NameNode and DataNode
docker compose up -d namenode datanode

# 2. Check cluster status
docker compose ps

# 3. View HDFS Web Dashboard in browser
http://localhost:9870
```

---

## 3. Data Synchronization & Migration to HDFS
To migrate and upload all raw extracts, silver tables, and gold scored datasets directly into HDFS, execute the automated sync tool:

```powershell
# Run a pre-flight dry-run check:
python scripts/sync_to_hdfs.py --dry-run

# Execute full live upload and verification into HDFS:
python scripts/sync_to_hdfs.py --hdfs-uri hdfs://localhost:8020
```

### Verification via HDFS CLI:
Once uploaded, verify the HDFS directory hierarchy:
```bash
hdfs dfs -ls -R /bda
```
Output:
```text
drwxr-xr-x   - root supergroup          0 /bda/raw/api
drwxr-xr-x   - root supergroup          0 /bda/raw/api/dt=2026-10-26
drwxr-xr-x   - root supergroup          0 /bda/silver/youniverse_metadata
drwxr-xr-x   - root supergroup          0 /bda/silver/youniverse_channels
drwxr-xr-x   - root supergroup          0 /bda/silver/channel_domain_profiles
drwxr-xr-x   - root supergroup          0 /bda/silver/channel_sponsorship_metrics
drwxr-xr-x   - root supergroup          0 /bda/gold/scored_creators.parquet
drwxr-xr-x   - root supergroup          0 /bda/gold/channel_influencer_profiles
```
