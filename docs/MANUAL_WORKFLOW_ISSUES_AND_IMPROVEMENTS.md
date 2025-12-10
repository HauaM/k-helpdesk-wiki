# 메뉴얼 워크플로우 - 문제점 및 개선사항 (개발 대기)

## 📋 문서 목적

이 문서는 **MANUAL_WORKFLOW_AND_VERSIONING.md** 문서 작성 과정에서 발견된:
- ❌ 실제 구현과 문서의 불일치
- ⚠️ 불명확하거나 누락된 기능
- 🔧 개선이 필요한 부분

이들을 정리하여 **향후 개발 시 참고할 수 있도록** 작성되었습니다.

---

## 🔴 P0 (즉시 개선 필요)

### 1️⃣ IN_PROGRESS 상태 사용되지 않음 (중대)

**문제:**
- 문서의 상태 다이어그램: `"TODO → IN_PROGRESS → DONE/REJECTED"`
- 실제 구현: `"TODO → DONE/REJECTED"` (IN_PROGRESS 스킵)

**증거:**

```python
# app/services/task_service.py:71-98
async def approve_task(self, task_id: UUID, payload: ManualReviewApproval):
    task = await self.task_repo.get_by_id(task_id)

    await self._add_history(
        task,
        TaskStatus.DONE,  # ← 직접 DONE으로 변경
        changed_by=payload.employee_id,
    )

    task.status = TaskStatus.DONE  # IN_PROGRESS를 거치지 않음
    await self.task_repo.update(task)
```

