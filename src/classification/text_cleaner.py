"""
src/classification/text_cleaner.py
Clean and prepare video text (title + tags + truncated description)
using native PySpark SQL functions without python UDF overhead.
"""
from __future__ import annotations

from pyspark.sql import DataFrame
from pyspark.sql import functions as F


def clean_video_text(
    df: DataFrame,
    max_desc_chars: int = 500,
    output_col: str = "text",
) -> DataFrame:
    """
    Lowercase, strip URLs, emojis, punctuation, truncate description, and concatenate
    title, tags, and description into a single cleaned text column.

    Parameters
    ----------
    df : DataFrame
        Input DataFrame with columns `title`, `tags`, `description`.
    max_desc_chars : int
        Maximum characters from description to prevent boilerplate leakage/bloat.
    output_col : str
        Name of the cleaned text column.
    """
    # 1. Clean description: truncate then remove URLs
    clean_desc = F.regexp_replace(
        F.substring(F.coalesce(F.col("description"), F.lit("")), 1, max_desc_chars),
        r"https?://\S+|www\.\S+",
        " ",
    )
    clean_title = F.coalesce(F.col("title"), F.lit(""))
    clean_tags = F.coalesce(F.col("tags"), F.lit(""))

    # 2. Concatenate title, tags, description
    combined = F.concat_ws(" ", clean_title, clean_tags, clean_desc)

    # 3. Strip non-alphanumeric noise, lowercase, and collapse whitespace
    clean_text = F.lower(F.regexp_replace(combined, r"[^a-zA-Z0-9\s]", " "))
    clean_text = F.regexp_replace(clean_text, r"\s+", " ")
    clean_text = F.trim(clean_text)

    return df.withColumn(output_col, clean_text)
