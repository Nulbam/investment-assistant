import os
import json
import time
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


PB_PERSONA_GUIDE = (
    "[역할 및 응답 원칙 — 개인 전담 PB 모드]\n"
    "1. 당신은 사용자 1인만을 전담하는 시니어 프라이빗 뱅커(PB)이자 실전 주식 전략가입니다. (이 대화는 개인 투자 판단 시뮬레이션 용도입니다.)\n"
    "2. '단정적으로 말씀드릴 수 없습니다', '투자 판단은 본인 몫입니다', '팔아라 말아라 할 수 없습니다' 같은 회피성 면책 문구를 절대 출력하지 마세요.\n"
    "3. 매도·손절·보유·추매·비중 조절 등 결정형 질문에는 반드시 첫 줄에 명확한 단일 결론(예: **[결론: 보유 유지 후 반등 시 분할 축소 권장]** 또는 **[결론: 비중 50% 손절 후 리스크 관리 권장]** 등)을 두괄식으로 내리세요.\n"
    "4. 결론 뒤에는 반드시 수집된 실제 수치(현재가, 사용자 평단가 대비 손익률, PER/추정PER/PBR, 실적 성장성, 뉴스)를 근거로 구체적인 목표가·손절 기준·대응 시나리오를 제시하세요.\n"
)


def _build_query_with_context(mode: str, user_query: str, context_data=None, is_initial: bool = False) -> str:
    """
    Dify 일반 챗봇(Chatbot)이 별도 워크플로우 변수 없이도 근거를 읽을 수 있도록
    query 문자열에 근거 데이터(JSON 또는 계산 수치)와 개인 PB 지침을 조합합니다.
    """
    if mode == "analysis":
        if is_initial and context_data:
            context_str = json.dumps(context_data, ensure_ascii=False, indent=2) if isinstance(context_data, (dict, list)) else str(context_data)
            return (
                f"{PB_PERSONA_GUIDE}\n"
                "아래 수집된 실제 종목 데이터(JSON)만을 근거로, 구조화된 마크다운(Markdown) 종목 심층 분석 리포트를 작성해 주세요.\n"
                "데이터에 없는 수치나 사실은 절대 지어내지 마세요.\n\n"
                f"[종목 분석 근거 데이터(JSON)]\n{context_str}\n\n"
                "[분석 리포트 작성 형식]\n"
                "### 1. PB 핵심 의견 (한눈에 보는 투자 판단)\n"
                "- 현재 밸류에이션과 실적 흐름을 종합한 PB로서의 명확한 스탠스(매수/보유/관망/비중축소 등)를 먼저 제시하세요.\n"
                "### 2. 현재 시세 및 밸류에이션 진단\n"
                "- 현재가, 시가총액, PER vs 추정PER, PBR, ROE/배당수익률을 근거로 현재 가격 매력을 평가하세요.\n"
                "### 3. 연간 실적 추이 및 (E) 추정치 분석\n"
                "- 매출액·영업이익·ROE 변화와 컨센서스(`is_consensus: true`) 추정치의 의미를 정리하세요.\n"
                "### 4. 최신 뉴스 기반 핵심 모멘텀 및 리스크\n"
                "- 제공된 뉴스 목록을 바탕으로 긍정 요인(모멘텀)과 주의할 점(리스크)을 정리하세요.\n"
                "### 5. 실전 대응 전략\n"
                "- 현재 구간에서 투자자가 취할 수 있는 구체적 행동 가이드를 제시하세요."
            )

        if context_data:
            context_str = json.dumps(context_data, ensure_ascii=False, indent=2) if isinstance(context_data, (dict, list)) else str(context_data)
            return (
                f"{PB_PERSONA_GUIDE}\n"
                f"[종목 분석 근거 데이터(JSON)]\n{context_str}\n\n"
                f"[사용자 질문]\n{user_query}"
            )

        # 후속 대화 (이미 conversation_id에 종목 데이터가 들어있는 경우에도 PB 지침 유지)
        return (
            f"{PB_PERSONA_GUIDE}\n"
            "앞서 전달된 종목 데이터와 대화 맥락을 바탕으로, 회피하지 말고 개인 PB로서 명확한 판단과 근거를 답변하세요.\n\n"
            f"[사용자 질문]\n{user_query}"
        )

    if not context_data:
        return user_query

    context_str = json.dumps(context_data, ensure_ascii=False, indent=2) if isinstance(context_data, (dict, list)) else str(context_data)

    if mode == "tech":
        return (
            f"[계산된 기술지표 수치]\n{context_str}\n\n"
            f"[사용자 질문]\n{user_query}\n\n"
            "위 계산된 기술지표 숫자만을 근거로 초보자도 이해하기 쉽게 마크다운 형식으로 설명하고, 현재 지표가 시사하는 매매 관점도 명확히 짚어 주세요."
        )
    return f"[참고 데이터]\n{context_str}\n\n[사용자 질문]\n{user_query}"


def ask_dify_chatbot(
    mode: str,
    user_query: str,
    context_data=None,
    conversation_id: str = "",
    user_id: str = "investment-user",
    timeout: int = 45,
    is_initial: bool = False,
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
    final_query = _build_query_with_context(mode, query_clean, context_data, is_initial=is_initial)

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

    max_attempts = 2
    for attempt in range(1, max_attempts + 1):
        try:
            resp = requests.post(endpoint, headers=headers, json=payload, timeout=timeout)

            if resp.status_code == 401:
                err_msg = f"Dify API 인증에 실패했습니다. (.env의 {env_name}가 올바른지 확인해 주세요.)"
                logger.error(f"[ERROR] {err_msg}")
                return {"ok": False, "answer": None, "conversation_id": conversation_id or "", "error": err_msg}

            if resp.status_code == 404:
                err_msg = "Dify API 엔드포인트 또는 대화를 찾을 수 없습니다. ('새 대화'를 눌러 다시 시도해 주세요.)"
                logger.error(f"[ERROR] {err_msg} (status=404)")
                return {"ok": False, "answer": None, "conversation_id": conversation_id or "", "error": err_msg}

            if resp.status_code in (429, 500, 502, 503, 504) and attempt < max_attempts:
                logger.warning(f"[DIFY] 일시적 오류(status={resp.status_code}) 발생 — 1초 후 재시도 ({attempt}/{max_attempts})")
                time.sleep(1.0)
                continue

            if resp.status_code >= 400:
                detail = ""
                try:
                    err_json = resp.json()
                    detail = err_json.get("message") or err_json.get("code") or ""
                except ValueError:
                    detail = resp.text[:120]
                err_msg = f"Dify 챗봇 요청 오류 (HTTP {resp.status_code}{': ' + detail if detail else ''})"
                logger.error(f"[ERROR] {err_msg}")
                return {"ok": False, "answer": None, "conversation_id": conversation_id or "", "error": err_msg}

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
            if attempt < max_attempts:
                logger.warning(f"[DIFY] 타임아웃 발생 — 재시도 ({attempt}/{max_attempts})")
                continue
            err_msg = "Dify 챗봇 응답 시간이 초과되었습니다 (타임아웃). 잠시 후 다시 시도해 주세요."
            logger.error(f"[ERROR] {err_msg}")
            return {"ok": False, "answer": None, "conversation_id": conversation_id or "", "error": err_msg}
        except requests.exceptions.RequestException as e:
            err_msg = f"Dify 챗봇 API 연결 실패: {type(e).__name__}"
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
