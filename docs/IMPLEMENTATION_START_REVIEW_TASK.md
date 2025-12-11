# 검토 태스크 시작 API 구현 완료 (FR-6)

**작성일**: 2024-12-11
**상태**: ✅ 완료
**참조**: MANUAL_WORKFLOW_AND_VERSIONING.md

---

## 📋 요구사항

### 목표
메뉴얼 검토자에게 검토를 올리기 전에 TODO 상태의 초안이 그대로 노출되는 문제를 방지하기 위해,
검토 시작 시점에 명시적 상태 변경(TODO → IN_PROGRESS)을 수행하는 API 추가.

### API 명세
```
PUT /api/v1/manual-review/tasks/{task_id}
```

### 플로우
```
초안 상태 (TODO)
    ↓
PUT /api/v1/manual-review/tasks/{task_id} 호출
    ↓
상태 변경 (IN_PROGRESS)
```

---

## 🔧 구현 내용

### 1. TaskService에 start_task 메소드 추가

**파일**: [app/services/task_service.py:118-145](../app/services/task_service.py#L118-L145)

```python
async def start_task(
    self,
    task_id: UUID,
) -> ManualReviewTaskResponse:
    """검토 태스크 시작 (TODO → IN_PROGRESS)

    검토자가 태스크 검토를 시작할 때 상태를 IN_PROGRESS로 변경합니다.
    이를 통해 미완성 초안 노출을 방지합니다.
    """
    task = await self.task_repo.get_by_id(task_id)
    if task is None:
        raise RecordNotFoundError(f"ManualReviewTask(id={task_id}) not found")

    await self._add_history(task, TaskStatus.IN_PROGRESS)

    task.status = TaskStatus.IN_PROGRESS
    await self.task_repo.update(task)

    return await self._to_response(task)
```

**주요 기능**:
- ✅ TODO 상태의 태스크를 IN_PROGRESS로 변경
- ✅ 상태 변경 이력(TaskHistory) 자동 기록
- ✅ 업데이트된 ManualReviewTaskResponse 반환
- ✅ 예외 처리: 태스크 미존재 시 RecordNotFoundError 발생

---

### 2. 라우터에 PUT 엔드포인트 추가

**파일**: [app/routers/tasks.py:111-134](../app/routers/tasks.py#L111-L134)

```python
@router.put(
    "/tasks/{task_id}",
    response_model=ManualReviewTaskResponse,
    summary="Start manual review task",
)
async def start_review_task(
    task_id: UUID,
    service: TaskService = Depends(get_task_service),
) -> ManualReviewTaskResponse:
    """FR-6: 검토 태스크 시작 (TODO → IN_PROGRESS)

    검토자가 검토를 시작할 때 태스크 상태를 IN_PROGRESS로 변경합니다.
    이를 통해 미완성 초안이 노출되는 것을 방지합니다.
    """
    return await service.start_task(task_id)
```

**엔드포인트 특성**:
- ✅ HTTP 메소드: PUT (상태 변경)
- ✅ 경로: `/api/v1/manual-review/tasks/{task_id}`
- ✅ 요청 본문: 없음 (task_id만 필요)
- ✅ 응답: ManualReviewTaskResponse (200 OK)
- ✅ 에러: 404 Not Found (태스크 없을 때)

---

## 📊 상태 전이 다이어그램

```
생성
  ↓
TODO (신규 리뷰 태스크)
  ↓
PUT /tasks/{task_id} 호출
  ↓
IN_PROGRESS (검토 중)
  ↓
┌─────────────────────────┐
│  검토자 의사결정         │
├─────────────────────────┤
│ POST /tasks/{id}/approve│  → DONE (승인)
│ POST /tasks/{id}/reject │  → REJECTED (반려)
└─────────────────────────┘
  ↓
처리 완료
```

---

## 🧪 테스트

**파일**: [tests/unit/test_manual_review_submission.py](../tests/unit/test_manual_review_submission.py)

### 테스트 케이스
1. ✅ `test_start_task_success`: 정상 상태 변경
2. ✅ `test_start_task_not_found`: 태스크 미존재 예외 처리
3. ✅ `test_start_task_records_history`: 상태 변경 이력 기록 확인
4. ✅ `test_start_task_changes_status`: 상태 변경 확인

### 테스트 실행 결과
```bash
$ uv run pytest tests/unit/test_manual_review_submission.py -v

tests/unit/test_manual_review_submission.py::TestStartReviewTask::test_start_task_success PASSED
tests/unit/test_manual_review_submission.py::TestStartReviewTask::test_start_task_not_found PASSED
tests/unit/test_manual_review_submission.py::TestStartReviewTask::test_start_task_records_history PASSED
tests/unit/test_manual_review_submission.py::TestStartReviewTask::test_start_task_changes_status PASSED

====== 4 passed in 0.76s ======
```

---

## 📈 워크플로우 시퀀스

```
검토자                        API Server            Repository              DB
  │                             │                         │                   │
  │─PUT /tasks/{task_id}───────→│                         │                   │
  │                             │                         │                   │
  │                             │──get_by_id(task_id)────→│                   │
  │                             │←───task (status=TODO)───│                   │
  │                             │                         │                   │
  │                             │──────add_history────────→│─COMMIT (TODO→IN_PROGRESS)─→│
  │                             │                         │                   │
  │                             │──update(task)──────────→│─UPDATE status───→│
  │                             │                         │                   │
  │                             │←───ManualReviewTaskResponse──────────────────│
  │←────200 OK────────────────│
  │  {status: IN_PROGRESS}     │
```

---

## 🔄 기존 기능과의 통합

### 리뷰 태스크 생성 후 플로우
```
1. POST /manuals/draft/{manual_id}/conflict-check
   → ManualReviewTask 생성 (status=TODO)

2. PUT /manual-review/tasks/{task_id}
   → 상태 변경 (TODO → IN_PROGRESS)

3. POST /manual-review/tasks/{task_id}/approve
   → 승인 (IN_PROGRESS → DONE)

또는

3. POST /manual-review/tasks/{task_id}/reject
   → 반려 (IN_PROGRESS → REJECTED)
```

---

## 💾 데이터 변경사항

### TaskHistory 기록
- **from_status**: TODO
- **to_status**: IN_PROGRESS
- **changed_by**: NULL (사용자 정보 없을 때)
- **reason**: NULL (기본값)

### ManualReviewTask 변경
- **status**: TODO → IN_PROGRESS
- **updated_at**: 현재 시간으로 자동 갱신
- **reviewer_id**: 변경 없음 (검토 시작 시에는 아직 할당 안 함)

---

## ✨ 주요 개선사항

### 1. 미완성 초안 노출 방지
- 검토 시작 시점에 명시적 상태 변경으로 초안 상태를 추적 가능

### 2. 워크플로우 명확화
- TODO → IN_PROGRESS → DONE/REJECTED 순차적 흐름
- 각 단계에서의 책임 명확화

### 3. 감사(Audit) 추적
- TaskHistory에 모든 상태 변경 기록
- 검토 프로세스 투명성 증대

### 4. 사용자 경험 개선
- 검토자가 검토 시작 시점을 명확하게 마킹
- 시스템에서 검토 중인 태스크 상태를 정확하게 추적

---

## 📝 API 문서

### 요청
```http
PUT /api/v1/manual-review/tasks/{task_id}
```

**경로 매개변수**:
- `task_id` (UUID): 검토 태스크 ID

**요청 본문**: 없음

### 응답 (200 OK)
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "created_at": "2024-12-10T10:00:00Z",
  "updated_at": "2024-12-10T10:05:00Z",
  "old_entry_id": "550e8400-e29b-41d4-a716-446655440001",
  "new_entry_id": "550e8400-e29b-41d4-a716-446655440002",
  "similarity": 0.92,
  "status": "IN_PROGRESS",
  "reviewer_id": null,
  "review_notes": null,
  "old_manual_summary": "기존 메뉴얼 요약...",
  "new_manual_summary": "신규 초안 요약...",
  "business_type": "인터넷뱅킹",
  "business_type_name": "인터넷뱅킹",
  "new_error_code": "ERR_LOGIN_001",
  "new_manual_topic": "인터넷뱅킹 로그인 오류 해결"
}
```

### 에러 응답 (404 Not Found)
```json
{
  "detail": "ManualReviewTask(id=550e8400-e29b-41d4-a716-446655440000) not found"
}
```

---

## 🚀 배포 후 주의사항

### 1. 기존 TODO 태스크 마이그레이션
- 기존에 TODO 상태로 있던 태스크들은 수동으로 검토하고 상태 업데이트 필요
- 또는 배치 작업으로 일괄 IN_PROGRESS로 변경 가능

### 2. UI/클라이언트 수정
- 리뷰어 UI에 "검토 시작" 버튼 추가
- 해당 버튼이 PUT 엔드포인트 호출하도록 수정

### 3. 모니터링
- TaskHistory 테이블에 TODO→IN_PROGRESS 전환 기록 모니터링
- 장시간 IN_PROGRESS 상태로 남아있는 태스크 추적

---

## 📚 참조 문서

- [MANUAL_WORKFLOW_AND_VERSIONING.md](./MANUAL_WORKFLOW_AND_VERSIONING.md): 메뉴얼 워크플로우 전체 흐름
- [app/models/task.py](../app/models/task.py): TaskStatus, ManualReviewTask 모델
- [app/services/task_service.py](../app/services/task_service.py): TaskService 구현
- [app/routers/tasks.py](../app/routers/tasks.py): 라우터 정의
