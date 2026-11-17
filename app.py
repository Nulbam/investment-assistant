import os
import logging
from flask import Flask, jsonify, render_template, request
from dotenv import load_dotenv
from collector import fetch_stock_basic
from rebalancer import run_rebalance
from indicators import calculate_indicators
from dify_client import ask_dify_chatbot

# .env 환경변수 로드
load_dotenv()

# 로깅 설정 (print 대신 logging 모듈 사용)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

@app.route("/")
def index():
    """메인 페이지"""
    # templates/index.html 파일이 있으면 렌더링하고, 없으면 기본 메시지 반환
    if os.path.exists(os.path.join(app.template_folder or "templates", "index.html")):
        return render_template("index.html")
    return "<h1>Stock Data Collector & Briefing Tool</h1><p>Flask Server is running. (Step 11: /health available)</p>"


@app.route("/test")
def test_collector_page():
    """기존 1차 종목 데이터 수집기 테스트 화면 (보존용)"""
    logger.info("[REQUEST] GET /test")
    return render_template("test.html")


@app.route("/health", methods=["GET"])
def health():
    """서버 상태 및 API 키 설정 여부 확인 라우트 (키 값 자체는 절대 노출 금지)"""
    serper_key = os.getenv("SERPER_API_KEY", "").strip()
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    dify_analysis_key = os.getenv("DIFY_ANALYSIS_API_KEY", "").strip()
    dify_tech_key = os.getenv("DIFY_TECH_API_KEY", "").strip()

    # 키가 설정되어 있고 기본 더미 텍스트가 아닌지 여부만 체크 (True / False)
    is_serper_ready = bool(serper_key and serper_key != "your_serper_api_key_here")
    is_gemini_ready = bool(gemini_key and gemini_key != "your_gemini_api_key_here")
    is_dify_analysis_ready = bool(
        dify_analysis_key and not dify_analysis_key.startswith("your_dify_")
    )
    is_dify_tech_ready = bool(
        dify_tech_key and not dify_tech_key.startswith("your_dify_")
    )

    logger.info("[HEALTH] Server health check requested")

    return jsonify({
        "status": "ok",
        "serper_api_configured": is_serper_ready,
        "gemini_api_configured": is_gemini_ready,
        "dify_analysis_configured": is_dify_analysis_ready,
        "dify_tech_configured": is_dify_tech_ready
    }), 200


@app.route("/fetch", methods=["POST"])
def fetch():
    """종목코드를 받아 네이버 금융 수집 + Serper 뉴스 검색을 통합 실행하고 최종 JSON 반환"""
    body = request.get_json(silent=True) or {}
    raw_code = body.get("code") if isinstance(body, dict) else None
    if raw_code is None:
        raw_code = request.form.get("code", "")

    code = str(raw_code).strip() if raw_code is not None else ""
    logger.info(f"[REQUEST] POST /fetch code={code}")

    # 1. 종목코드 미입력 체크
    if not code:
        err_msg = "종목코드를 입력해 주세요."
        logger.warning(f"[ERROR] {err_msg}")
        return jsonify({
            "code": "",
            "name": None,
            "snapshot": {},
            "financials": [],
            "news": [],
            "errors": [err_msg]
        }), 400

    # 2. 6자리 숫자 문자열 여부 체크
    if len(code) != 6 or not code.isdigit():
        err_msg = "종목코드는 6자리 숫자여야 합니다. (예: 000660)"
        logger.warning(f"[ERROR] {err_msg} (input={code})")
        return jsonify({
            "code": code,
            "name": None,
            "snapshot": {},
            "financials": [],
            "news": [],
            "errors": [err_msg]
        }), 400

    # 3. 통합 데이터 수집 실행
    try:
        data = fetch_stock_basic(code)
    except Exception as e:
        err_msg = f"데이터 수집 중 예기치 않은 서버 오류가 발생했습니다: {str(e)}"
        logger.error(f"[ERROR] {err_msg}", exc_info=True)
        return jsonify({
            "code": code,
            "name": None,
            "snapshot": {},
            "financials": [],
            "news": [],
            "errors": [err_msg]
        }), 500

    # 종목명조차 파싱 실패한 경우 (존재하지 않는 종목코드 등) 404 반환
    status_code = 200 if data.get("name") else 404
    logger.info(
        f"[RESPONSE] POST /fetch 완료 (code={code}, status={status_code}, "
        f"errors={len(data.get('errors', []))}건)"
    )
    return jsonify(data), status_code


