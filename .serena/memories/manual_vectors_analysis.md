# Manual Vectors 데이터베이스 분석

## 실제 데이터 저장소 (수정됨)

### 1. VectorStore 테이블: `manual_vectors` ✅ 실제 사용
- **설정 위치:** app/core/config.py:55
- **기본값:** "manual_vectors"
- **용도:** 벡터 임베딩 저장소 (VectorStore에 의해 관리)
- **생성:** PGVectorStore._create_extension_and_table() 호출 시 자동 생성
- **DB 상태:** ✅ PostgreSQL에 존재 (0건 또는 APPROVED manual 개수)
- **스키마:**
  - id: UUID PRIMARY KEY
  - embedding: VECTOR(1536) - 벡터 임베딩
  - metadata: JSONB - {business_type, error_code, created_at}
  - business_type: TEXT (INDEX)
  - error_code: TEXT (INDEX)
  - created_at: TIMESTAMPTZ

### 2. RDB 메타데이터 테이블: `manual_vector_index` ❌ 미완성 (설계만 존재)
- **정의:** app/models/vector_index.py:97-133 (ORM 모델만)
- **DB 상태:** ❌ PostgreSQL에 테이블 없음
- **마이그레이션:** ❌ Alembic 마이그레이션 파일 없음 (절대 CREATE된 적 없음)
- **사용 코드:** ❌ 서비스에서 호출하지 않음
- **설계 의도:** RDB에서 벡터 인덱싱 상태를 추적 (PENDING/INDEXED/FAILED)
- **역할 (미실현):** 
  1. VectorStore 인덱싱 상태 추적
  2. 실패한 인덱싱 재시도 관리
  3. VectorStore 실패 시 RDB에서 벡터 백업/복구
- **모델:** ManualVectorIndex (SQLAlchemy ORM) - 정의만 있음
- **설계 스키마:**
  - id: UUID PRIMARY KEY
  - manual_entry_id: UUID FK UNIQUE (to manual_entries)
  - embedding: ARRAY(Float) - 벡터 저장 (백업용)
  - metadata_json: JSONB - 메타데이터
  - business_type: VARCHAR(50) INDEX
  - error_code: VARCHAR(50) INDEX
  - status: ENUM('PENDING', 'INDEXED', 'FAILED') ← 상태 추적 용도
  
**현재 상황:**
- 설계: 있음 (RDB + VectorStore 이중 저장)
- 구현: 없음 (VectorStore만 단독 사용)
- 이유: 단순화를 위해 VectorStore만 사용하기로 결정

## 데이터 흐름 (실제 구현 기준)

### 1. Manual 생성 (DRAFT)
- 메서드: create_draft_from_consultation()
- RDB 저장: 
  - ✅ manual_entries (DRAFT 상태)
  - ✅ manual_versions
- VectorStore: ❌ 저장 안 함 (DRAFT 상태이므로)

### 2. Manual 수정 (DRAFT → DRAFT)
- 메서드: update_manual()
- RDB 업데이트: manual_entries 필드 업데이트만
- VectorStore: ❌ 변경 없음

### 3. Manual 승인 (DRAFT → APPROVED) ⭐ 중요!
- 메서드: approve_manual() [app/services/manual_service.py:479]
- 단계:
  1. ManualVersion 생성
  2. manual.status = ManualStatus.APPROVED 설정
  3. _index_manual_vector(manual) 호출 [line 1176]
     - ❌ manual_vector_index에는 저장 안 함 (테이블 없음)
     - ✅ vectorstore.index_document() 호출만 함
- VectorStore 저장:
  - VECTORSTORE_TYPE=mock → 메모리 저장
  - VECTORSTORE_TYPE=pgvector → manual_vectors 테이블에 UPSERT

### 4. Manual 삭제 (DRAFT 상태만)
- 메서드: delete_manual() [app/services/manual_service.py:1493]
- 조건: manual.status == ManualStatus.DRAFT만 가능
- 단계:
  1. vectorstore.delete(str(manual_id)) 호출
  2. review_tasks 삭제
  3. manual_entries 삭제
- VectorStore 삭제:
  - VECTORSTORE_TYPE=mock → 메모리에서 제거
  - VECTORSTORE_TYPE=pgvector → manual_vectors에서 DELETE

## manual_vectors가 0건인 이유

1. **VECTORSTORE_TYPE=mock 인 경우:**
   - VectorStore가 메모리(Python dict)에만 저장
   - manual_vectors 테이블 사용 안 함
   - 서버 재시작 시 데이터 손실

2. **VECTORSTORE_TYPE=pgvector 인 경우:**
   - manual_vectors 테이블에 저장
   - APPROVED manual 개수만큼 데이터 존재
   - 현재 APPROVED manual이 없으면 0건

## PGVector Index_document 동작

```python
# FROM: app/vectorstore/pgvector.py:47-97
async def index_document(id: UUID, text: str, metadata: dict | None = None):
    # SQL: UPSERT (INSERT ... ON CONFLICT DO UPDATE)
    INSERT INTO manual_vectors
        (id, embedding, metadata, branch_code, business_type, error_code, created_at)
    VALUES
        (:id, :embedding, :metadata, :branch_code, :business_type, :error_code, :created_at)
    ON CONFLICT (id) DO UPDATE SET
        embedding = EXCLUDED.embedding,
        metadata = EXCLUDED.metadata,
        ...
```

## 벡터 검색

검색 메서드: search_manuals() [ManualService]
→ vectorstore.search(query, top_k=10, metadata_filter={...})
→ PGVector SQL:
  ```sql
  SELECT id, metadata, 1.0/(1.0+(embedding <-> :embedding)) AS score
  FROM manual_vectors
  WHERE business_type = ? AND error_code = ?
  ORDER BY embedding <-> :embedding
  LIMIT 10
  ```

## 재시도 큐 통합

VectorStore 인덱싱 실패 시:
- RetryQueueJob 생성 (target_type='MANUAL', status='PENDING')
- retry_queue에서 재시도
- _index_manual_vector() 재호출

## 핵심 요점 (정정됨)

1. **APPROVED 상태에서만 벡터 저장** - DRAFT는 벡터스토어에 저장 안 함
2. **UPSERT 작동** - 동일 ID로 재인덱싱 가능
3. **메타데이터 필터링** - business_type, error_code로 검색 최적화
4. **Mock 개발 모드** - 프로덕션에서만 pgvector 활성화
5. **manual_vector_index는 미완성** - ORM 모델만 있고 마이그레이션/사용 코드 없음
6. **RDB 저장소** - manual_entries, manual_versions만 실제 사용
7. **VectorStore만 사용** - manual_vectors만 실제 벡터 저장소
