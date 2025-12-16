{
  "summary": "테스트거래 - 인터넷뱅킹 로그인 시 공인인증서가 목록에 나타나지 않습니다. USB에 인증서를 저장해두었습니다.",
  "inquiry_text": "인터넷뱅킹 로그인 시 공인인증서가 목록에 나타나지 않습니다. USB에 인증서를 저장해두었습니다.",
  "action_taken": "인증서가 USB에 저장되어 있으나, OS 권한 설정으로 인해 브라우저에서 접근 불가한 상태임을 확인. 관리자 권한으로 브라우저 재실행 후 인증서 위치 재설정하여 정상 로그인 처리.",
  "branch_code": "IT 기획부",
  "employee_id": "21P0031",
  "screen_id": "SCR001",
  "transaction_name": "테스트거래",
  "business_type": "TEST",
  "error_code": "NOTHING",
  "metadata_fields": {
    "additionalProp1": {}
  }
}

## draft entry response examples

#### comparison_type: similar
```json
{
  "success": true,
  "data": {
    "created_at": "2025-12-16T08:33:22.579184Z",
    "updated_at": "2025-12-16T08:32:42.599478Z",
    "id": "1260b9cd-f743-4211-8f8a-44800b75864c",
    "comparison_type": "similar",
    "draft_entry": {
      "created_at": "2025-12-16T08:33:22.579184Z",
      "updated_at": "2025-12-16T08:32:42.599478Z",
      "id": "1260b9cd-f743-4211-8f8a-44800b75864c",
      "keywords": [
        "공인인증서",
        "USB 저장소",
        "인증서"
      ],
      "topic": "인터넷뱅킹 로그인 시 공인인증서가 목록에 보이지 않음",
      "background": "인증서 경로가 기본 위치가 아닌 USB 저장소에 있어 인식 안 된 것으로 확인",
      "guideline": "인증서 위치 재설정 후 정상 로그인 확인",
      "business_type": "TEST",
      "error_code": "NOTHING",
      "source_consultation_id": "4201e354-7f06-4412-9efe-1228c334cb10",
      "version_id": null,
      "status": "ARCHIVED",
      "business_type_name": "테스트"
    },
    "existing_manual": {
      "created_at": "2025-12-16T08:22:47.411510Z",
      "updated_at": "2025-12-16T08:25:23.606760Z",
      "id": "32ec2914-4bbb-4615-8521-de212f3e6546",
      "keywords": [
        "공인인증서",
        "USB 저장소",
        "인증서"
      ],
      "topic": "인터넷뱅킹 로그인 시 공인인증서가 목록에 보이지 않음",
      "background": "인증서 경로가 기본 위치가 아닌 USB 저장소에 있어 인식 안 된 것으로 확인",
      "guideline": "인증서 위치 재설정 후 정상 로그인 확인",
      "business_type": "TEST",
      "error_code": "NOTHING",
      "source_consultation_id": "4201e354-7f06-4412-9efe-1228c334cb10",
      "version_id": "0aa25164-4350-4ba2-84bc-c0c1b52dcac3",
      "status": "APPROVED",
      "business_type_name": "테스트"
    },
    "review_task_id": null,
    "similarity_score": 1,
    "comparison_version": "kw2_bonus10",
    "message": "기존 메뉴얼(버전 0aa25164-4350-4ba2-84bc-c0c1b52dcac3)과 100% 유사합니다. 기존 메뉴얼을 참고하세요."
  },
  "error": null,
  "meta": {
    "requestId": "8f948c98-4680-4a3e-9bbf-014432479772",
    "timestamp": "2025-12-16T08:33:22.693246Z"
  },
  "feedback": []
}
```

#### comparison_type: supplement
상담아이디 
--4201e354-7f06-4412-9efe-1228c334cb10 원본
--6eddf8bf-7e4d-4405-8eaa-700d30086139 수정본 

