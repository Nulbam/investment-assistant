import os
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


def _safe_round(val, digits=2):
    """NaN / Inf 값을 안전하게 None으로 변환하고 반올림합니다."""
    if val is None:
        return None
    try:
        f = float(val)
        if not np.isfinite(f):
            return None
        return round(f, digits)
    except (ValueError, TypeError):
        return None


def _get_stock_name(code: str) -> str:
    """네이버 모바일 API에서 종목명을 간단히 조회하고, 실패 시 종목코드를 그대로 반환합니다."""
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


def calculate_mdd(price_series: pd.Series) -> float:
    """단일 종목 또는 포트폴리오 가치 시계열의 최대낙폭(MDD, %)을 계산합니다."""
    if price_series is None or len(price_series) < 2:
        return None
    cum_max = price_series.cummax()
    drawdown = (price_series - cum_max) / cum_max
    return _safe_round(drawdown.min() * 100, 2)


def fetch_portfolio_history(codes: list, lookback_days: int = 365) -> dict:
    """
    Step 6: FinanceDataReader로 다중 종목의 최근 1년 종가를 수집하고
    수익률, 연율화 변동성, 공분산 행렬, 종목별 MDD를 계산합니다.
    """
    # 1. 종목코드 정제 및 중복 제거 (순서 유지)
    clean_codes = []
    seen = set()
    for raw in codes or []:
        c = str(raw).strip()
        if c and c not in seen:
            seen.add(c)
            clean_codes.append(c)

    if len(clean_codes) < 2:
        return {
            "ok": False,
            "error": "리밸런싱 계산을 위해 최소 2개 이상의 서로 다른 종목코드를 입력해 주세요."
        }

    invalid = [c for c in clean_codes if len(c) != 6 or not c.isdigit()]
    if invalid:
        return {
            "ok": False,
            "error": f"올바르지 않은 6자리 종목코드가 포함되어 있습니다: {', '.join(invalid)}"
        }

    end_dt = datetime.now()
    start_dt = end_dt - timedelta(days=lookback_days)
    start_str = start_dt.strftime("%Y-%m-%d")
    end_str = end_dt.strftime("%Y-%m-%d")

    logger.info(f"[FDR] FinanceDataReader 주가 수집 시작 (codes={clean_codes}, period={start_str}~{end_str})")

    series_map = {}
    names_map = {}

    for code in clean_codes:
        try:
            df = fdr.DataReader(code, start_str, end_str)
            if df is None or df.empty or "Close" not in df.columns:
                err_msg = f"종목코드 {code}의 최근 1년 주가 데이터를 찾을 수 없습니다."
                logger.warning(f"[ERROR] {err_msg}")
                return {"ok": False, "error": err_msg}

            close_s = pd.to_numeric(df["Close"], errors="coerce").dropna()
            if len(close_s) < 20:
                err_msg = f"종목코드 {code}의 거래일 데이터가 부족합니다. (수집={len(close_s)}일)"
                logger.warning(f"[ERROR] {err_msg}")
                return {"ok": False, "error": err_msg}

            series_map[code] = close_s
            names_map[code] = _get_stock_name(code)
        except Exception as e:
            err_msg = f"종목코드 {code} 주가 수집 실패: {str(e)}"
            logger.error(f"[ERROR] {err_msg}", exc_info=True)
            return {"ok": False, "error": err_msg}

    # 2. 공통 거래일 기준으로 종가 정렬 및 결측치 제거
    prices_df = pd.DataFrame(series_map).dropna()
    if len(prices_df) < 20:
        return {
            "ok": False,
            "error": "입력한 종목들의 공통 거래일 데이터가 20일 미만이라 계산할 수 없습니다."
        }

    # 3. 일간 수익률, 연율화 기대수익률/변동성, 공분산 행렬, MDD 계산
    returns_df = prices_df.pct_change().dropna()
    trading_days = 252

    mean_returns = returns_df.mean() * trading_days
    cov_matrix = returns_df.cov() * trading_days

    asset_stats = []
    for code in clean_codes:
        ann_ret = _safe_round(mean_returns[code] * 100, 2)
        ann_vol = _safe_round(returns_df[code].std() * np.sqrt(trading_days) * 100, 2)
        mdd = calculate_mdd(prices_df[code])
        asset_stats.append({
            "code": code,
            "name": names_map[code],
            "annual_return_pct": ann_ret,
            "annual_volatility_pct": ann_vol,
            "mdd_pct": mdd,
            "latest_price": _safe_round(prices_df[code].iloc[-1], 0),
        })

    logger.info(f"[CALC] 종목별 1년 수익률·공분산·MDD 계산 완료 (공통 거래일={len(prices_df)}일)")

    return {
        "ok": True,
        "codes": clean_codes,
        "names": names_map,
        "period": f"{prices_df.index[0].strftime('%Y-%m-%d')} ~ {prices_df.index[-1].strftime('%Y-%m-%d')}",
        "trading_days": int(len(prices_df)),
        "prices_df": prices_df,
        "returns_df": returns_df,
        "mean_returns": mean_returns,
        "cov_matrix": cov_matrix,
        "asset_stats": asset_stats,
        "error": None
    }