**원인:**
- `TaskStatus.IN_PROGRESS`는 [app/models/task.py:24](../app/models/task.py#L24)에 정의만 되어있음
- 실제 워크플로우에서는 사용되지 않음

**개선 방안:**

**옵션 A: IN_PROGRESS 제거** (권장)
```python
class TaskStatus(str, enum.Enum):
    TODO = "TODO"
    DONE = "DONE"
    REJECTED = "REJECTED"
    # IN_PROGRESS 제거
```

**옵션 B: IN_PROGRESS 활성화** (미래를 위해)
```python
# 검토 시작 시 IN_PROGRESS로 변경
async def start_review_task(self, task_id: UUID):
    task = await self.task_repo.get_by_id(task_id)
    task.status = TaskStatus.IN_PROGRESS
    await self.task_repo.update(task)

# 승인/반려 시에 DONE/REJECTED로 변경
```

**예상 영향:**
- 상태 다이어그램 수정
- 문서 갱신
- 테스트 코드 수정

---

### 2️⃣ get_manual_by_version 임시 구현 (중대)

**문제:**
- 함수명: "특정 버전의 메뉴얼 상세 조회"
- 실제 동작: "특정 버전의 첫 번째 메뉴얼만 반환"

**현재 코드:**

```python
# app/services/manual_service.py:190-247
async def get_manual_by_version(
    self, manual_id: UUID, version: str
) -> ManualDetailResponse:
    # 버전 조회
    manual_version = await self.version_repo.get_by_version(version)

    # 해당 버전의 메뉴얼 항목 조회 (APPROVED 상태만)
    entries = list(
        await self.manual_repo.find_by_version(
            manual_version.id,
            statuses={ManualStatus.APPROVED},
        )
    )

    # ⚠️ 임시 구현: 첫 번째 엔트리 반환
    # TODO: manual_id를 기반으로 특정 항목만 반환하도록 수정
    entry = entries[0]  # ← 항상 첫 번째만 반환!

    return ManualDetailResponse(...)
```

**문제점:**

```
API 요청:
  GET /manuals/menu_123/versions/v2

예상:
  menu_123이 해당 버전에 있으면 그 항목 반환

실제 동작:
  버전 v2의 첫 번째 APPROVED 메뉴얼 반환 (menu_123 무시)
```

**개선 방안:**

```python
async def get_manual_by_version(
    self, manual_id: UUID, version: str
) -> ManualDetailResponse:
    # 버전 조회
    manual_version = await self.version_repo.get_by_version(version)

    # 특정 메뉴얼 조회
    entry = await self.manual_repo.get_by_id(manual_id)
    if entry is None:
        raise RecordNotFoundError(f"ManualEntry(id={manual_id}) not found")

    # 버전 일치 확인
    if entry.version_id != manual_version.id:
        raise RecordNotFoundError(
            f"ManualEntry(id={manual_id}) not found in version '{version}'"
        )

    # 상태 확인 (APPROVED만 반환)
    if entry.status != ManualStatus.APPROVED:
        raise RecordNotFoundError(
            f"ManualEntry(id={manual_id}) is {entry.status}, not APPROVED"
        )

    # guideline 파싱
    guidelines = parse_guideline_string(entry.guideline)

    return ManualDetailResponse(...)
```

**예상 영향:**
- API 동작 명확화
- 요청 매개변수 활용
- 에러 처리 개선

---

### 3️⃣ 환각 검증 실패 시 리뷰 태스크 속성 불명확 (중대)

**문제:**
- 환각 검증 실패로 생성된 리뷰 태스크의 특성이 명확하지 않음

**현재 코드:**

```python
# app/services/manual_service.py:1055-1069
async def _create_review_task(
    self,
    *,
    new_entry: ManualEntry,
    reason: str,
) -> ManualReviewTask:
    task = ManualReviewTask(
        old_entry_id=None,        # ← 기존 메뉴얼 없음 (신규)
        new_entry_id=new_entry.id,
        similarity=0.0,            # ← 유사도 0 (의미 없음)
        status=TaskStatus.TODO,
        decision_reason=reason,    # validation_failed
    )
    await self.review_repo.create(task)
    return task
```

**혼동되는 부분:**

1. **old_entry_id = NULL인 경우의 의미**
   - 충돌 감지로 생성된 리뷰: old_entry_id = 기존 메뉴얼 ID (비교 필요)
   - 환각 검증 실패로 생성된 리뷰: old_entry_id = NULL (비교 불필요)
   - 두 경우가 같은 테이블에 섞임

2. **similarity = 0.0의 의미**
   - 충돌 감지: VectorStore 유사도 점수 (실제 값)
   - 환각 검증: 의미 없는 값

**개선 방안:**

**옵션 A: 분리 (권장)**
```python
# 환각 검증 실패 전용 테이블 생성
class ManualValidationFailureTask(BaseModel):
    new_entry_id: UUID
    failure_reason: str  # "missing_keywords", "background_missing", "guideline_missing"
    failed_items: list[str]  # 실패 항목 목록

# 리뷰 태스크는 오직 "충돌 감지"만 담당
```

**옵션 B: 통합** (현재)
```python
# 문서에 명확히 설명
"""
old_entry_id = NULL인 경우:
  - 환각 검증 실패로 생성된 리뷰 태스크
  - similarity = 0.0 (무시)
  - decision_reason = "validation_failed" | "missing_keywords:..." | ...
  - 검토자가 메뉴얼 내용 수정 검토

old_entry_id != NULL인 경우:
  - 충돌 감지로 생성된 리뷰 태스크
  - similarity = VectorStore 유사도 (실제 값)
  - decision_reason = "auto_conflict_detected"
  - 검토자가 기존 메뉴얼과 비교 검토
"""
```

**예상 영향:**
- 리뷰 태스크 필터링 로직 명확화
- 검토자 UI에서 다른 방식으로 표시 필요

---

## 🟠 P1 (높음 우선순위)

### 4️⃣ 논리적 키 생성 규칙 설명 부족

**문제:**
- 대부분의 경우: `"{business_type}::{error_code}"`
- 특수 케이스: `"{business_type}::{error_code}::{topic}"`

**현재 코드:**

```python
# app/services/manual_service.py:772-781
def _logical_key(self, entry: ManualEntry) -> str:
    """업무구분/에러코드 기반 논리 키 생성 (없으면 topic까지 포함)."""

    business = entry.business_type or "default"
    error = entry.error_code or "none"
    topic_part = (entry.topic or "").strip().lower()

    if entry.business_type is None and entry.error_code is None and topic_part:
        return f"{business}::{error}::{topic_part}"
    return f"{business}::{error}"
```

**문제점:**

1. **Deprecate 로직에 미치는 영향**
   ```python
   # 승인 시 이전 메뉴얼 Deprecate
   await self._deprecate_previous_entries(manual)

   # 내부 구현
   stmt = select(ManualEntry).where(
       ManualEntry.business_type == manual.business_type,
       ManualEntry.error_code == manual.error_code,  # ← topic 무시
   )
   ```

   **결과:** business_type과 error_code가 같으면 topic이 달라도 Deprecate됨

2. **Diff 계산에 미치는 영향**
   ```python
   base_map = {self._logical_key(entry): entry for entry in base_entries}
   compare_map = {self._logical_key(entry): entry for entry in compare_entries}
   ```

   **예시:**
   ```
   v1:
     - key="인터넷뱅킹::ERR_001", topic="로그인 오류"

   v2:
     - key="인터넷뱅킹::ERR_001", topic="로그인 오류 (수정)"

   Diff에서: 내용 수정으로 표시 (topic은 건드리지 않았더라도)
   ```

**개선 방안:**

```python
def _logical_key(self, entry: ManualEntry) -> str:
    """
    논리적 키 생성 규칙:

    정상 케이스 (권장):
      "{business_type}::{error_code}"
      예: "인터넷뱅킹::ERR_LOGIN_001"

    특수 케이스 (business_type, error_code 모두 NULL):
      "{business_type}::{error_code}::{topic_lowercase}"
      예: "default::none::특수_처리방법"

    주의:
      - topic은 논리적 키에 포함되지 않는 것이 정상
      - topic 변경만으로는 메뉴얼이 "수정"되지 않음
      - Deprecate 시 topic 무관하게 동작
    """

    business = entry.business_type or "default"
    error = entry.error_code or "none"

    # 둘 다 NULL인 경우만 topic 포함
    if entry.business_type is None and entry.error_code is None:
        topic_part = (entry.topic or "").strip().lower()
        if topic_part:
            return f"{business}::{error}::{topic_part}"

    return f"{business}::{error}"
```

**예상 영향:**
- 문서 명확화 (코드 변경 불필요)
- Deprecate 로직 재검토

---

### 5️⃣ VectorStore 인덱싱 실패 처리

**문제:**
- VectorStore 인덱싱 실패해도 **메뉴얼은 APPROVED 상태 유지**
- 검색에 포함되지 않음 (데이터 불일치)

**현재 코드:**

```python
# app/services/manual_service.py:878-901
async def _index_manual_vector(self, manual: ManualEntry) -> None:
    """APPROVED 메뉴얼을 VectorStore에 인덱싱 (재사용 가능 헬퍼)."""

    if self.vectorstore is None:
        logger.warning("manual_vectorstore_not_configured_skip_index", ...)
        return

    text = self._build_manual_text(manual)
    metadata = {...}

    try:
        await self.vectorstore.index_document(
            id=manual.id,
            text=text,
            metadata=metadata,
        )
        logger.info("manual_indexed", manual_id=str(manual.id))
    except Exception as exc:  # ← 예외 무시!
        logger.warning("manual_index_failed", ...)
        metrics_counter("vector_index_failure", target="manual")
        # 메뉴얼 승인은 계속 진행됨
```

**문제 시나리오:**

```
1. 메뉴얼 승인 요청
2. ManualEntry status = APPROVED
3. ManualVersion 생성 및 할당
4. 기존 메뉴얼 DEPRECATED 처리
5. VectorStore 인덱싱 시도
   ❌ Pinecone 연결 실패 (네트워크 오류)
6. 예외 무시, 함수 반환
7. 사용자에게 "승인 완료" 응답

결과:
  - DB: APPROVED 상태
  - VectorStore: 인덱스 없음
  - 검색: 해당 메뉴얼 조회 불가 (데이터 불일치)
```

**개선 방안:**

**옵션 A: 재시도 큐 (권장)**
```python
async def _index_manual_vector(self, manual: ManualEntry) -> None:
    try:
        await self.vectorstore.index_document(...)
        logger.info("manual_indexed", manual_id=str(manual.id))
    except Exception as exc:
        logger.warning("manual_index_failed", ...)

        # 재시도 큐에 추가
        await self.retry_queue.enqueue(
            operation="index_manual",
            manual_id=str(manual.id),
            retry_count=0,
            max_retries=3,
        )
```

**옵션 B: 승인 취소**
```python
async def _index_manual_vector(self, manual: ManualEntry) -> None:
    try:
        await self.vectorstore.index_document(...)
    except Exception as exc:
        logger.error("manual_index_failed_reverting_approval", ...)

        # 승인 상태 되돌리기
        manual.status = ManualStatus.DRAFT
        manual.version_id = None
        await self.manual_repo.update(manual)

        # 버전도 제거
        # ...

        raise BusinessLogicError("VectorStore 인덱싱 실패, 승인 취소됨")
```

**옵션 C: 비동기 처리**
```python
# 승인은 먼저 처리
await self.manual_repo.update(manual)

# 인덱싱은 백그라운드에서 (비동기)
asyncio.create_task(self._index_manual_vector_async(manual))
```

**예상 영향:**
- 데이터 일관성 확보
- 시스템 복원력 개선
- 에러 처리 복잡도 증가

---

### 6️⃣ TaskHistory 기록 범위 불완전

**문제:**
- 리뷰 태스크 **생성 시점**의 상태 변경이 기록되지 않음
- approve_task, reject_task에서만 _add_history 호출

**현재 코드:**

```python
# app/services/manual_service.py:125-179
async def create_draft_from_consultation(self, request):
    # ...

    if has_hallucination:
        await self._create_review_task(
            new_entry=manual_entry,
            reason=";".join(fail_reasons) or "validation_failed",
        )
        # ← TaskHistory 기록 안 함!

# app/services/manual_service.py:249-329
async def check_conflict_and_create_task(self, manual_id):
    # ...

    task = ManualReviewTask(
        old_entry_id=chosen.id,
        new_entry_id=manual.id,
        similarity=chosen_score,
        status=TaskStatus.TODO,
        decision_reason="auto_conflict_detected",
    )
    await self.review_repo.create(task)
    # ← TaskHistory 기록 안 함!

# app/services/task_service.py:71-98
async def approve_task(self, task_id, payload):
    # ...
    await self._add_history(
        task,
        TaskStatus.DONE,  # ← 여기서만 기록
        changed_by=payload.employee_id,
    )
```

**문제점:**

```
TaskHistory 테이블에는 다음만 기록됨:
  - TODO → DONE
  - TODO → REJECTED

기록되지 않은 것:
  - "없음" → TODO (생성 시점)
```

**개선 방안:**

```python
async def _create_review_task(
    self,
    *,
    new_entry: ManualEntry,
    reason: str,
) -> ManualReviewTask:
    task = ManualReviewTask(
        old_entry_id=None,
        new_entry_id=new_entry.id,
        similarity=0.0,
        status=TaskStatus.TODO,
        decision_reason=reason,
    )
    await self.review_repo.create(task)

    # TaskHistory 기록: 생성 시점
    await self._add_history(
        task,
        to_status=TaskStatus.TODO,
        changed_by="system",  # 시스템이 자동 생성
        reason=f"auto_created_{reason}",
    )

    return task
```

**예상 영향:**
- 감사 추적 완성
- 리뷰 태스크 생성 원인 추적 가능

---

### 7️⃣ 동시성 이슈 - 경합 조건 (Race Condition)

**문제:**
- 같은 논리적 키로 동시에 두 메뉴얼 승인 시 예측 불가능한 동작

**시나리오:**

```
시간 T0:
  - 메뉴얼 A (인터넷뱅킹::ERR_001, v1) APPROVED
  - 메뉴얼 B (인터넷뱅킹::ERR_001, DRAFT)
  - 메뉴얼 C (인터넷뱅킹::ERR_001, DRAFT)

시간 T1 (동시에):
  POST /manuals/approve/B
  POST /manuals/approve/C

T1 + 1ms: B 승인 처리 시작
  - v2 버전 생성
  - A 상태를 DEPRECATED로 변경

T1 + 2ms: C 승인 처리 시작
  - v2 버전 조회 (이미 생성됨)
  - A 상태 변경 시도 (이미 DEPRECATED)
  - B 상태는 어떻게?

결과: 불명확한 상태
```

**현재 코드:**

```python
# app/services/manual_service.py:331-369
async def approve_manual(self, manual_id: UUID, request: ManualApproveRequest):
    manual = await self.manual_repo.get_by_id(manual_id)

    latest_version = await self.version_repo.get_latest_version()
    next_version_num = self._next_version_number(latest_version)
    next_version = ManualVersion(version=str(next_version_num))
    await self.version_repo.create(next_version)  # ← 동시 생성 가능

    await self._deprecate_previous_entries(manual)  # ← 동시 Deprecate 가능

    manual.status = ManualStatus.APPROVED
    manual.version_id = next_version.id
    await self.manual_repo.update(manual)  # ← 동시 update 가능
```

**개선 방안:**

**옵션 A: 데이터베이스 잠금** (권장)
```python
async def approve_manual(self, manual_id: UUID, request: ManualApproveRequest):
    # 트랜잭션 시작
    async with self.session.begin():
        # 행 잠금 (SELECT FOR UPDATE)
        manual = await self.manual_repo.get_by_id_for_update(manual_id)

        # 같은 키의 다른 APPROVED 메뉴얼도 잠금
        other_approved = await self.manual_repo.find_by_business_and_error_for_update(
            business_type=manual.business_type,
            error_code=manual.error_code,
            statuses={ManualStatus.APPROVED},
        )

        # 이제 동시성 안전
        latest_version = await self.version_repo.get_latest_version()
        next_version = ManualVersion(version=str(int(latest_version.version) + 1))
        await self.version_repo.create(next_version)

        await self._deprecate_previous_entries(manual)
        manual.status = ManualStatus.APPROVED
        manual.version_id = next_version.id
        await self.manual_repo.update(manual)
```

**옵션 B: 버전 시퀀스** (간단)
```python
# PostgreSQL 시퀀스 사용
class ManualVersion(BaseModel):
    version: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        server_default="concat('v', nextval('manual_version_seq'))",
    )
```

**예상 영향:**
- 데이터 일관성 보장
- 복잡도 증가

---

## 🟡 P2 (중간 우선순위)

### 8️⃣ 환경 변수 설정 확인 필요

**문제:**
- 충돌 감지 임계값이 하드코딩되어 있음

**현재 코드:**

```python
# app/services/manual_service.py:249-254
async def check_conflict_and_create_task(
    self,
    manual_id: UUID,
    *,
    top_k: int = 3,  # ← 기본값
    similarity_threshold: float = 0.85,  # ← 기본값
):
```

**확인 필요:**

1. `.env` 파일에 이 값들이 있나?
   ```bash
   SEARCH_TOP_K=10
   SEARCH_SIMILARITY_THRESHOLD=0.7
   MANUAL_SIMILARITY_THRESHOLD=0.85
   ```

2. 설정 로드 방식
   ```python
   # app/core/config.py에서 로드되나?
   MANUAL_CONFLICT_TOP_K: int = Field(default=3, env="MANUAL_CONFLICT_TOP_K")
   MANUAL_CONFLICT_SIMILARITY_THRESHOLD: float = Field(default=0.85, env="MANUAL_CONFLICT_SIMILARITY_THRESHOLD")
   ```

**개선 방안:**

```python
from app.core.config import settings

async def check_conflict_and_create_task(
    self,
    manual_id: UUID,
    *,
    top_k: int | None = None,
    similarity_threshold: float | None = None,
):
    top_k = top_k or settings.MANUAL_CONFLICT_TOP_K
    similarity_threshold = similarity_threshold or settings.MANUAL_CONFLICT_SIMILARITY_THRESHOLD

    # ...
```

---

### 9️⃣ 엔드포인트 구현 상태 불일치

**문제:**
- 문서에서 설명한 엔드포인트 중 일부가 구현되지 않았거나 다름

**확인 사항:**

| 엔드포인트 | 문서 설명 | 실제 구현 | 상태 |
|-----------|---------|---------|------|
| PATCH /manual-review/tasks/{id}/start | TODO → IN_PROGRESS | ❌ 미구현 | P1 |
| GET /manual-review/tasks | 필터링 가능 | ⚠️ 부분 구현 | P2 |
| PUT /manuals/{id} | DRAFT 수정 | ✅ 구현됨 | OK |
| POST /manuals/approve/{id} | 승인 + 버전 | ✅ 구현됨 | OK |

**누락된 엔드포인트:**

```python
# 구현 필요
@router.patch(
    "/tasks/{task_id}/start",
    response_model=ManualReviewTaskResponse,
    summary="Start reviewing task",
)
async def start_review_task(
    task_id: UUID,
    service: TaskService = Depends(get_task_service),
) -> ManualReviewTaskResponse:
    """
    리뷰 태스크를 IN_PROGRESS 상태로 변경
    (검토자가 검토를 시작했음을 표시)
    """
    return await service.start_task(task_id)
```

---

## 🟢 P3 (낮은 우선순위 / 참고사항)

### 🔟 VectorStore 정규화

**참고:**
- 메뉴얼 검색 시 VectorStore의 메타데이터 필터링
- [app/services/manual_service.py:930-997](../app/services/manual_service.py#L930)
- Rerank 로직으로 재정렬

**특이점:**
```python
# 검색 결과 재정렬
reranked = rerank_results(
    base_results,
    domain_weight_config={
        "business_type": params.business_type,
        "error_code": params.error_code,
        "business_type_weight": 0.05,
        "error_code_weight": 0.05,
    },
    recency_weight_config={"weight": 0.05, "half_life_days": 30},
)
```

**개선 고려사항:**
- 가중치 조정 가능성
- 캐싱 전략

---

## 📋 체크리스트: 개발 시 확인사항

### 즉시 처리 (Sprint N)
- [ ] **IN_PROGRESS 상태 결정**: 사용할지 제거할지 결정
- [ ] **get_manual_by_version 수정**: 첫 번째가 아닌 요청한 manual_id 반환
- [ ] **환각 검증 태스크 분류**: 분리 또는 통합 방식 결정

### 높은 우선순위 (Sprint N+1)
- [ ] **논리적 키 문서화**: Deprecate 영향 범위 명확히
- [ ] **VectorStore 실패 처리**: 재시도 큐 또는 다른 방식 구현
- [ ] **TaskHistory 완성**: 생성 시점 기록 추가
- [ ] **동시성 제어**: 데이터베이스 잠금 또는 시퀀스 구현

### 중간 우선순위 (Sprint N+2)
- [ ] **환경 변수 설정**: 하드코딩된 값 외부화
- [ ] **엔드포인트 완성**: /tasks/{id}/start 구현
- [ ] **테스트 작성**: 동시성, 경합 조건 테스트

### 낮은 우선순위 (추후)
- [ ] **성능 최적화**: VectorStore 캐싱
- [ ] **모니터링**: 메트릭 수집 및 분석

---

## 📚 참고 파일

| 파일 | 라인 | 내용 |
|------|------|------|
| [app/services/manual_service.py](../app/services/manual_service.py) | 125 | 초안 생성 |
| [app/services/manual_service.py](../app/services/manual_service.py) | 190 | get_manual_by_version (임시) |
| [app/services/manual_service.py](../app/services/manual_service.py) | 249 | 충돌 감지 |
| [app/services/manual_service.py](../app/services/manual_service.py) | 331 | 승인 (버전 관리) |
| [app/services/manual_service.py](../app/services/manual_service.py) | 772 | 논리적 키 생성 |
| [app/services/manual_service.py](../app/services/manual_service.py) | 878 | VectorStore 인덱싱 |
| [app/services/task_service.py](../app/services/task_service.py) | 71 | 리뷰 승인 |
| [app/models/task.py](../app/models/task.py) | 20 | TaskStatus 정의 |
| [app/routers/tasks.py](../app/routers/tasks.py) | 42 | 리뷰 태스크 API |

---

## 🤝 작성자 노트

이 문서는 **2024년 12월 10일** 기준으로 작성되었습니다.

코드 버전:
```
commit: 2d66fe5 (feat: add common code management and enhance manual APIs)
```

각 항목의 우선순위는 **데이터 일관성**과 **사용자 경험**을 기준으로 매겨졌습니다.

개발 시 이 문서를 기준으로 코드 리뷰를 진행하세요.
