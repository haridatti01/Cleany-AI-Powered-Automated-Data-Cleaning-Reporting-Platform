"""
utils/charts.py
Generates Plotly chart JSON for the dashboard and Matplotlib/Seaborn
images for embedding in PDF reports.
"""
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.utils
import json
import io
import base64
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns


def _fig_to_json(fig):
    return json.loads(json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder))


def generate_histograms(df: pd.DataFrame, max_cols: int = 6) -> dict:
    charts = {}
    numeric_cols = df.select_dtypes(include=[np.number]).columns[:max_cols]
    for col in numeric_cols:
        fig = px.histogram(df, x=col, nbins=30, title=f"Distribution of {col}")
        charts[col] = _fig_to_json(fig)
    return charts


def generate_boxplots(df: pd.DataFrame, max_cols: int = 6) -> dict:
    charts = {}
    numeric_cols = df.select_dtypes(include=[np.number]).columns[:max_cols]
    for col in numeric_cols:
        fig = px.box(df, y=col, title=f"Box Plot: {col}")
        charts[col] = _fig_to_json(fig)
    return charts


def generate_correlation_heatmap(df: pd.DataFrame):
    numeric_df = df.select_dtypes(include=[np.number])
    if numeric_df.shape[1] < 2:
        return None
    corr = numeric_df.corr().round(2)
    fig = px.imshow(corr, text_auto=True, title="Correlation Heatmap", color_continuous_scale="RdBu_r")
    return _fig_to_json(fig)


def generate_bar_chart(df: pd.DataFrame, categorical_col: str, numeric_col: str = None, top_n: int = 10):
    if categorical_col not in df.columns:
        return None
    if numeric_col and numeric_col in df.columns:
        data = df.groupby(categorical_col)[numeric_col].sum().sort_values(ascending=False).head(top_n)
        fig = px.bar(x=data.index, y=data.values, title=f"Top {top_n} {categorical_col} by {numeric_col}",
                     labels={"x": categorical_col, "y": numeric_col})
    else:
        data = df[categorical_col].value_counts().head(top_n)
        fig = px.bar(x=data.index, y=data.values, title=f"Top {top_n} {categorical_col}",
                     labels={"x": categorical_col, "y": "Count"})
    return _fig_to_json(fig)


def generate_static_heatmap_image(df: pd.DataFrame) -> bytes:
    """Generate a PNG image (bytes) of the correlation heatmap using Seaborn, for PDF embedding."""
    numeric_df = df.select_dtypes(include=[np.number])
    if numeric_df.shape[1] < 2:
        return None
    plt.figure(figsize=(6, 5))
    sns.heatmap(numeric_df.corr(), annot=True, cmap="coolwarm", fmt=".2f")
    plt.title("Correlation Heatmap")
    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=120)
    plt.close()
    buf.seek(0)
    return buf.read()


def generate_static_missing_chart(df: pd.DataFrame) -> bytes:
    """Bar chart image of missing values per column for PDF embedding."""
    missing = df.isnull().sum()
    missing = missing[missing > 0].sort_values(ascending=False)
    if missing.empty:
        return None
    plt.figure(figsize=(6, 4))
    sns.barplot(x=missing.values, y=missing.index, color="#4C72B0")
    plt.title("Missing Values by Column")
    plt.xlabel("Missing Count")
    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=120)
    plt.close()
    buf.seek(0)
    return buf.read()
