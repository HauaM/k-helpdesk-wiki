# Unit Spec (v2.2): ManualStatus ARCHIVED 도입

## 1. 요구사항 요약

- **목적:** `ComparisonService`의 SIMILAR 경로에서 Draft를 "보관" 처리하기 위해 새로운 `ManualStatus.ARCHIVED` 값을 도입하고, 모든 DB/타입/서비스가 이를 인식하도록 마이그레이션한다.
- **유형:** ☑ 변경 / ☐ 신규 / ☐ 삭제
- **핵심 요구사항:**
  - 입력: `ManualEntry.status` 값이 `ManualStatus.DRAFT`인 상태에서 ComparisonService가 `similar` 판정을 내리는 흐름
  - 출력: `ManualEntry.status`가 `ManualStatus.ARCHIVED`로 바뀌고, DB enum 타입/스키마가 새로운 값도 허용함
  - 예외/제약: Postgres의 `manual_status` enum에는 `ARCHIVED`라는 값이 없으므로 migration을 통해 타입을 확장해야 하며, downgrade는 지원되지 않음을 문서로 남겨야 함
  - 처리흐름 요약: Draft 생성 → ComparisonService에서 `similar` 판단 → 해당 Draft를 `ARCHIVED`로 변경 → response 반환

---

## 2. 구현 대상 파일

| 구분 | 경로 | 설명 |
| ---- | ------------------------------------------- | ------------------------------- |
| 변경 | `app/models/manual.py` | `ManualStatus` enum에 `ARCHIVED` 추가 |
| 변경 | `alembic/versions/20251211_0003_manual_status_archived.py` | Postgres `manual_status` enum에 ARCHIVED를 추가하는 migration |
| 참조 | `app/services/manual_service.py` | SIMILAR 경로에서 `ManualStatus.ARCHIVED`를 사용할 수 있도록 이미 구현됨 |

---

## 3. 동작 플로우 (Mermaid)

```mermaid
flowchart TD
    A[ComparisonService 판정: SIMILAR] --> B[ManualEntry(status=DRAFT)]
    B --> C[ManualService = ManualStatus.ARCHIVED 설정]
    C --> D[DB (manual_status ENUM)에 ARCHIVED 허용]
    D --> E[Response에 기존 Manual 반환]
```

---

## 4. 테스트 계획

### 4.1 원칙
- **회귀 보호:** 기존 `tests/integration/test_create_draft_from_consultation.py`의 SIMILAR 경로가 실패하지 않도록 `ManualStatus.ARCHIVED`가 `ManualEntry`에 저장되는지 확인한다.
- **타입 완전성:** `migration` 후에도 기존 값을 사용하는 쿼리가 정상 동작해야 하므로, enum 값 추가 시 dependency 문제가 없도록 한다.

### 4.2 테스트 케이스

| TC ID | 계층 | 시나리오 | 목적 | 입력 | 기대결과 |
|-------|------|----------|------|------|---------|
| TC-ARCH-001 | Integration | SIMILAR 경로 | Draft가 ARCHIVED로 변경되는지 | `ManualService.create_draft_from_consultation` (similar) | API 호출 후 `manual_repo.update`가 ARCHIVED 상태로 저장됨 |
| TC-MIG-002 | DB | Migration 실행 | enum 타입에 ARCHIVED 추가 확인 | `uv run alembic upgrade head` | Postgres에서 `manual_status`에 ARCHIVED 존재, 이전 값 유지 |

---

## 5. 작업 우선순위

1. `ManualStatus` enum에 `ARCHIVED` 추가 (모델 + 타입 정의)
2. 신규 Alembic migration(20251211_0003) 작성: Postgres의 `manual_status` enum에 ARCHIVED 값 추가, downgrade는 NotImplemented로 명시
3. (검증) 유닛/통합 테스트 및 `alembic upgrade` 시나리오에서 실패 없는지 확인

**참고:** 기존 `ComparisonService`와 `ManualService.create_draft_from_consultation`은 이미 `ManualStatus.ARCHIVED`를 사용하고 있으므로, 엔드 투 엔드 흐름의 유지를 위해 위 작업이 반드시 필요합니다.