def _evaluate_portfolio(weights: np.ndarray, returns_df: pd.DataFrame, mean_returns: pd.Series, cov_matrix: pd.DataFrame, codes: list, names: dict, risk_free_rate: float) -> dict:
    """주어진 비중 벡터에 대한 포트폴리오 기대수익률, 변동성, 샤프지수, MDD를 계산합니다."""
    port_ret = float(np.dot(weights, mean_returns.values))
    port_var = float(np.dot(weights.T, np.dot(cov_matrix.values, weights)))
    port_vol = float(np.sqrt(max(port_var, 0.0)))
    sharpe = (port_ret - risk_free_rate) / port_vol if port_vol > 0 else 0.0

    # 포트폴리오 1년 누적 가치 곡선으로 MDD 계산
    port_daily_ret = returns_df.values @ weights
    port_curve = pd.Series((1.0 + port_daily_ret).cumprod())
    mdd = calculate_mdd(port_curve)

    weight_items = [
        {
            "code": code,
            "name": names[code],
            "weight_pct": _safe_round(w * 100, 2)
        }
        for code, w in zip(codes, weights)
    ]

    return {
        "weights": weight_items,
        "expected_return_pct": _safe_round(port_ret * 100, 2),
        "volatility_pct": _safe_round(port_vol * 100, 2),
        "sharpe_ratio": _safe_round(sharpe, 3),
        "mdd_pct": mdd,
    }


