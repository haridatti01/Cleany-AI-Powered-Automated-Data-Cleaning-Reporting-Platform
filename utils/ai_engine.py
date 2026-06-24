"""
utils/ai_engine.py
AI-powered insight generation and natural-language dataset chat.
Supports OpenAI or Gemini via API keys in environment variables.
Falls back to a deterministic heuristic engine when no API key is set,
so the app remains fully functional without external AI access.
"""
import os
import json
import logging
import pandas as pd
import numpy as np

logger = logging.getLogger("cleany.ai_engine")

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")


def _llm_available() -> bool:
    return bool(OPENAI_API_KEY or GEMINI_API_KEY)


def _call_openai(prompt: str, system: str = "You are a senior data analyst.") -> str:
    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY)
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        temperature=0.3,
    )
    return resp.choices[0].message.content


def _call_gemini(prompt: str, system: str = "You are a senior data analyst.") -> str:
    import google.generativeai as genai
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-1.5-flash", system_instruction=system)
    resp = model.generate_content(prompt)
    return resp.text


def _call_llm(prompt: str, system: str = "You are a senior data analyst.") -> str:
    try:
        if OPENAI_API_KEY:
            return _call_openai(prompt, system)
        elif GEMINI_API_KEY:
            return _call_gemini(prompt, system)
    except Exception as e:
        logger.warning(f"LLM call failed, falling back to heuristic engine: {e}")
    return None


def generate_ai_insights(profile: dict, understanding: dict, quality: dict,
                          cleaning_report: dict, df: pd.DataFrame) -> dict:
    """
    Produce an executive summary, key findings, business insights,
    risks, recommendations, and data quality observations.
    Uses an LLM if configured, otherwise a rule-based generator.
    """
    context = {
        "profile": profile,
        "understanding": understanding,
        "quality": quality,
        "cleaning_report": {k: v for k, v in cleaning_report.items() if k != "missing_treatment_recommendations"},
    }

    if _llm_available():
        prompt = f"""
Analyze the following dataset metadata and produce a JSON object with keys:
executive_summary (string), key_findings (list of strings),
business_insights (list of strings), risks (list of strings),
recommendations (list of strings), data_quality_observations (list of strings).
Respond with ONLY valid JSON, no markdown.

Dataset metadata:
{json.dumps(context, default=str, indent=2)[:6000]}
"""
        raw = _call_llm(prompt)
        if raw:
            try:
                cleaned = raw.strip().strip("```json").strip("```").strip()
                return json.loads(cleaned)
            except Exception as e:
                logger.warning(f"Could not parse LLM JSON output: {e}")

    return _heuristic_insights(profile, understanding, quality, cleaning_report)


def _heuristic_insights(profile, understanding, quality, cleaning_report) -> dict:
    domain = understanding.get("domain", "General")
    rows, cols = profile["total_rows"], profile["total_columns"]

    executive_summary = (
        f"The dataset contains {rows:,} rows and {cols} columns and appears to belong to the "
        f"'{domain}' domain. Overall data quality score is {quality['score']}/100 "
        f"({quality['grade']}). "
        f"{cleaning_report.get('duplicates_removed', 0)} duplicate rows were removed and "
        f"{profile['missing_total']} missing values were detected prior to cleaning."
    )

    key_findings = [
        f"Dataset has {len(understanding['numerical_columns'])} numerical columns and "
        f"{len(understanding['categorical_columns'])} categorical columns.",
        f"Missing data accounted for {profile['missing_percent']}% of all cells before cleaning.",
        f"{cleaning_report.get('duplicates_removed', 0)} duplicate records were removed.",
    ]
    if understanding.get("date_columns"):
        key_findings.append(f"Detected {len(understanding['date_columns'])} date column(s): "
                             f"{', '.join(understanding['date_columns'])}.")
    if understanding.get("potential_targets"):
        key_findings.append(f"Likely target variable(s): {', '.join(understanding['potential_targets'])}.")

    business_insights = [
        f"This dataset is well-suited for analysis in the {domain} domain.",
        "Numerical columns can be used for trend, correlation, and predictive analysis.",
    ]
    if understanding.get("potential_targets"):
        business_insights.append(
            f"Consider building predictive models targeting: {', '.join(understanding['potential_targets'])}."
        )

    risks = []
    if quality["breakdown"]["missing_penalty"] > 10:
        risks.append("High proportion of missing data may bias downstream analysis.")
    if quality["breakdown"]["outlier_penalty"] > 10:
        risks.append("Significant outliers detected; they may distort averages and models.")
    if quality["breakdown"]["duplicate_penalty"] > 5:
        risks.append("Duplicate records were present and could have inflated counts/metrics.")
    if not risks:
        risks.append("No major data risks identified after cleaning.")

    recommendations = [
        "Review automatically imputed values for columns with high missingness.",
        "Validate outlier-flagged records with domain experts before exclusion.",
        "Establish data validation rules at the point of collection to reduce future errors.",
    ]

    data_quality_observations = [
        f"Quality score: {quality['score']}/100 ({quality['grade']}).",
        f"Missing value penalty: {quality['breakdown']['missing_penalty']}",
        f"Duplicate penalty: {quality['breakdown']['duplicate_penalty']}",
        f"Outlier penalty: {quality['breakdown']['outlier_penalty']}",
        f"Consistency penalty: {quality['breakdown']['consistency_penalty']}",
    ]

    return {
        "executive_summary": executive_summary,
        "key_findings": key_findings,
        "business_insights": business_insights,
        "risks": risks,
        "recommendations": recommendations,
        "data_quality_observations": data_quality_observations,
    }