```json 
{
  "success": true,
  "data": {
    "created_at": "2025-12-16T08:59:26.164363Z",
    "updated_at": "2025-12-16T08:59:26.164363Z",
    "id": "2173dbd3-3696-434d-b096-d2a2572a95ea",
    "comparison_type": "supplement",
    "draft_entry": {
      "created_at": "2025-12-16T08:59:26.164363Z",
      "updated_at": "2025-12-16T08:59:26.164363Z",
      "id": "2173dbd3-3696-434d-b096-d2a2572a95ea",
      "keywords": [
        "공인인증서",
        "USB",
        "브라우저"
      ],
      "topic": "인터넷뱅킹 로그인 시 공인인증서가 목록에 나타나지 않음",
      "background": "인증서가 USB에 저장되어 있으나 OS 권한 설정으로 브라우저에서 접근 불가",
      "guideline": "관리자 권한으로 브라우저 재실행 후 인증서 위치 재설정하여 정상 로그인 처리",
      "business_type": "TEST",
      "error_code": "NOTHING",
      "source_consultation_id": "6eddf8bf-7e4d-4405-8eaa-700d30086139",
      "version_id": null,
      "status": "DRAFT",
      "business_type_name": "테스트"
    },
    "existing_manual": {
      "created_at": "2025-12-16T08:22:47.411510Z",
      "updated_at": "2025-12-16T08:25:23.606760Z",
      "id": "32ec2914-4bbb-4615-8521-de212f3e6546",
      "keywords": [
        "공인인증서",
        "USB 저장소",
        "인증서"
      ],
      "topic": "인터넷뱅킹 로그인 시 공인인증서가 목록에 보이지 않음",
      "background": "인증서 경로가 기본 위치가 아닌 USB 저장소에 있어 인식 안 된 것으로 확인",
      "guideline": "인증서 위치 재설정 후 정상 로그인 확인",
      "business_type": "TEST",
      "error_code": "NOTHING",
      "source_consultation_id": "4201e354-7f06-4412-9efe-1228c334cb10",
      "version_id": "0aa25164-4350-4ba2-84bc-c0c1b52dcac3",
      "status": "APPROVED",
      "business_type_name": "테스트"
    },
    "review_task_id": "e151a552-7fb5-435d-adbd-6cd76577ede8",
    "similarity_score": 0.7224746041573049,
    "comparison_version": "kw2_bonus10",
    "message": "기존 메뉴얼(버전 0aa25164-4350-4ba2-84bc-c0c1b52dcac3)의 내용을 보충했습니다. 검토자가 확인 후 승인합니다."
  },
  "error": null,
  "meta": {
    "requestId": "f270dd1a-2b38-413c-b97e-d8186c56484c",
    "timestamp": "2025-12-16T09:00:13.858163Z"
  },
  "feedback": []
}
```

### 
```json
{
  "success": true,
  "data": {
    "created_at": "2025-12-16T09:22:44.251894Z",
    "updated_at": "2025-12-16T09:22:44.251894Z",
    "id": "6ab65589-c897-497a-b236-b67e762cc2c8",
    "comparison_type": "new",
    "draft_entry": {
      "created_at": "2025-12-16T09:22:44.251894Z",
      "updated_at": "2025-12-16T09:22:44.251894Z",
      "id": "6ab65589-c897-497a-b236-b67e762cc2c8",
      "keywords": [
        "앱 알림",
        "권한",
        "테스트"
      ],
      "topic": "앱 알림이 최근 3일간 오지 않음",
      "background": "앱 알림권한 OFF 상태 확인",
      "guideline": "권한 재활성화 후 테스트 알림 정상 수신 확인",
      "business_type": "TEST",
      "error_code": "NOTHING",
      "source_consultation_id": "ec748b7f-bdfb-488a-b9c4-02e5b39769c0",
      "version_id": null,
      "status": "DRAFT",
      "business_type_name": "테스트"
    },
    "existing_manual": null,
    "review_task_id": "019ae94e-fa63-4f93-90f0-5e3674f739dc",
    "similarity_score": null,
    "comparison_version": "kw2_bonus10",
    "message": "신규 메뉴얼 초안으로 생성되었습니다."
  },
  "error": null,
  "meta": {
    "requestId": "f388d87c-a5ab-46e2-9b90-83c6740cbd8a",
    "timestamp": "2025-12-16T09:22:44.281704Z"
  },
  "feedback": []
}
```