def run_rebalance(codes: list, num_simulations: int = 3000, risk_free_rate: float = 0.03) -> dict:
    """
    Step 7: 단순화 몬테카를로 시뮬레이션(3,000회)과 효율적 프론티어를 계산하여
    최대 샤프 비중, 최소 변동성 비중, 동일 비중 비교 및 시각화용 데이터를 반환합니다.
    (Dify AI 미사용 — 순수 Python/NumPy 계산)
    """
    history = fetch_portfolio_history(codes)
    if not history.get("ok"):
        return {
            "ok": False,
            "error": history.get("error", "주가 데이터 수집에 실패했습니다.")
        }

    clean_codes = history["codes"]
    names = history["names"]
    returns_df = history["returns_df"]
    mean_returns = history["mean_returns"]
    cov_matrix = history["cov_matrix"]
    n_assets = len(clean_codes)

    # 1. 단순화 몬테카를로 시뮬레이션 (디리클레 분포로 합=1인 랜덤 비중 생성)
    all_weights = np.random.dirichlet(np.ones(n_assets), size=num_simulations)
    mu = mean_returns.values
    sigma = cov_matrix.values

    sim_returns = all_weights @ mu
    # 각 시뮬레이션 비중 w에 대해 sqrt(w^T * Sigma * w) 벡터 계산
    sim_vars = np.einsum("ij,jk,ik->i", all_weights, sigma, all_weights)
    sim_vols = np.sqrt(np.maximum(sim_vars, 0.0))
    sim_sharpes = np.where(sim_vols > 0, (sim_returns - risk_free_rate) / sim_vols, 0.0)

    # 2. 최적 포트폴리오 탐색 (최대 샤프 지수 / 최소 변동성 / 동일 비중 기준선)
    max_sharpe_idx = int(np.argmax(sim_sharpes))
    min_vol_idx = int(np.argmin(sim_vols))
    equal_weights = np.ones(n_assets) / n_assets

    max_sharpe_port = _evaluate_portfolio(
        all_weights[max_sharpe_idx], returns_df, mean_returns, cov_matrix, clean_codes, names, risk_free_rate
    )
    min_vol_port = _evaluate_portfolio(
        all_weights[min_vol_idx], returns_df, mean_returns, cov_matrix, clean_codes, names, risk_free_rate
    )
    equal_port = _evaluate_portfolio(
        equal_weights, returns_df, mean_returns, cov_matrix, clean_codes, names, risk_free_rate
    )

    # 3. 효율적 프론티어 산점도(Scatter) 시각화용 샘플링 (최대 300개 점)
    sample_step = max(1, num_simulations // 300)
    frontier_points = []
    for idx in range(0, num_simulations, sample_step):
        x_vol = _safe_round(sim_vols[idx] * 100, 2)
        y_ret = _safe_round(sim_returns[idx] * 100, 2)
        s_val = _safe_round(sim_sharpes[idx], 3)
        if x_vol is not None and y_ret is not None:
            frontier_points.append({"x": x_vol, "y": y_ret, "sharpe": s_val})

    # 4. 수치 기반 근거 요약 (AI 감이 아닌 계산 수치 기반)
    top_asset = max(max_sharpe_port["weights"], key=lambda item: item["weight_pct"] or 0)
    rationale = [
        f"최근 1년({history['period']}, {history['trading_days']}거래일) 실제 종가를 바탕으로 {num_simulations:,}회 무작위 포트폴리오를 시뮬레이션했습니다.",
        f"최대 샤프 비율({max_sharpe_port['sharpe_ratio']}) 포트폴리오는 '{top_asset['name']}({top_asset['code']})' 비중을 {top_asset['weight_pct']}%로 제안하며, 연 기대수익률 {max_sharpe_port['expected_return_pct']}% / 변동성 {max_sharpe_port['volatility_pct']}% / MDD {max_sharpe_port['mdd_pct']}%입니다.",
        f"최소 변동성 포트폴리오는 변동성을 {min_vol_port['volatility_pct']}%까지 낮춰(동일 비중 {equal_port['volatility_pct']}% 대비) 하락 방어에 초점을 맞춥니다.",
    ]

    logger.info(
        f"[CALC] 몬테카를로({num_simulations}회) & 효율적 프론티어 계산 완료 "
        f"(max_sharpe={max_sharpe_port['sharpe_ratio']}, min_vol={min_vol_port['volatility_pct']}%)"
    )

    return {
        "ok": True,
        "period": history["period"],
        "trading_days": history["trading_days"],
        "simulations": num_simulations,
        "risk_free_rate_pct": _safe_round(risk_free_rate * 100, 2),
        "asset_stats": history["asset_stats"],
        "max_sharpe": max_sharpe_port,
        "min_volatility": min_vol_port,
        "equal_weight": equal_port,
        "frontier_points": frontier_points,
        "rationale": rationale,
        "error": None
    }


if __name__ == "__main__":
    import json
    print("=" * 60)
    print("Step 7 단독 테스트: rebalancer.py 2차 (몬테카를로 & 효율적 프론티어)")
    print("=" * 60)

    sample_codes = ["005930", "000660", "069500"]
    res = run_rebalance(sample_codes)
    if not res["ok"]:
        print("오류:", res["error"])
    else:
        output_preview = {
            "period": res["period"],
            "simulations": res["simulations"],
            "max_sharpe": res["max_sharpe"],
            "min_volatility": res["min_volatility"],
            "equal_weight": res["equal_weight"],
            "frontier_points_count": len(res["frontier_points"]),
            "rationale": res["rationale"]
        }
        print(json.dumps(output_preview, ensure_ascii=False, indent=2))
