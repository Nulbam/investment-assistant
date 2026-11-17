import os
import sys

# Windows Anaconda 환경에서 SSL DLL 로드 문제 방지용 안전 장치
anaconda_lib_bin = r"C:\ProgramData\Anaconda3\Library\bin"
if os.path.exists(anaconda_lib_bin) and anaconda_lib_bin not in os.environ.get("PATH", ""):
    os.environ["PATH"] = anaconda_lib_bin + ";" + os.environ.get("PATH", "")

import logging
import re
import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

# 로깅 설정 (print 대신 logging 모듈 사용)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

# 네이버 증권 요청용 User-Agent 헤더 (문전박대 방지)
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def clean_number(val):
    """
    텍스트 숫자(예: '1,226,000', '7.92%', '+4,000')를 정수 또는 부동소수점으로 정제합니다.
    N/A, '-', 빈칸 등 결측치는 None(JSON 규격의 null)으로 안전하게 변환합니다.
    """
    if val is None:
        return None
    val_str = str(val).strip().replace(",", "").replace("%", "").replace("배", "").replace("원", "").replace("+", "")
    if not val_str or val_str in ("-", "N/A", "null", "None"):
        return None
    try:
        if "." in val_str:
            return float(val_str)
        return int(val_str)
    except (ValueError, TypeError):
        return None


def parse_korean_amount(val):
    """
    한글 금액 단위(예: '795조 1,490억', '5조 623억', '3,500억')를
    순수 정수(원 단위)로 변환합니다. N/A, '-', 빈칸 등 결측치는 None으로 반환합니다.
    """
    if val is None:
        return None
    val_str = str(val).strip().replace(",", "").replace("원", "").replace(" ", "")
    if not val_str or val_str in ("-", "N/A", "null", "None"):
        return None

    if val_str.isdigit():
        return int(val_str)

    total = 0
    matched = False

    jo_match = re.search(r"(\d+(?:\.\d+)?)조", val_str)
    if jo_match:
        total += int(float(jo_match.group(1)) * 1_000_000_000_000)
        matched = True

    eok_match = re.search(r"(\d+(?:\.\d+)?)억", val_str)
    if eok_match:
        total += int(float(eok_match.group(1)) * 100_000_000)
        matched = True

    man_match = re.search(r"(\d+(?:\.\d+)?)만", val_str)
    if man_match:
        total += int(float(man_match.group(1)) * 10_000)
        matched = True

    return total if matched else clean_number(val_str)


