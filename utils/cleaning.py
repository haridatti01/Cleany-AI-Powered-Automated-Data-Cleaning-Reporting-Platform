"""
utils/cleaning.py
Automated data cleaning: missing values, duplicates, outliers,
data type correction, standardization, and date parsing.
"""
import pandas as pd
import numpy as np
import logging

logger = logging.getLogger("cleany.cleaning")


def load_dataset(filepath: str) -> pd.DataFrame:
    """Load a CSV or Excel file into a DataFrame."""
    if filepath.lower().endswith(".csv"):
        df = pd.read_csv(filepath)
    elif filepath.lower().endswith((".xls", ".xlsx")):
        df = pd.read_excel(filepath)
    else:
        raise ValueError("Unsupported file format. Use CSV or Excel.")
    df.columns = [str(c).strip() for c in df.columns]
    return df


def detect_missing(df: pd.DataFrame) -> dict:
    total = len(df)
    missing = df.isnull().sum()
    pct = (missing / total * 100).round(2) if total else missing * 0
    return {
        col: {"count": int(missing[col]), "percent": float(pct[col])}
        for col in df.columns if missing[col] > 0
    }


def recommend_missing_treatment(df: pd.DataFrame) -> dict:
    """Suggest a treatment strategy for each column with missing data."""
    recs = {}
    for col in df.columns:
        n_missing = df[col].isnull().sum()
        if n_missing == 0:
            continue
        pct = n_missing / len(df) * 100
        if pct > 50:
            recs[col] = "drop_column (over 50% missing)"
        elif pd.api.types.is_numeric_dtype(df[col]):
            recs[col] = "impute_median"
        elif pd.api.types.is_datetime64_any_dtype(df[col]):
            recs[col] = "forward_fill"
        else:
            recs[col] = "impute_mode"
    return recs


def detect_duplicates(df: pd.DataFrame) -> int:
    return int(df.duplicated().sum())


def detect_outliers_iqr(df: pd.DataFrame) -> dict:
    outliers = {}
    for col in df.select_dtypes(include=[np.number]).columns:
        q1, q3 = df[col].quantile(0.25), df[col].quantile(0.75)
        iqr = q3 - q1
        lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        count = int(((df[col] < lower) | (df[col] > upper)).sum())
        if count > 0:
            outliers[col] = count
    return outliers


def detect_outliers_zscore(df: pd.DataFrame, threshold: float = 3.0) -> dict:
    outliers = {}
    for col in df.select_dtypes(include=[np.number]).columns:
        series = df[col].dropna()
        if series.std(ddof=0) == 0 or series.empty:
            continue
        z = (series - series.mean()) / series.std(ddof=0)
        count = int((z.abs() > threshold).sum())
        if count > 0:
            outliers[col] = count
    return outliers


def correct_data_types(df: pd.DataFrame) -> pd.DataFrame:
    """Attempt to infer and correct column dtypes (numeric, date, category)."""
    df = df.copy()
    for col in df.columns:
        if df[col].dtype == object:
            # Try numeric
            converted = pd.to_numeric(df[col], errors="coerce")
            if converted.notna().sum() / max(len(df), 1) > 0.9:
                df[col] = converted
                continue
            # Try datetime
            converted_dt = pd.to_datetime(df[col], errors="coerce", infer_datetime_format=True)
            if converted_dt.notna().sum() / max(len(df), 1) > 0.9:
                df[col] = converted_dt
    return df


def standardize_dates(df: pd.DataFrame, fmt: str = "%Y-%m-%d") -> pd.DataFrame:
    df = df.copy()
    for col in df.select_dtypes(include=["datetime64[ns]"]).columns:
        df[col] = df[col].dt.strftime(fmt)
    return df


def standardize_text(df: pd.DataFrame) -> pd.DataFrame:
    """Trim whitespace and normalize casing for text/categorical columns."""
    df = df.copy()
    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].astype(str).str.strip()
        df[col] = df[col].replace({"nan": np.nan, "None": np.nan, "": np.nan})
    return df


def clean_dataset(filepath: str, drop_duplicates=True, treat_missing=True,
                   handle_outliers=False) -> tuple[pd.DataFrame, dict]:
    """
    Full automated cleaning pipeline. Returns (cleaned_df, report_dict).
    """
    df = load_dataset(filepath)
    report = {
        "original_rows": len(df),
        "original_columns": len(df.columns),
        "missing_before": detect_missing(df),
        "duplicates_before": detect_duplicates(df),
    }

    df = standardize_text(df)
    df = correct_data_types(df)

    recs = recommend_missing_treatment(df)
    if treat_missing:
        for col, action in recs.items():
            if action.startswith("drop_column"):
                df.drop(columns=[col], inplace=True)
            elif action == "impute_median":
                df[col] = df[col].fillna(df[col].median())
            elif action == "impute_mode":
                mode = df[col].mode()
                df[col] = df[col].fillna(mode[0] if not mode.empty else "Unknown")
            elif action == "forward_fill":
                df[col] = df[col].ffill().bfill()

    if drop_duplicates:
        before = len(df)
        df = df.drop_duplicates()
        report["duplicates_removed"] = before - len(df)
    else:
        report["duplicates_removed"] = 0

    report["outliers_iqr"] = detect_outliers_iqr(df)
    report["outliers_zscore"] = detect_outliers_zscore(df)

    if handle_outliers:
        for col, _ in report["outliers_iqr"].items():
            q1, q3 = df[col].quantile(0.25), df[col].quantile(0.75)
            iqr = q3 - q1
            lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
            df[col] = df[col].clip(lower, upper)

    df = standardize_dates(df)

    report["missing_treatment_recommendations"] = recs
    report["final_rows"] = len(df)
    report["final_columns"] = len(df.columns)

    return df, report
