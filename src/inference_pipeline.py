import sys
import os
import time
import logging
import pandas as pd
import lightgbm as lgb
from pathlib import Path

# Add sentiment_analysis project to path to import its modules
SENTIMENT_DIR = Path("/home/shoki/workspace/sentiment_analysis/sentiment_analysis")
if str(SENTIMENT_DIR) not in sys.path:
    sys.path.insert(0, str(SENTIMENT_DIR))

from src.fetch_inference_features import fetch_inference_features
from src.fetch_tdnet_pdf import fetch_latest_kessan
from src.run_sentiment import extract_text_pipeline, analyze_sentiment_with_gemini, analyze_sentiment_with_gemini_fallback, load_industry_scenarios

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

MODEL_PATH = SENTIMENT_DIR / "models" / "lgbm_all.txt"
SAVE_DIR = SENTIMENT_DIR / "data" / "pdfs"

def run_inference_pipeline(candidate_df: pd.DataFrame, progress_callback=None, threshold: float=0.5) -> pd.DataFrame:
    """
    Run the end-to-end inference pipeline for a given DataFrame of candidate stocks.
    
    Flow:
    1. Extract features using yfinance.
    2. Predict win probability using LGBM.
    3. Filter out negative predictions (LGBM prob <= 0.5).
    4. Fetch earnings report PDFs for the remaining companies.
    5. Extract text and analyze sentiment using Gemini.
    6. Calculate combined scores.
    """
    if candidate_df.empty:
        return candidate_df

    # 1. Fetch features
    if progress_callback:
        progress_callback("LGBM推論用特徴量を取得中...", 0.1)
    
    # 5-digit format for fetching
    sec_codes_5 = [str(code) + "0" if len(str(code)) == 4 else str(code) for code in candidate_df['secCode']]
    
    def yf_progress_cb(current, total, code):
        if progress_callback:
            base_progress = 0.1
            # Allocate 0.2 (10% to 30%) for this yfinance feature extraction phase
            step_progress = 0.2 * (current / total)
            
            # Find the company name if available
            match = candidate_df[candidate_df['secCode'].astype(str) == str(code)[:4]]
            company_name = match.iloc[0]['name'] if not match.empty else ""
            
            msg = f"yfinanceから推論用特徴量を取得中... ({current}/{total}) {code[:4]} {company_name}"
            progress_callback(msg, base_progress + step_progress)

    features_df = fetch_inference_features(sec_codes_5, progress_callback=yf_progress_cb)
    
    if features_df.empty:
        logging.warning("No features retrieved.")
        return pd.DataFrame()
        
    # 2. LGBM Prediction
    if progress_callback:
        progress_callback("LGBMモデルで推論を実行中...", 0.3)
        
    if not MODEL_PATH.exists():
        logging.error(f"LGBM model not found at {MODEL_PATH}")
        return pd.DataFrame()
        
    model = lgb.Booster(model_file=str(MODEL_PATH))
    feature_names = model.feature_name()
    
    # Keep only the features that the model expects
    available_cols = set(features_df.columns)
    for col in feature_names:
        if col not in available_cols:
            features_df[col] = 0.0 # Fill missing expected features
            
    X = features_df[feature_names].astype(float)
    probs = model.predict(X)
    features_df['lgbm_prob'] = probs
    
    # Merge back to candidate_df
    # Note: candidate_df['secCode'] is usually 4 digits, features_df['sec_code'] is 5 digits
    features_df['secCode_4'] = features_df['sec_code'].astype(str).str[:4]
    
    merged_df = candidate_df.copy()
    merged_df['secCode_str'] = merged_df['secCode'].astype(str)
    merged_df = pd.merge(merged_df, features_df[['secCode_4', 'lgbm_prob']], 
                         left_on='secCode_str', right_on='secCode_4', how='left')
                         
    # 3. Filter out negative predictions
    if progress_callback:
        progress_callback("「負け」予測の銘柄を除外中...", 0.4)
        
    # Drop where prob is missing or prob <= threshold
    merged_df = merged_df.dropna(subset=['lgbm_prob'])
    filtered_df = merged_df[merged_df['lgbm_prob'] > threshold].copy()
    
    if filtered_df.empty:
        logging.warning("No stocks passed the LGBM filter.")
        return filtered_df
        
    # 4. Fetch PDFs
    if progress_callback:
        progress_callback(f"生き残った {len(filtered_df)} 銘柄の決算短信を取得中...", 0.5)
        
    surviving_codes = filtered_df['secCode_str'].tolist()
    pdf_results = fetch_latest_kessan(surviving_codes, save_dir=SAVE_DIR, search_days=30)
    
    # 5. Sentiment Analysis
    if progress_callback:
        progress_callback("Gemini API でテキスト感情分析を実行中...", 0.7)
        
    industry_scenarios = load_industry_scenarios()
    
    sentiment_scores = []
    llm_summaries = []
    
    for i, row in filtered_df.iterrows():
        code_str = row['secCode_str']
        company_name = row['name']
        industry = row.get('industry', 'Unknown')
        
        # Find pdf path
        pdf_path_str = ""
        if not pdf_results.empty:
            match = pdf_results[pdf_results['sec_code'].str.startswith(code_str)]
            if not match.empty:
                pdf_path_str = match.iloc[0]['pdf_path']
                
        sentiment_score = 0.0
        summary = "PDFが見つかりませんでした"
        
        if pdf_path_str and os.path.exists(pdf_path_str):
            try:
                important_text = extract_text_pipeline(Path(pdf_path_str), company_name=company_name)
                analysis_result = analyze_sentiment_with_gemini(company_name, industry, important_text, industry_scenarios)
                sentiment_score = analysis_result.get("sentiment_score", 0.0)
                summary = analysis_result.get("reasoning", "")
            except Exception as e:
                logging.error(f"Sentiment analysis failed for {company_name}: {e}")
                summary = f"感情分析エラー: {e}"
        else:
            # Fallback to WEB Search Grounding
            try:
                logging.info(f"PDF not found for {company_name}. Using fallback Web search.")
                analysis_result = analyze_sentiment_with_gemini_fallback(company_name, industry, code_str, industry_scenarios)
                sentiment_score = analysis_result.get("sentiment_score", 0.0)
                summary = "[WEB検索結果] " + analysis_result.get("reasoning", "")
            except Exception as e:
                logging.error(f"Fallback sentiment analysis failed for {company_name}: {e}")
                summary = f"WEB検索フォールバックエラー: {e}"
                
        sentiment_scores.append(sentiment_score)
        llm_summaries.append(summary)
        
    filtered_df['sentiment_score'] = sentiment_scores
    filtered_df['llm_summary'] = llm_summaries
    
    # 6. Calculate combined score
    if progress_callback:
        progress_callback("総合スコアを算出中...", 0.9)
        
    # Example combination: (lgbm_prob - 0.5)*2 gives range [0, 1] for positive probs
    # Then average with sentiment score (range [-1, 1]). 
    # Or just sum them. 
    filtered_df['combined_score'] = filtered_df['lgbm_prob'] + filtered_df['sentiment_score']
    
    if progress_callback:
        progress_callback("完了", 1.0)
        
    return filtered_df
