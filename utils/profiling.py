"""
utils/profiling.py
Data profiling, AI-style dataset understanding, and data quality scoring.
"""
import pandas as pd
import numpy as np


def profile_dataset(df: pd.DataFrame, duplicates_before: int = None) -> dict:
    total_cells = df.shape[0] * df.shape[1] if df.shape[1] else 1
    missing_total = int(df.isnull().sum().sum())
    dup_count = duplicates_before if duplicates_before is not None else int(df.duplicated().sum())

    return {
        "total_rows": int(df.shape[0]),
        "total_columns": int(df.shape[1]),
        "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
        "missing_total": missing_total,
        "missing_percent": round(missing_total / total_cells * 100, 2),
        "duplicate_count": dup_count,
        "memory_usage_kb": round(df.memory_usage(deep=True).sum() / 1024, 2),
    }


def understand_dataset(df: pd.DataFrame) -> dict:
    """Heuristically classify columns and guess dataset domain/targets."""
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    date_cols = df.select_dtypes(include=["datetime64[ns]"]).columns.tolist()
    categorical_cols = [c for c in df.columns if c not in numeric_cols and c not in date_cols]

    # Potential targets: numeric cols with common business keywords, or
    # low-cardinality categorical columns that look like labels/classes.
    target_keywords = ["target", "label", "price", "sales", "revenue", "salary",
                        "churn", "score", "amount", "profit", "outcome"]
    potential_targets = [c for c in numeric_cols if any(k in c.lower() for k in target_keywords)]
    if not potential_targets:
        low_card_cat = [c for c in categorical_cols if df[c].nunique() <= 10]
        potential_targets = low_card_cat[:3]

    domain_keywords = {
        "Sales / Retail": ["sales", "revenue", "product", "order", "customer", "price"],
        "Human Resources": ["salary", "employee", "department", "hire", "attrition"],
        "Finance": ["transaction", "amount", "balance", "loan", "credit", "account"],
        "Healthcare": ["patient", "diagnosis", "treatment", "hospital", "disease"],
        "Marketing": ["campaign", "click", "impression", "conversion", "lead"],
    }
    cols_lower = " ".join(df.columns).lower()
    domain_scores = {d: sum(k in cols_lower for k in kws) for d, kws in domain_keywords.items()}
    best_domain = max(domain_scores, key=domain_scores.get)
    domain = best_domain if domain_scores[best_domain] > 0 else "General / Unclassified"

    return {
        "domain": domain,
        "numerical_columns": numeric_cols,
        "categorical_columns": categorical_cols,
        "date_columns": date_cols,
        "potential_targets": potential_targets,
    }


def compute_quality_score(profile: dict, outliers_iqr: dict, total_rows: int) -> dict:
    """
    Compute a 0-100 data quality score based on missing values,
    duplicates, outliers, and consistency.
    """
    missing_penalty = min(profile["missing_percent"], 40)
    dup_pct = (profile["duplicate_count"] / total_rows * 100) if total_rows else 0
    dup_penalty = min(dup_pct, 25)

    outlier_total = sum(outliers_iqr.values())
    outlier_pct = (outlier_total / total_rows * 100) if total_rows else 0
    outlier_penalty = min(outlier_pct, 20)

    # Consistency penalty: proportion of columns that are still 'object' dtype
    # after type correction is treated as a mild consistency concern.
    n_cols = max(len(profile["dtypes"]), 1)
    object_cols = sum(1 for d in profile["dtypes"].values() if d == "object")
    consistency_penalty = min((object_cols / n_cols) * 15, 15)

    score = 100 - missing_penalty - dup_penalty - outlier_penalty - consistency_penalty
    score = max(0, round(score, 1))

    if score >= 85:
        grade = "Excellent"
    elif score >= 70:
        grade = "Good"
    elif score >= 50:
        grade = "Fair"
    else:
        grade = "Poor"

    return {
        "score": score,
        "grade": grade,
        "breakdown": {
            "missing_penalty": round(missing_penalty, 1),
            "duplicate_penalty": round(dup_penalty, 1),
            "outlier_penalty": round(outlier_penalty, 1),
            "consistency_penalty": round(consistency_penalty, 1),
        },
    }


def summary_statistics(df: pd.DataFrame) -> dict:
    numeric_df = df.select_dtypes(include=[np.number])
    if numeric_df.empty:
        return {}
    return numeric_df.describe().round(2).to_dict()


def correlation_matrix(df: pd.DataFrame) -> dict:
    numeric_df = df.select_dtypes(include=[np.number])
    if numeric_df.shape[1] < 2:
        return {}
    return numeric_df.corr().round(2).to_dict()