@app.route("/api/analyze-chat", methods=["POST"])
def api_analyze_chat():
    """[탭1] 종목코드 기반 근거 수집(collector.py) + Dify 챗봇① 심층분석 호출"""
    body = request.get_json(silent=True) or {}
    code = str(body.get("code", "")).strip()
    query = str(body.get("query", "")).strip()
    use_tool = bool(body.get("use_tool", True))
    is_initial = bool(body.get("is_initial", False))
    conversation_id = str(body.get("conversation_id", "")).strip()
    prefetched = body.get("collected_data")

    logger.info(f"[REQUEST] POST /api/analyze-chat code={code}, use_tool={use_tool}, is_initial={is_initial}")

    if not query and not is_initial:
        return jsonify({"ok": False, "answer": None, "conversation_id": conversation_id, "error": "질문을 입력해 주세요."}), 400

    if is_initial and not query:
        query = f"{code} 종목에 대한 전문가 심층 분석 리포트를 작성해 주세요."

    collected_data = None
    if use_tool:
        if isinstance(prefetched, dict) and prefetched.get("name"):
            collected_data = prefetched
        elif not conversation_id:
            if not code or len(code) != 6 or not code.isdigit():
                return jsonify({
                    "ok": False,
                    "answer": None,
                    "conversation_id": conversation_id,
                    "error": "근거 수집 분석을 위해 6자리 숫자 종목코드를 입력해 주세요. (예: 000660)"
                }), 400

            collected_data = fetch_stock_basic(code)
            if not collected_data.get("name"):
                errs = collected_data.get("errors") or ["종목 정보를 수집하지 못했습니다."]
                return jsonify({
                    "ok": False,
                    "answer": None,
                    "conversation_id": conversation_id,
                    "collected_data": collected_data,
                    "error": errs[0]
                }), 404

    dify_res = ask_dify_chatbot(
        mode="analysis",
        user_query=query,
        context_data=collected_data,
        conversation_id=conversation_id,
        is_initial=is_initial,
    )

    status_code = 200 if dify_res["ok"] else 400
    return jsonify({
        "ok": dify_res["ok"],
        "answer": dify_res["answer"],
        "conversation_id": dify_res["conversation_id"],
        "collected_data": collected_data,
        "error": dify_res["error"]
    }), status_code


@app.route("/api/rebalance", methods=["POST"])
def api_rebalance():
    """[탭2] 다중 종목 FDR 1년 데이터 기반 몬테카를로 & 효율적 프론티어 계산 (Dify 미사용)"""
    body = request.get_json(silent=True) or {}
    raw_codes = body.get("codes", [])

    if isinstance(raw_codes, str):
        codes = [c.strip() for c in raw_codes.split(",") if c.strip()]
    elif isinstance(raw_codes, list):
        codes = [str(c).strip() for c in raw_codes if str(c).strip()]
    else:
        codes = []

    logger.info(f"[REQUEST] POST /api/rebalance codes={codes}")
    result = run_rebalance(codes)
    status_code = 200 if result.get("ok") else 400
    logger.info(f"[RESPONSE] POST /api/rebalance 완료 (ok={result.get('ok')})")
    return jsonify(result), status_code


@app.route("/api/indicators", methods=["POST"])
def api_indicators():
    """[탭3] 종목코드 기반 FDR 주가 수집 + MA/RSI/MACD/볼린저밴드 계산"""
    body = request.get_json(silent=True) or {}
    code = str(body.get("code", "")).strip()
    logger.info(f"[REQUEST] POST /api/indicators code={code}")

    result = calculate_indicators(code)
    status_code = 200 if result.get("ok") else 400
    logger.info(f"[RESPONSE] POST /api/indicators 완료 (ok={result.get('ok')})")
    return jsonify(result), status_code


@app.route("/api/tech-chat", methods=["POST"])
def api_tech_chat():
    """[탭3] 계산된 기술지표 숫자를 숨겨서 주입하고 Dify 챗봇③으로 설명 답변 생성"""
    body = request.get_json(silent=True) or {}
    code = str(body.get("code", "")).strip()
    query = str(body.get("query", "")).strip()
    latest_summary = body.get("latest_summary")
    conversation_id = str(body.get("conversation_id", "")).strip()

    logger.info(f"[REQUEST] POST /api/tech-chat code={code}, has_summary={bool(latest_summary)}")

    if not query:
        return jsonify({"ok": False, "answer": None, "conversation_id": conversation_id, "error": "질문을 입력해 주세요."}), 400

    # 요약 수치가 함께 전달되지 않은 경우 종목코드로 즉시 계산
    if not latest_summary:
        if not code or len(code) != 6 or not code.isdigit():
            return jsonify({
                "ok": False,
                "answer": None,
                "conversation_id": conversation_id,
                "error": "먼저 6자리 종목코드로 기술지표를 조회해 주세요."
            }), 400
        calc_res = calculate_indicators(code)
        if not calc_res.get("ok"):
            return jsonify({
                "ok": False,
                "answer": None,
                "conversation_id": conversation_id,
                "error": calc_res.get("error", "기술지표 계산에 실패했습니다.")
            }), 400
        latest_summary = calc_res["latest_summary"]

    dify_res = ask_dify_chatbot(
        mode="tech",
        user_query=query,
        context_data=latest_summary,
        conversation_id=conversation_id
    )

    status_code = 200 if dify_res["ok"] else 400
    return jsonify({
        "ok": dify_res["ok"],
        "answer": dify_res["answer"],
        "conversation_id": dify_res["conversation_id"],
        "error": dify_res["error"]
    }), status_code


if __name__ == "__main__":
    debug_mode = os.getenv("FLASK_DEBUG", "true").lower() == "true"
    logger.info("[START] Starting Flask server on http://127.0.0.1:5000")
    app.run(host="127.0.0.1", port=5000, debug=debug_mode)
