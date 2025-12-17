"""
FastAPI Swagger 문서화를 위한 공통 응답 구조 정의

각 엔드포인트의 @router 데코레이터에서 사용하여
Swagger UI에 공통 응답 envelope 구조를 표시합니다.
"""

from typing import Any, Dict


def success_response_example(
    status_code: int = 200,
    data_example: Any = None,
) -> Dict[int, Dict[str, Any]]:
    """
    성공 응답 예시 생성

    Args:
        status_code: HTTP 상태 코드 (200, 201, 204 등)
        data_example: 응답 data 필드의 예시 값

    Returns:
        FastAPI responses 매개변수에 전달할 딕셔너리
    """
    if status_code == 204:
        # No Content
        return {}

    return {
        status_code: {
            "description": {
                200: "성공",
                201: "생성 성공",
                202: "처리 중",
            }.get(status_code, "성공"),
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "data": data_example or {},
                        "error": None,
                        "meta": {
                            "requestId": "req-uuid-xxx",
                            "timestamp": "2024-12-16T10:35:00Z",
                        },
                        "feedback": [],
                    }
                }
            },
        }
    }


def error_response_examples() -> Dict[int, Dict[str, Any]]:
    """
    공통 에러 응답 예시들

    Returns:
        FastAPI responses 매개변수에 전달할 딕셔너리
    """
    return {
        400: {
            "description": "Bad Request - 유효하지 않은 입력",
            "content": {
                "application/json": {
                    "example": {
                        "success": False,
                        "data": None,
                        "error": {
                            "code": "ValidationError",
                            "message": "입력값이 유효하지 않습니다",
                            "details": {"field": "error message"},
                            "hint": "필드를 확인해주세요",
                        },
                        "meta": {
                            "requestId": "req-uuid-xxx",
                            "timestamp": "2024-12-16T10:35:00Z",
                        },
                        "feedback": [],
                    }
                }
            },
        },
        404: {
            "description": "Not Found - 리소스를 찾을 수 없음",
            "content": {
                "application/json": {
                    "example": {
                        "success": False,
                        "data": None,
                        "error": {
                            "code": "RecordNotFoundError",
                            "message": "요청한 리소스를 찾을 수 없습니다",
                            "details": None,
                            "hint": None,
                        },
                        "meta": {
                            "requestId": "req-uuid-xxx",
                            "timestamp": "2024-12-16T10:35:00Z",
                        },
                        "feedback": [],
                    }
                }
            },
        },
        409: {
            "description": "Conflict - 상태 충돌",
            "content": {
                "application/json": {
                    "example": {
                        "success": False,
                        "data": None,
                        "error": {
                            "code": "NeedsReReviewError",
                            "message": "재검토가 필요합니다",
                            "details": None,
                            "hint": "다시 검토해주세요",
                        },
                        "meta": {
                            "requestId": "req-uuid-xxx",
                            "timestamp": "2024-12-16T10:35:00Z",
                        },
                        "feedback": [],
                    }
                }
            },
        },
        422: {
            "description": "Unprocessable Entity - 필드 검증 실패",
            "content": {
                "application/json": {
                    "example": {
                        "success": False,
                        "data": None,
                        "error": {
                            "code": "ValidationError",
                            "message": "필드 검증에 실패했습니다",
                            "details": {
                                "inquiry_text": ["최소 10자 이상이어야 합니다"]
                            },
                            "hint": None,
                        },
                        "meta": {
                            "requestId": "req-uuid-xxx",
                            "timestamp": "2024-12-16T10:35:00Z",
                        },
                        "feedback": [],
                    }
                }
            },
        },
        500: {
            "description": "Internal Server Error - 서버 오류",
            "content": {
                "application/json": {
                    "example": {
                        "success": False,
                        "data": None,
                        "error": {
                            "code": "INTERNAL.UNEXPECTED",
                            "message": "예기치 않은 서버 오류가 발생했습니다",
                            "details": None,
                            "hint": "관리자에게 문의해주세요",
                        },
                        "meta": {
                            "requestId": "req-uuid-xxx",
                            "timestamp": "2024-12-16T10:35:00Z",
                        },
                        "feedback": [],
                    }
                }
            },
        },
    }


def combined_responses(
    status_code: int = 200,
    data_example: Any = None,
    include_errors: list[int] | None = None,
) -> Dict[int, Dict[str, Any]]:
    """
    성공 응답과 에러 응답을 함께 정의

    Args:
        status_code: 성공 HTTP 상태 코드
        data_example: 응답 data 필드의 예시 값
        include_errors: 포함할 에러 상태 코드 리스트 (기본값: [400, 404, 500])

    Returns:
        FastAPI responses 매개변수에 전달할 딕셔너리
    """
    if include_errors is None:
        include_errors = [400, 404, 500]

    responses = success_response_example(status_code, data_example)
    error_examples = error_response_examples()

    for error_code in include_errors:
        if error_code in error_examples:
            responses[error_code] = error_examples[error_code]

    return responses