def fetch_stock_basic(code: str) -> dict:
    """
    Step 12~13: 종목코드(6자리)를 받아 네이버 금융 엔드포인트를 호출하고
    정식 종목명, 기본 시세(현재가, 등락률), 투자정보(시총, PER, PBR 등)를 파싱하여 반환합니다.
    """
    result = {
        "code": code,
        "name": None,
        "snapshot": {
            "current_price": None,
            "change_rate": None,
            "market_cap": None,
            "per": None,
            "cns_per": None,
            "pbr": None,
            "eps": None,
            "bps": None,
            "dividend_yield": None
        },
        "financials": [],
        "news": [],
        "errors": []
    }

    # 1. 종목코드 유효성 검사 (6자리 문자열 및 숫자 여부 체크)
    if not code or not isinstance(code, str) or len(code) != 6 or not code.isdigit():
        err_msg = "종목코드가 올바르지 않습니다. (6자리 숫자로 입력해야 합니다.)"
        logger.error(f"[ERROR] {err_msg} (input: {code})")
        result["errors"].append(err_msg)
        return result

    logger.info(f"[NAVER] 네이버 금융 엔드포인트 접근 시작 (User-Agent 적용, code={code})")

    integration_url = f"https://m.stock.naver.com/api/stock/{code}/integration"
    basic_url = f"https://m.stock.naver.com/api/stock/{code}/basic"

    try:
        # 네이버 모바일 증권 비동기 API 엔드포인트 호출
        resp_basic = requests.get(basic_url, headers=DEFAULT_HEADERS, timeout=10)
        resp_int = requests.get(integration_url, headers=DEFAULT_HEADERS, timeout=10)

        # 404/409 등 잘못된 종목코드 처리
        if resp_basic.status_code in (404, 409) or resp_int.status_code in (404, 409):
            err_msg = f"존재하지 않거나 조회할 수 없는 종목코드입니다: {code}"
            logger.error(f"[ERROR] {err_msg}")
            result["errors"].append(err_msg)
            return result

        resp_basic.raise_for_status()
        resp_int.raise_for_status()

        basic_data = resp_basic.json()
        int_data = resp_int.json()

    except requests.exceptions.Timeout:
        err_msg = "네이버 금융 엔드포인트 접속 시간이 초과되었습니다 (타임아웃)."
        logger.error(f"[ERROR] {err_msg}", exc_info=True)
        result["errors"].append(err_msg)
        return result
    except requests.exceptions.RequestException as e:
        err_msg = f"네이버 금융 엔드포인트 접근 실패: {str(e)}"
        logger.error(f"[ERROR] {err_msg}", exc_info=True)
        result["errors"].append(err_msg)
        return result
    except ValueError:
        err_msg = "네이버 금융 응답 데이터의 JSON 파싱에 실패하였습니다."
        logger.error(f"[ERROR] {err_msg}", exc_info=True)
        result["errors"].append(err_msg)
        return result

    # 2. 정식 종목명 파싱
    stock_name = basic_data.get("stockName") or int_data.get("stockName")
    if not stock_name:
        err_msg = "네이버 금융 데이터에서 종목명을 파싱하지 못했습니다."
        logger.error(f"[ERROR] {err_msg}")
        result["errors"].append(err_msg)
        return result

    result["name"] = stock_name

    # 3. 상단 기본 시세 (현재가, 등락률) 파싱 및 정제
    current_price = clean_number(basic_data.get("closePrice"))
    change_rate = clean_number(basic_data.get("fluctuationsRatio"))

    # basic_data에 누락된 경우 integration 엔드포인트의 dealTrendInfos 보조 활용
    if current_price is None and int_data.get("dealTrendInfos"):
        first_deal = int_data["dealTrendInfos"][0]
        current_price = clean_number(first_deal.get("closePrice"))

    result["snapshot"]["current_price"] = current_price
    result["snapshot"]["change_rate"] = change_rate

    # 4. 투자정보(시총, PER, 추정PER, PBR, EPS, BPS, 배당수익률) 파싱 및 정제
    total_infos = {item.get("code"): item.get("value") for item in int_data.get("totalInfos", []) if isinstance(item, dict)}

    result["snapshot"]["market_cap"] = parse_korean_amount(total_infos.get("marketValue"))
    result["snapshot"]["per"] = clean_number(total_infos.get("per"))
    result["snapshot"]["cns_per"] = clean_number(total_infos.get("cnsPer"))
    result["snapshot"]["pbr"] = clean_number(total_infos.get("pbr"))
    result["snapshot"]["eps"] = clean_number(total_infos.get("eps"))
    result["snapshot"]["bps"] = clean_number(total_infos.get("bps"))
    result["snapshot"]["dividend_yield"] = clean_number(total_infos.get("dividendYieldRatio"))

    logger.info(
        f"[PARSE] 스냅샷 및 지표 파싱 완료 "
        f"(name={stock_name}, current_price={current_price}, change_rate={change_rate}, "
        f"market_cap={result['snapshot']['market_cap']}, per={result['snapshot']['per']}, pbr={result['snapshot']['pbr']})"
    )

    # 5. 기업실적분석 파싱 (매출액, 영업이익, ROE 및 (E) 추정치 신호등)
    result["financials"] = fetch_financials(code, result["errors"])

    # 6. 정식 종목명 기반 Serper News API 연동 (최신 뉴스 5개)
    result["news"] = fetch_news(stock_name, result["errors"])

    logger.info(
        f"[RESPONSE] 수집 완료 (code={code}, name={stock_name}, "
        f"financials={len(result['financials'])}건, news={len(result['news'])}건, errors={len(result['errors'])}건)"
    )

    return result