def answer_dataset_question(df: pd.DataFrame, question: str) -> str:
    """
    Answer a natural-language question about the dataset.
    Uses an LLM with dataset context if configured; otherwise falls back
    to a pandas-based heuristic matcher for common question patterns.
    """
    if _llm_available():
        sample = df.head(20).to_csv(index=False)
        describe = df.describe(include="all").to_csv()
        prompt = f"""
You are a data analyst assistant. Given this dataset sample (first 20 rows) and summary
statistics, answer the user's question concisely and accurately. If a computation is
needed, reason through it using the sample/statistics provided. If you cannot determine
the answer from the given data, say so clearly.

Dataset sample (CSV):
{sample}

Summary statistics (CSV):
{describe}

Question: {question}
"""
        answer = _call_llm(prompt, system="You are a precise, concise data analyst assistant.")
        if answer:
            return answer.strip()

    return _heuristic_answer(df, question)


def _heuristic_answer(df: pd.DataFrame, question: str) -> str:
    q = question.lower()
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    categorical_cols = [c for c in df.columns if c not in numeric_cols]

    # Average / mean of a column
    for col in numeric_cols:
        if col.lower() in q and ("average" in q or "mean" in q):
            return f"The average {col} is {df[col].mean():.2f}."
        if col.lower() in q and ("max" in q or "highest" in q):
            return f"The maximum {col} is {df[col].max():.2f}."
        if col.lower() in q and ("min" in q or "lowest" in q):
            return f"The minimum {col} is {df[col].min():.2f}."
        if col.lower() in q and "sum" in q or ("total" in q and col.lower() in q):
            return f"The total {col} is {df[col].sum():.2f}."

    # "highest X by group" / "which Y has highest X"
    if "highest" in q or "top" in q:
        for cat in categorical_cols:
            if cat.lower() in q:
                for num in numeric_cols:
                    if num.lower() in q:
                        grouped = df.groupby(cat)[num].sum().sort_values(ascending=False)
                        top = grouped.head(10)
                        lines = [f"{idx}: {val:,.2f}" for idx, val in top.items()]
                        return f"Top {cat} by {num}:\n" + "\n".join(lines)
        for num in numeric_cols:
            if num.lower() in q:
                top_n = df.nlargest(10, num)
                return f"Top 10 rows by {num}:\n{top_n.to_string(index=False)}"

    # Row/column counts
    if "how many rows" in q or "number of rows" in q:
        return f"The dataset has {len(df):,} rows."
    if "how many columns" in q or "number of columns" in q:
        return f"The dataset has {df.shape[1]} columns."

    # Trends
    if "trend" in q:
        if numeric_cols:
            corr_text = ""
            if len(numeric_cols) >= 2:
                corr = df[numeric_cols].corr().abs()
                np.fill_diagonal(corr.values, 0)
                max_pair = corr.stack().idxmax()
                corr_text = (f" The strongest relationship found is between "
                             f"{max_pair[0]} and {max_pair[1]} "
                             f"(correlation = {corr.loc[max_pair]:.2f}).")
            return f"Numerical columns available for trend analysis: {', '.join(numeric_cols)}.{corr_text}"

    return ("I couldn't confidently match that question to the dataset using the built-in "
            "assistant. Try asking about a specific column, e.g. 'What is the average <column>?' "
            "or 'Show top 10 <category> by <numeric column>.' For more advanced natural-language "
            "answers, configure an OPENAI_API_KEY or GEMINI_API_KEY.")
