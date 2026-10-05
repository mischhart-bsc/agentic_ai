"""Neutral data schema for the prompt: column names, dtypes, example values. No descriptions, no traps."""
import pandas as pd

import config


def _fmt(v, max_len):
    """Floats with 4 significant digits (saves tokens), everything else cut to max_len."""
    return f"{v:.4g}" if isinstance(v, float) else str(v)[:max_len]


def data_schema(n_examples=2, max_len=30):
    df = pd.read_csv(config.DATA_DIR / config.DATA_FILE, low_memory=False)
    lines = [f"File: /data/{config.DATA_FILE}  ({len(df)} rows, {df.shape[1]} columns)",
             "column | dtype | example values"]
    for col in df.columns:
        ex = [_fmt(v, max_len) for v in df[col].dropna().head(n_examples)]
        lines.append(f"{col} | {df[col].dtype} | {', '.join(ex)}")
    return "\n".join(lines)