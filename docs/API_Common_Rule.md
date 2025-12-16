# API 규약
## 성공 예시
{
  "success": true,
  "data": { },
  "error": null,
  "meta": {
    "requestId": "1c0c...f",
    "timestamp": "2025-12-16T16:00:00+09:00"
  },
  "feedback": [
    {
      "code": "PROFILE_INCOMPLETE",
      "level": "info",
      "message": "프로필 사진을 등록하면 더 좋아요."
    }
  ]
}

## 실패 예시
{
  "success": false,
  "data": null,
  "error": {
    "code": "AUTH.INVALID_TOKEN",
    "message": "유효하지 않은 토큰입니다.",
    "details": { "reason": "expired" },
    "hint": "다시 로그인해 주세요."
  },
  "meta": {
    "requestId": "1c0c...f",
    "timestamp": "2025-12-16T16:00:00+09:00"
  },
  "feedback": []
}
