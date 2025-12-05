"""
Manual Draft Prompt Templates (FR-2, FR-9)

System/Instruction/Context를 분리하여 환각 방지 규칙을 명시한다.
"""

SYSTEM_PROMPT = """
당신은 상담 내용을 정리해 메뉴얼 초안을 만드는 비서입니다.

환각 금지 규칙:
- 입력된 상담 텍스트 외 문장/정보를 생성하지 않는다.
- 모호한 추론형 문장, 규정/정책 문구를 만들지 않는다.
- 키워드는 반드시 원문에 존재하는 단어만 사용한다.
- 불확실하면 "정보 없음"으로 남긴다.
"""

INSTRUCTION_TEMPLATE = """
다음 상담 내용을 기반으로 핵심 키워드(1~3개), topic, background, guideline을 JSON으로 작성하세요.

출력 필수 규칙:
- keywords: 원문에 존재하는 단어만 사용 (1~3개)
- topic/background/guideline: 입력 문장을 재배열·요약만 하며 새 정보 추가 금지
- 명확하지 않은 부분은 "정보 없음"으로 표기
"""

CONTEXT_TEMPLATE = """
[문의내용]
{inquiry_text}

[조치내용]
{action_taken}

[업무구분]
{business_type}

[에러코드]
{error_code}
"""


def build_manual_draft_prompt(
    *,
    inquiry_text: str,
    action_taken: str,
    business_type: str | None,
    error_code: str | None,
) -> str:
    context = CONTEXT_TEMPLATE.format(
        inquiry_text=inquiry_text,
        action_taken=action_taken,
        business_type=business_type or "미지정",
        error_code=error_code or "미지정",
    )
    return f"{INSTRUCTION_TEMPLATE}\n{context}"
