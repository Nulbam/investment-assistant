import os
import logging
from flask import Flask, jsonify, render_template, request
from dotenv import load_dotenv
from collector import fetch_stock_basic

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

@app.route("/health", methods=["GET"])
def health():
    """서버 상태 및 API 키 설정 여부 확인 라우트 (키 값 자체는 절대 노출 금지)"""
    serper_key = os.getenv("SERPER_API_KEY", "").strip()
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()

    # 키가 설정되어 있고 기본 더미 텍스트가 아닌지 여부만 체크 (True / False)
    is_serper_ready = bool(serper_key and serper_key != "your_serper_api_key_here")
    is_gemini_ready = bool(gemini_key and gemini_key != "your_gemini_api_key_here")

    logger.info("[HEALTH] Server health check requested")

    return jsonify({
        "status": "ok",
        "serper_api_configured": is_serper_ready,
        "gemini_api_configured": is_gemini_ready
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


if __name__ == "__main__":
    debug_mode = os.getenv("FLASK_DEBUG", "true").lower() == "true"
    logger.info("[START] Starting Flask server on http://127.0.0.1:5000")
    app.run(host="127.0.0.1", port=5000, debug=debug_mode)
