"""
src/common/spark_session.py
Centralised Spark session factory. Only place that creates SparkSession.
Reads config from settings.yaml; never hardcodes master/app_name.
"""
from __future__ import annotations

from src.common.config import get_settings, get_hdfs_uri


def get_spark(app_name: str | None = None, local_mode: bool = False):
    """
    Create or retrieve the active SparkSession.

    Parameters
    ----------
    app_name : str | None
        Override the app name from settings.yaml.
    local_mode : bool
        If True, configures filesystem as local file:/// instead of HDFS namenode.
    """
    import os
    import sys
    from pathlib import Path

    # Ensure JAVA_HOME is configured
    if "JAVA_HOME" not in os.environ:
        default_java = Path(r"C:\Program Files\Eclipse Adoptium\jdk-17.0.20.101-hotspot")
        if default_java.exists():
            os.environ["JAVA_HOME"] = str(default_java)
            os.environ["PATH"] = str(default_java / "bin") + os.pathsep + os.environ.get("PATH", "")

    # Ensure HADOOP_HOME is configured for Windows native operations
    if "HADOOP_HOME" not in os.environ:
        default_hadoop = Path(r"C:\hadoop")
        if default_hadoop.exists():
            os.environ["HADOOP_HOME"] = str(default_hadoop)
            os.environ["PATH"] = str(default_hadoop / "bin") + os.pathsep + os.environ.get("PATH", "")

    # Ensure worker python matches active driver interpreter
    if "PYSPARK_PYTHON" not in os.environ:
        os.environ["PYSPARK_PYTHON"] = sys.executable
    if "PYSPARK_DRIVER_PYTHON" not in os.environ:
        os.environ["PYSPARK_DRIVER_PYTHON"] = sys.executable

    try:
        from pyspark.sql import SparkSession  # noqa: PLC0415
    except ImportError:
        raise ImportError(
            "PySpark is not installed. Install it with: pip install pyspark==3.5.3"
        )

    cfg = get_settings()["spark"]
    hdfs_uri = "file:///" if (local_mode or os.environ.get("SPARK_LOCAL_MODE") == "1") else get_hdfs_uri()

    builder = (
        SparkSession.builder
        .master(cfg.get("master", "local[*]"))
        .appName(app_name or cfg.get("app_name", "yt-influencer-pipeline"))
        .config("spark.sql.shuffle.partitions", str(cfg.get("shuffle_partitions", 8)))
    )

    if hdfs_uri.startswith("hdfs://"):
        builder = (
            builder
            .config("spark.hadoop.fs.defaultFS", hdfs_uri)
            .config("dfs.client.use.datanode.hostname", "true")
        )

    spark = builder.getOrCreate()

    log_level = cfg.get("log_level", "WARN")
    spark.sparkContext.setLogLevel(log_level)
    return spark
