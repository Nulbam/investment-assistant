import logging
from datetime import datetime, timedelta
import requests
import numpy as np
import pandas as pd
import FinanceDataReader as fdr

logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def _safe_num(val, digits=2):
    """NaN / Inf 값을 JSON 안전한 None(null)으로 변환하고 반올림합니다."""
    if val is None or pd.isna(val):
        return None
    try:
        f = float(val)
        if not np.isfinite(f):
            return None
        return round(f, digits)
    except (ValueError, TypeError):
        return None


def _series_to_list(series: pd.Series, digits=2) -> list:
    """Pandas Series를 JSON 직렬화 가능한 리스트(NaN -> None)로 변환합니다."""
    return [_safe_num(v, digits) for v in series]


def _get_stock_name(code: str) -> str:
    """네이버 모바일 API에서 정식 종목명을 조회하고, 실패 시 종목코드를 반환합니다."""
    try:
        resp = requests.get(
            f"https://m.stock.naver.com/api/stock/{code}/basic",
            headers=DEFAULT_HEADERS,
            timeout=3
        )
        if resp.status_code == 200:
            name = resp.json().get("stockName")
            if name:
                return name
    except Exception:
        pass
    return code


def calculate_indicators(code: str, chart_days: int = 120) -> dict:
    """
    Step 8: FinanceDataReader로 최근 1년 주가를 수집한 뒤
    MA(5, 20, 60), RSI(14), MACD(12, 26, 9), 볼린저밴드(20, 2)를 계산하고
    차트용 시계열(최근 chart_days 거래일)과 Dify 주입용 최신 수치 요약을 반환합니다.
    """
    clean_code = str(code or "").strip()
    if not clean_code or len(clean_code) != 6 or not clean_code.isdigit():
        return {
            "ok": False,
            "error": "종목코드는 6자리 숫자여야 합니다. (예: 000660)"
        }

    end_dt = datetime.now()
    start_dt = end_dt - timedelta(days=365)
    start_str = start_dt.strftime("%Y-%m-%d")
    end_str = end_dt.strftime("%Y-%m-%d")

    logger.info(f"[FDR] 기술지표용 주가 수집 시작 (code={clean_code}, period={start_str}~{end_str})")

    try:
        df = fdr.DataReader(clean_code, start_str, end_str)
        if df is None or df.empty or "Close" not in df.columns:
            err_msg = f"종목코드 {clean_code}의 주가 데이터를 찾을 수 없습니다."
            logger.warning(f"[ERROR] {err_msg}")
            return {"ok": False, "error": err_msg}

        close = pd.to_numeric(df["Close"], errors="coerce").dropna()
        if len(close) < 30:
            err_msg = f"종목코드 {clean_code}의 거래일 데이터가 부족하여 기술지표를 계산할 수 없습니다. (수집={len(close)}일)"
            logger.warning(f"[ERROR] {err_msg}")
            return {"ok": False, "error": err_msg}
    except Exception as e:
        err_msg = f"주가 데이터 수집 실패: {str(e)}"
        logger.error(f"[ERROR] {err_msg}", exc_info=True)
        return {"ok": False, "error": err_msg}

    stock_name = _get_stock_name(clean_code)

    # 1. 이동평균선 (MA 5, 20, 60)
    ma5 = close.rolling(window=5).mean()
    ma20 = close.rolling(window=20).mean()
    ma60 = close.rolling(window=60).mean()

    # 2. 볼린저밴드 (20일, 2표준편차)
    std20 = close.rolling(window=20).std()
    bb_upper = ma20 + (2 * std20)
    bb_lower = ma20 - (2 * std20)

    # 3. RSI (14일, Wilder 지수이동평균 방식)
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi14 = 100 - (100 / (1 + rs))
    # 하락이 전혀 없는 구간(avg_loss == 0 and avg_gain > 0)은 RSI 100 처리
    rsi14 = rsi14.where(~((avg_loss == 0) & (avg_gain > 0)), 100.0)

    # 4. MACD (12, 26, 9)
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    macd_signal = macd.ewm(span=9, adjust=False).mean()
    macd_hist = macd - macd_signal

    # 최근 chart_days 거래일만 차트용 시계열로 슬라이싱
    tail_idx = close.index[-chart_days:]
    dates = [dt.strftime("%Y-%m-%d") for dt in tail_idx]

    series = {
        "dates": dates,
        "close": _series_to_list(close.loc[tail_idx], 0),
        "ma5": _series_to_list(ma5.loc[tail_idx], 0),
        "ma20": _series_to_list(ma20.loc[tail_idx], 0),
        "ma60": _series_to_list(ma60.loc[tail_idx], 0),
        "bb_upper": _series_to_list(bb_upper.loc[tail_idx], 0),
        "bb_lower": _series_to_list(bb_lower.loc[tail_idx], 0),
        "rsi14": _series_to_list(rsi14.loc[tail_idx], 2),
        "macd": _series_to_list(macd.loc[tail_idx], 2),
        "macd_signal": _series_to_list(macd_signal.loc[tail_idx], 2),
        "macd_hist": _series_to_list(macd_hist.loc[tail_idx], 2),
    }

    latest_summary = {
        "code": clean_code,
        "name": stock_name,
        "date": dates[-1],
        "close": _safe_num(close.iloc[-1], 0),
        "ma5": _safe_num(ma5.iloc[-1], 0),
        "ma20": _safe_num(ma20.iloc[-1], 0),
        "ma60": _safe_num(ma60.iloc[-1], 0),
        "bb_upper": _safe_num(bb_upper.iloc[-1], 0),
        "bb_mid": _safe_num(ma20.iloc[-1], 0),
        "bb_lower": _safe_num(bb_lower.iloc[-1], 0),
        "rsi14": _safe_num(rsi14.iloc[-1], 2),
        "macd": _safe_num(macd.iloc[-1], 2),
        "macd_signal": _safe_num(macd_signal.iloc[-1], 2),
        "macd_hist": _safe_num(macd_hist.iloc[-1], 2),
    }

    logger.info(
        f"[CALC] 기술지표 계산 완료 (code={clean_code}, name={stock_name}, "
        f"date={latest_summary['date']}, close={latest_summary['close']}, rsi14={latest_summary['rsi14']})"
    )

    return {
        "ok": True,
        "code": clean_code,
        "name": stock_name,
        "latest_summary": latest_summary,
        "series": series,
        "error": None
    }


if __name__ == "__main__":
    import json
    print("=" * 60)
    print("Step 8 단독 테스트: indicators.py (SK하이닉스 000660)")
    print("=" * 60)

    res = calculate_indicators("000660")
    if not res["ok"]:
        print("오류:", res["error"])
    else:
        preview = {
            "code": res["code"],
            "name": res["name"],
            "latest_summary": res["latest_summary"],
            "series_points": len(res["series"]["dates"]),
        }
        print(json.dumps(preview, ensure_ascii=False, indent=2))
