"""
Manual 비교 프롬프트 (FR-6/FR-7)

환각 방지 규칙을 System Prompt에서 명시한다.
"""

SYSTEM_PROMPT = """
당신은 두 개의 메뉴얼 텍스트를 비교해 차이점만 찾아주는 감사관입니다.

환각 금지 규칙:
- 입력에 없는 문장/규정/정책을 만들지 않는다.
- 추론형/가정형 문장을 만들지 않는다.
- 숫자, 날짜, 고유명사는 입력에 존재할 때만 사용한다.
- 차이점은 실제 텍스트 차이만 기술하고, 평가/판단을 하지 않는다.
"""

INSTRUCTION_TEMPLATE = """
아래 기존 메뉴얼과 신규 초안을 비교해 실제 텍스트 차이만 JSON으로 제공하세요.

출력 형식(JSON):
{
  "differences": ["차이점1", "차이점2"],
  "summary": "간단 요약"
}
"""

def build_manual_compare_prompt(*, old_manual: str, new_manual: str) -> str:
    return f"{INSTRUCTION_TEMPLATE}\n[기존]\n{old_manual}\n\n[신규]\n{new_manual}"
