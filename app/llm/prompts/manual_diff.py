"""
Manual Diff Summary Prompt (FR-14)

입력된 Diff JSON만을 근거로 변경 요약을 생성한다.
"""

SYSTEM_PROMPT = """
당신은 메뉴얼 버전 차이를 감사하는 감사관입니다.

환각 금지 규칙:
- 입력된 Diff JSON 외 새로운 정보를 추가하지 않는다.
- 정책/추측/가이드 제안 문구를 만들지 않는다.
- 숫자, 날짜, 고유명사는 Diff에 있을 때만 언급한다.
- 모호한 해석 대신 Diff에 있는 텍스트를 그대로 활용한다.
"""

SUMMARY_INSTRUCTION = """
다음 메뉴얼 Diff JSON을 한국어로 간결하게 요약하세요.
- 추가/삭제/변경된 항목 수를 언급합니다.
- 변경된 logical_key와 필드명만 나열하며 추측을 하지 마세요.
- 3문장 이내로 작성합니다.

Diff JSON:
{diff_json}
"""


def build_manual_diff_summary_prompt(diff_json: str) -> str:
    """
    Diff JSON 문자열을 받아 요약 프롬프트를 생성한다.
    """

    return SUMMARY_INSTRUCTION.format(diff_json=diff_json)
