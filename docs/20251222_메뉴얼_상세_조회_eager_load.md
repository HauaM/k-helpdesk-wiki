# Unit Spec

## 1. 요구사항 요약

- **목적:** 메뉴얼 상세 조회 시 `source_consultation` 관계를 eager load하여 `MissingGreenlet` 오류를 방지
- **유형:** ☑ 변경
- **핵심 요구사항:**
  - 입력: `manual_id` (UUID)
  - 출력: 기존과 동일한 `ManualEntryResponse`
  - 예외/제약: 기존 에러 처리 흐름 유지
  - 처리흐름 요약: 상세 조회 시 `ManualEntry`와 `source_consultation`을 함께 로딩

---

## 2. 구현 대상 파일

| 구분 | 경로                              | 설명                                |
| ---- | --------------------------------- | ----------------------------------- |
| 변경 | app/repositories/manual_rdb.py    | `source_consultation` eager load 추가 |
| 변경 | app/routers/manuals.py            | 상세 조회에 eager-load 메서드 사용 |

---

## 3. 동작 플로우 (Mermaid)

```mermaid
flowchart TD
    A[Client] -->|GET /manuals/{id}| B(API Router)
    B --> C[Repository: get_by_id_with_consultation]
    C --> D[DB: ManualEntry + source_consultation]
    D --> E[Router: 권한 체크]
    E --> F[Response]
```

---

## 4. 테스트 계획

### 4.1 원칙

- **테스트 우선(TDD)**: 본 섹션의 항목을 우선 구현하고 코드 작성.
- **계층별 커버리지**: Unit → Integration → API(E2E-lite) 순서로 최소 P0 커버.
- **독립성/재현성**: 외부 연동(LLM/DB/File I/O)은 모킹 또는 임베디드 스토리지 사용.
- **판정 기준**: 기대 상태코드/스키마/부작용(저장/로그)을 명시적으로 검증.

### 4.2 구현 예상 테스트 항목(각 항목의 목적 포함)

| TC ID       | 계층 | 시나리오              | 목적(무엇을 검증?)                   | 입력/사전조건                    | 기대결과                                   |
| ----------- | ---- | --------------------- | ------------------------------------ | -------------------------------- | ------------------------------------------ |
| TC-API-001  | API  | 정상 조회             | eager load 적용 후 500 미발생        | `GET /manuals/{id}`              | `200`, 응답 스키마 일치                    |
| TC-API-002  | API  | 권한 없음(초안)       | 초안 권한 검증 유지                  | 초안 + 다른 직원                 | `403`                                      |

---

## 5. 사용자 요청 기록

### 원본 요청 (1차)
```
아래와 같은 오류가 발생하는대 원인과 해결방법을 알려줘.
해당 오류는 작성된 메뉴얼 초안을 가져오는 API 중 발생하는 것 같아.
> 모든 대답은 한글로

[오류 내역 ] :
INFO:     127.0.0.1:48510 - "GET /api/v1/manuals/0f66ba3d-7431-434b-aedf-50eb6853975e HTTP/1.1" 500 Internal Server Error
ERROR:    Exception in ASGI application
Traceback (most recent call last):
  ...
sqlalchemy.exc.MissingGreenlet: greenlet_spawn has not been called; can't call await_only() here. Was IO attempted in an unexpected place? (Background on this error at: https://sqlalche.me/e/20/xd2s)
```

### 사용자 명확화 (2차+)
```
eager load 하도록 조회 쿼리 수정 해줘.
```

### 최종 확정 (체크리스트)
- ✅ 메뉴얼 상세 조회에서 eager load 적용
- ✅ 기존 응답/에러 흐름 유지
