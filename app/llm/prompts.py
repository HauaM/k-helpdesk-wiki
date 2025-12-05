"""
LLM Prompt Templates
Pre-defined prompts for manual generation and validation

RFP Reference: Section 7 - LLM 활용 규칙
"""


# System prompt for all manual generation tasks
SYSTEM_PROMPT_BASE = """
You are a knowledge management assistant for a customer support system.

CRITICAL RULES - 환각(Hallucination) 방지:
1. You MUST ONLY use words and information from the input text
2. You MUST NOT create new information, suggestions, or policies
3. You MUST NOT infer or assume anything beyond what is explicitly stated
4. You MUST NOT add numbers, dates, or regulations not present in input
5. If information is unclear or missing, leave it as-is or mark as "정보 없음"

Your role is to ORGANIZE and SUMMARIZE existing content, NOT to create new content.
"""


# Prompt for keyword extraction (RFP Section 5.1, Step 4)
PROMPT_EXTRACT_KEYWORDS = """
다음 상담 내용에서 핵심 키워드 1~3개를 추출하세요.

규칙:
- 반드시 입력 텍스트에 있는 단어만 사용할 것
- 새로운 단어나 개념을 만들지 말 것
- 가장 중요한 키워드 1~3개만 추출

입력:
{consultation_text}

응답 형식 (JSON):
{{
  "keywords": ["키워드1", "키워드2", "키워드3"]
}}
"""


# Prompt for manual draft generation (RFP Section 5.1, Step 5)
PROMPT_GENERATE_MANUAL_DRAFT = """
다음 상담 내용을 바탕으로 메뉴얼 항목을 작성하세요.

규칙:
- 입력된 내용만 사용하여 정리할 것
- 새로운 조치사항이나 정책을 만들지 말 것
- 명확하지 않은 내용은 "정보 부족"으로 표시할 것
- 숫자, 날짜, 규정은 입력에 있는 그대로만 사용할 것

입력:
문의내용: {inquiry_text}
조치내용: {action_taken}
업무구분: {business_type}
에러코드: {error_code}

응답 형식 (JSON):
{{
  "topic": "소재/주제 (짧게 요약)",
  "background": "상담 내용 기반 배경 설명",
  "guideline": "조치사항 요약 및 정리",
  "notes": "입력에 없는 내용은 생성하지 않았음을 명시"
}}
"""


# Prompt for comparing manual entries (RFP Section 5.2, Step 4)
PROMPT_COMPARE_MANUALS = """
기존 메뉴얼과 신규 메뉴얼을 비교하여 차이점만 요약하세요.

규칙:
- 두 텍스트에 실제로 있는 차이점만 나열할 것
- 어느 것이 "더 좋다"는 판단을 하지 말 것
- 새로운 정보를 추가하지 말 것

기존 메뉴얼:
{old_manual}

신규 메뉴얼:
{new_manual}

응답 형식 (JSON):
{{
  "differences": [
    "차이점 1 설명",
    "차이점 2 설명"
  ],
  "recommendation": "merge|replace|keep_both 중 하나"
}}
"""


# Prompt for validating LLM output (prevent hallucination)
PROMPT_VALIDATE_OUTPUT = """
다음 LLM 출력이 원본 텍스트에 있는 내용만 사용했는지 검증하세요.

원본 텍스트:
{source_text}

LLM 출력:
{llm_output}

검증 규칙:
- LLM 출력의 모든 단어/문장이 원본에 있는지 확인
- 새로 생성된 정보가 있으면 "INVALID" 반환
- 원본 내용만 정리했으면 "VALID" 반환

응답 형식 (JSON):
{{
  "is_valid": true/false,
  "violations": ["위반 사항 1", "위반 사항 2"] or [],
  "reason": "검증 결과 설명"
}}
"""


def build_keyword_extraction_prompt(consultation_text: str) -> str:
    """
    Build prompt for keyword extraction

    Args:
        consultation_text: Full consultation text

    Returns:
        Formatted prompt
    """
    return PROMPT_EXTRACT_KEYWORDS.format(consultation_text=consultation_text)


def build_manual_draft_prompt(
    inquiry_text: str,
    action_taken: str,
    business_type: str | None = None,
    error_code: str | None = None,
) -> str:
    """
    Build prompt for manual draft generation

    Args:
        inquiry_text: Customer inquiry
        action_taken: Actions taken by support
        business_type: Business type (optional)
        error_code: Error code (optional)

    Returns:
        Formatted prompt
    """
    return PROMPT_GENERATE_MANUAL_DRAFT.format(
        inquiry_text=inquiry_text,
        action_taken=action_taken,
        business_type=business_type or "미지정",
        error_code=error_code or "미지정",
    )


def build_comparison_prompt(old_manual: str, new_manual: str) -> str:
    """
    Build prompt for comparing two manuals

    Args:
        old_manual: Existing manual text
        new_manual: New manual text

    Returns:
        Formatted prompt
    """
    return PROMPT_COMPARE_MANUALS.format(old_manual=old_manual, new_manual=new_manual)
