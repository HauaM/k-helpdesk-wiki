# Manual Review Task Reviewer 변경 작업 계획

## 1. 대상 테이블
- `manual_review_tasks.reviewer_id` (현재 UUID)
- `task_history.changed_by` (현재 UUID)

### 스키마/서비스/리포지토리 전역 전환 원칙
- UUID → 문자열(`employee_id`)로 통일. FastAPI/Pydantic/서비스/리포지토리/MCP 모두 동일하게 맞춘다.
- `ManualApproveRequest.approver_id`는 이름은 그대로 두고 **타입만 문자열**로 전환한다.
- 코드 곳곳의 `str(reviewer_id)` 캐스팅 제거.

## 2. 연결 프로세스 영향도
1. **API/스키마**: `ManualReviewTask` 관련 Pydantic 모델(`ManualReviewTaskResponse`, `ManualReviewApproval`, `ManualReviewRejection`)과 FastAPI 라우터(`app/routers/tasks.py`)가 UUID를 기준으로 동작. 변경 시 DTO 입력/출력 타입을 문자열(`employee_id`)로 일치시켜야 함.
2. **서비스/비즈니스 로직**: `TaskService.approve_task`/`reject_task`는 현재 `reviewer_id`를 UUID로 받아 `ManualApproveRequest`, `TaskHistory`, `ManualReviewTask`에 그대로 저장. 문자열로 바꾸고 `users.employee_id`와 매핑하는 절차로 수정 필요.
3. **리포지토리/쿼리**: `TaskRepository` 및 `ManualReviewTaskRepository` 필터 조건(`reviewer_id`)과 검색 로직이 UUID 타입을 기대함. 문자열 비교로 바꾸고, 조건문 내 UUID 전환을 제거.
4. **MCP/테스트/문서**: MCP 도구(`app/mcp/tools.py`), `onboarding.md`, Swagger 정의 등에서 `reviewer_id`를 UUID로 보내도록 되어 있으므로 `employee_id` 문자열로 변경.
5. **데이터 마이그레이션**: 기존 UUID 값을 어떤 `employee_id`로 매핑할지 자료가 없다면 신규 필드(`reviewer_employee_id`)를 추가하고 점진적으로 채울 수도 있음. 작업 완료 후 기존 UUID 값은 더 이상 사용되지 않도록 정리.
6. **API 경로 확인**: 표준 경로를 코드 기준 `/api/v1/manual-review/tasks`로 확정. README/Swagger/onboarding를 모두 이 경로로 통일.

## 3. 작업 흐름
1. 모델·스키마 수정
   - `ManualReviewTask.reviewer_id`, `TaskHistory.changed_by` 타입을 `str | None`으로 변경하고 필요한 제약(FK/length) 추가.
   - Pydantic 모델에서 `reviewer_id` 필드를 문자열로 정의.
   - `ManualApproveRequest.approver_id`를 문자열로 변경하고 필드명을 `employee_id`로 통일하는 방안 포함.
2. API/서비스 수정
   - `ManualReviewApproval`/`Rejection` 입력에서 `reviewer_id` 대신 `employee_id`를 받도록 하고 `TaskService`의 승인/반려 로직에서 문자열로 처리.
   - 승인 시 `ManualService.approve_manual`에 전달하는 `approver_id`는 이름을 유지하되 타입을 문자열로 맞추고 `str()` 캐스팅 제거.
3. 리포지토리·쿼리 업데이트
   - `TaskRepository`/`ManualReviewTaskRepository`에서 `reviewer_id` 필터 타입을 문자열로 바꾸고 조건문 업데이트.
   - 필요 시 문자열 인덱스나 `users.employee_id` FK 조건 추가.
4. Alembic 마이그레이션
   - `reviewer_id`/`changed_by` 컬럼의 타입을 `UUID`에서 `String(50)`으로 변경(또는 신규 컬럼 추가 후 데이터 복사)하고 인덱스 추가.
   - `users.employee_id` FK 제약을 추가해 무결성 확보(선행: `users.employee_id` 유니크 보장 확인).
   - 기존 데이터는 삭제 후 재적재 예정이므로 UUID→employee_id 매핑 스크립트는 생략. 필요 시 NULL 허용 상태로 초기화 가능.
   - 다운그레이드 시 타입을 다시 UUID로 돌리거나 FK 제거 로직 포함.
5. 클라이언트/문서 정비
   - MCP 툴/Swagger/README/onboarding 등에서 `reviewer_id` 사용 예시를 모두 `employee_id`로 업데이트(예: `app/mcp/server.py` JSON Schema, `onboarding.md`, `onboarding_tmp.html`).
   - 테스트와 Postman/스크립트도 `employee_id` 사용으로 조정.
   - API 경로를 결정한 뒤 README/Swagger/onboarding의 경로도 일괄 수정.
6. 검증
   - `uv run pytest` 등 테스트 실행.
   - `POST /manual-review/tasks/{id}/approve`를 `employee_id`로 호출해 상태가 `DONE`으로 변하는지 확인.
   - `SELECT` 쿼리로 `manual_review_tasks`, `task_history`의 `employee_id` 값이 올바르게 저장됐는지 확인.
   - 필요 시 문자열 ID에 대한 길이/형식 검증 추가 테스트.

## 4. 테스트/품질 보강
- Task 승인/반려가 문자열 ID로 저장·반환되는지 확인하는 단위 테스트 및 라우터 테스트 추가.
- API 경로가 문서와 일치하는지, 스웨거 스펙이 employee_id를 요구하는지 검증.
- Alembic 마이그레이션 업/다운 시 스키마가 기대대로 변경되는지 확인하는 마이그레이션 테스트(옵션).

## 5. 구현 우선순위 안내 (기존 TODO와 연동)
- `ConsultationService.register_consultation`/`search_similar_consultations`가 NotImplemented이며 MCP 도구(`app/mcp/tools.py`)도 placeholder 상태. reviewer_id→employee_id 전환 이후, 상담/메뉴얼 서비스 구현과 MCP 연동을 우선순위에 넣어 다음 작업자가 바로 착수할 수 있도록 한다.

## 6. 환경/배포 유의사항
- 로컬에서는 `uv sync --all-groups` 후 `.env` 구성, `uv run alembic upgrade head`로 스키마를 최신화한다. `app/api/main.py`의 `init_db()`는 기본 주석 처리 상태이므로 Alembic 기반 초기화를 명시한다.

## 4. 참고
- `users.employee_id`가 유일하다는 전제를 유지하면서 `manual_review_tasks.reviewer_id`를 같은 문자열로 사용하면 외부 인증 정보와 연동이 쉬운 반면, 추후 UUID 기반 시스템과 통합하려면 별도 UUID 컬럼을 유지하거나 매핑 테이블을 두는 방향도 고려할 수 있음.
- 이 계획서는 Codex에게도 그대로 전달할 수 있는 형태이며, 이후 구현 단계에서 필요한 추가 정보(예: UUID→employee_id 매핑 정책, 테스트 케이스 등)를 함께 제공하면 작업 흐름이 매끄럽게 이어집니다.