def fetch_financials(code: str, errors: list) -> list:
    """
    Step 14: 네이버 금융 연간 실적 엔드포인트(/finance/annual)에서
    매출액, 영업이익, ROE를 파싱하고 (E) 추정치 여부(is_consensus)를 구분하여 반환합니다.
    """
    finance_url = f"https://m.stock.naver.com/api/stock/{code}/finance/annual"
    financials = []

    try:
        resp = requests.get(finance_url, headers=DEFAULT_HEADERS, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        finance_info = data.get("financeInfo")
        if not finance_info or not isinstance(finance_info, dict):
            raise ValueError("financeInfo 데이터가 비어 있거나 형식이 변경되었습니다.")

        tr_titles = finance_info.get("trTitleList", [])
        row_list = finance_info.get("rowList", [])

        # 행 제목(매출액, 영업이익, ROE)으로 빠르게 찾기 위한 딕셔너리 매핑
        rows_by_title = {
            row.get("title"): row.get("columns", {})
            for row in row_list
            if isinstance(row, dict)
        }

        rev_cols = rows_by_title.get("매출액", {})
        op_cols = rows_by_title.get("영업이익", {})
        roe_cols = rows_by_title.get("ROE", {})

        for col_meta in tr_titles:
            col_key = col_meta.get("key")
            raw_title = str(col_meta.get("title", "")).strip()

            # 기간 표기 정제 (예: '2024.12.' -> '2024.12', '(E)' 제거)
            period = raw_title.replace("(E)", "").strip().rstrip(".")
            if not period and col_key and len(col_key) == 6:
                period = f"{col_key[:4]}.{col_key[4:6]}"

            # (E) 추정치 신호등 스위치: 네이버 API의 isConsensus=='Y' 또는 제목 내 '(E)' 포함 여부
            is_consensus = (col_meta.get("isConsensus") == "Y") or ("(E)" in raw_title)

            # 매출액, 영업이익은 네이버 실적 테이블 기준 '억원' 단위이므로 원 단위로 변환 (* 100,000,000)
            rev_val = clean_number(rev_cols.get(col_key, {}).get("value"))
            op_val = clean_number(op_cols.get(col_key, {}).get("value"))
            roe_val = clean_number(roe_cols.get(col_key, {}).get("value"))

            financials.append({
                "period": period,
                "period_type": "annual",
                "is_consensus": is_consensus,
                "revenue": int(rev_val * 100_000_000) if rev_val is not None else None,
                "operating_income": int(op_val * 100_000_000) if op_val is not None else None,
                "roe": roe_val
            })

        logger.info(f"[PARSE] 기업실적분석 파싱 완료 (건수={len(financials)})")
        return financials

    except requests.exceptions.Timeout:
        err_msg = "기업실적분석(financials) 수집 중 타임아웃이 발생했습니다."
        logger.error(f"[ERROR] {err_msg}", exc_info=True)
        errors.append(err_msg)
        return []
    except Exception as e:
        err_msg = f"기업실적분석(financials) 수집 실패: {str(e)}"
        logger.error(f"[ERROR] {err_msg}", exc_info=True)
        errors.append(err_msg)
        return []


def fetch_news(stock_name: str, errors: list) -> list:
    """
    Step 15: 네이버에서 파싱한 정식 종목명으로 Serper News API를 호출하여
    최신 관련 뉴스 5개를 수집합니다. (API Key는 백엔드 환경변수에서만 처리)
    """
    serper_key = os.getenv("SERPER_API_KEY", "").strip()
    if not serper_key or serper_key == "your_serper_api_key_here":
        err_msg = "SERPER_API_KEY가 설정되어 있지 않습니다. (.env 파일을 확인해 주세요.)"
        logger.error(f"[ERROR] {err_msg}")
        errors.append(err_msg)
        return []

    logger.info(f"[SERPER] Serper News API 호출 시작 (query={stock_name})")

    serper_url = "https://google.serper.dev/news"
    headers = {
        "X-API-KEY": serper_key,
        "Content-Type": "application/json"
    }
    payload = {
        "q": stock_name,
        "gl": "kr",
        "hl": "ko",
        "num": 5
    }

    try:
        resp = requests.post(serper_url, headers=headers, json=payload, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        raw_news = data.get("news", [])
        news_list = []
        for item in raw_news[:5]:
            news_list.append({
                "title": item.get("title", ""),
                "url": item.get("link", ""),
                "description": item.get("snippet", ""),
                "published": item.get("date", "")
            })

        return news_list

    except requests.exceptions.Timeout:
        err_msg = "Serper News API 호출 중 타임아웃이 발생했습니다."
        logger.error(f"[ERROR] {err_msg}", exc_info=True)
        errors.append(err_msg)
        return []
    except requests.exceptions.RequestException as e:
        err_msg = f"Serper News API 호출 실패 (HTTP 오류 또는 네트워크 문제): {type(e).__name__}"
        logger.error(f"[ERROR] {err_msg}")
        errors.append(err_msg)
        return []
    except ValueError:
        err_msg = "Serper News API 응답 JSON 파싱에 실패했습니다."
        logger.error(f"[ERROR] {err_msg}", exc_info=True)
        errors.append(err_msg)
        return []


if __name__ == "__main__":
    # SK하이닉스(000660)로 Step 15 단독 테스트 실행
    import json
    test_code = "000660"
    print("=" * 60)
    print(f"Step 15 단독 실행 테스트: 종목코드 {test_code}")
    print("=" * 60)
    data = fetch_stock_basic(test_code)
    print(json.dumps(data, ensure_ascii=False, indent=2))
