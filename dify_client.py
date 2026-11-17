import os
import json
import logging
import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

# 모드별 환경변수 키 매핑
MODE_KEY_MAP = {
    "analysis": "DIFY_ANALYSIS_API_KEY",
    "tech": "DIFY_TECH_API_KEY",
}


def _get_dify_api_key(mode: str) -> tuple:
    """모드('analysis' | 'tech')에 맞는 Dify API 키와 환경변수 이름을 반환합니다."""
    env_name = MODE_KEY_MAP.get(mode)
    if not env_name:
        return None, None
    key_val = os.getenv(env_name, "").strip()
    if not key_val or key_val.startswith("your_dify_"):
        return None, env_name
    return key_val, env_name


def _build_query_with_context(mode: str, user_query: str, context_data=None) -> str:
    """
    Dify 일반 챗봇(Chatbot)이 별도 워크플로우 변수 없이도 근거를 읽을 수 있도록
    query 문자열에 근거 데이터(JSON 또는 계산 수치)를 조합합니다.
    """
    if not context_data:
        return user_query

    if isinstance(context_data, (dict, list)):
        context_str = json.dumps(context_data, ensure_ascii=False, indent=2)
    else:
        context_str = str(context_data)

    if mode == "analysis":
        return (
            f"[종목 분석 근거 데이터(JSON)]\n{context_str}\n\n"
            f"[사용자 질문]\n{user_query}\n\n"
            "위 근거 데이터에 포함된 수치와 뉴스만 바탕으로 분석해 주세요."
        )
    if mode == "tech":
        return (
            f"[계산된 기술지표 수치]\n{context_str}\n\n"
            f"[사용자 질문]\n{user_query}\n\n"
            "위 계산된 기술지표 숫자만을 근거로 초보자도 이해하기 쉽게 설명해 주세요."
        )
    return f"[참고 데이터]\n{context_str}\n\n[사용자 질문]\n{user_query}"


def ask_dify_chatbot(
    mode: str,
    user_query: str,
    context_data=None,
    conversation_id: str = "",
    user_id: str = "investment-user",
    timeout: int = 45,
) -> dict:
    """
    Dify 챗봇(/chat-messages) API를 호출합니다.
    mode: 'analysis' (탭1 종목 심층분석) | 'tech' (탭3 기술지표 설명)
    """
    query_clean = (user_query or "").strip()
    if not query_clean:
        return {
            "ok": False,
            "answer": None,
            "conversation_id": conversation_id or "",
            "error": "질문 내용을 입력해 주세요."
        }

    api_key, env_name = _get_dify_api_key(mode)
    if not env_name:
        return {
            "ok": False,
            "answer": None,
            "conversation_id": conversation_id or "",
            "error": f"지원하지 않는 Dify 호출 모드입니다: {mode}"
        }

    if not api_key:
        err_msg = f"{env_name}가 설정되어 있지 않습니다. (.env 파일에 Dify 챗봇 API 키를 입력해 주세요.)"
        logger.warning(f"[ERROR] {err_msg}")
        return {
            "ok": False,
            "answer": None,
            "conversation_id": conversation_id or "",
            "error": err_msg
        }

    base_url = os.getenv("DIFY_BASE_URL", "https://api.dify.ai/v1").strip().rstrip("/")
    endpoint = f"{base_url}/chat-messages"
    final_query = _build_query_with_context(mode, query_clean, context_data)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "inputs": {},
        "query": final_query,
        "response_mode": "blocking",
        "conversation_id": conversation_id or "",
        "user": user_id,
    }

    logger.info(
        f"[DIFY] Dify 챗봇 API 호출 시작 (mode={mode}, has_context={bool(context_data)}, "
        f"has_conv_id={bool(conversation_id)})"
    )

    try:
        resp = requests.post(endpoint, headers=headers, json=payload, timeout=timeout)

        if resp.status_code == 401:
            err_msg = f"Dify API 인증에 실패했습니다. (.env의 {env_name}가 올바른지 확인해 주세요.)"
            logger.error(f"[ERROR] {err_msg}")
            return {"ok": False, "answer": None, "conversation_id": conversation_id or "", "error": err_msg}

        if resp.status_code == 404:
            err_msg = "Dify API 엔드포인트를 찾을 수 없습니다. (DIFY_BASE_URL 또는 conversation_id를 확인해 주세요.)"
            logger.error(f"[ERROR] {err_msg}")
            return {"ok": False, "answer": None, "conversation_id": conversation_id or "", "error": err_msg}

        resp.raise_for_status()
        data = resp.json()

        answer = data.get("answer", "")
        new_conv_id = data.get("conversation_id", conversation_id or "")

        logger.info(f"[RESPONSE] Dify 챗봇 응답 수신 완료 (mode={mode}, answer_len={len(answer)})")
        return {
            "ok": True,
            "answer": answer,
            "conversation_id": new_conv_id,
            "error": None
        }

    except requests.exceptions.Timeout:
        err_msg = "Dify 챗봇 응답 시간이 초과되었습니다 (타임아웃). 잠시 후 다시 시도해 주세요."
        logger.error(f"[ERROR] {err_msg}")
        return {"ok": False, "answer": None, "conversation_id": conversation_id or "", "error": err_msg}
    except requests.exceptions.RequestException as e:
        err_msg = f"Dify 챗봇 API 호출 실패: {type(e).__name__}"
        logger.error(f"[ERROR] {err_msg}")
        return {"ok": False, "answer": None, "conversation_id": conversation_id or "", "error": err_msg}
    except ValueError:
        err_msg = "Dify 챗봇 응답 JSON 파싱에 실패했습니다."
        logger.error(f"[ERROR] {err_msg}", exc_info=True)
        return {"ok": False, "answer": None, "conversation_id": conversation_id or "", "error": err_msg}


if __name__ == "__main__":
    print("=" * 60)
    print("Step 5 단독 테스트: dify_client.py")
    print("=" * 60)

    sample_context = {"name": "SK하이닉스", "per": 4.93, "pbr": 2.99}
    res_analysis = ask_dify_chatbot("analysis", "현재 밸류에이션을 평가해줘.", context_data=sample_context)
    print("1) analysis 모드 결과:", json.dumps(res_analysis, ensure_ascii=False, indent=2))

    res_tech = ask_dify_chatbot("tech", "RSI가 과매수인가요?", context_data={"rsi_14": 68.4})
    print("2) tech 모드 결과:", json.dumps(res_tech, ensure_ascii=False, indent=2))
