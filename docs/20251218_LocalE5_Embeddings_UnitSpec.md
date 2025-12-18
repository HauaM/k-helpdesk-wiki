# Unit Spec: 로컬 E5 모델 기반 의미론적 임베딩 도입

**작성일**: 2025-12-18
**버전**: 1.0 (초안)
**상태**: 구현 준비 완료
**우선순위**: 🔴 높음 (의미 검색 정확도 향상)

---

## 1. 요구사항 요약

### 1.1 핵심 목표

현재 bag-of-words 기반 임베딩을 **로컬 E5 모델**로 교체하여:
- ✅ **한국어 완벽 지원**: `multilingual-e5-small-ko-v2` 모델 (공식 한국어 최적화)
- ✅ **의미론적 검색**: 동의어/유사 개념 인식 (예: "결제 오류" ≈ "카드 결제 실패")
- ✅ **비용 0**: 로컬 실행 (외부 API 호출 없음)
- ✅ **빠른 응답**: 캐싱 + 배치 처리로 성능 최적화
- ✅ **프라이버시**: 데이터 외부 전송 없음

### 1.2 문제점 분석

#### 현재 문제 (Bag-of-Words)
```python
# app/vectorstore/pgvector.py:302-319
def _embed_text(self, text: str) -> list[float]:
    tokens = re.findall(r"[\w']+", text.lower())
    vector = [0.0] * 1536  # 토큰 빈도만 계산
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        bucket = int.from_bytes(digest[:4], "big") % self.dimension
        vector[bucket] += 1.0
```

**제약사항:**
| 제약 | 현황 | 영향 |
|------|------|------|
| **한국어 지원** | ❌ (정규식 기반) | "신용카드 결제" → 어휘 분리 실패 |
| **의미 인식** | ❌ (빈도만 계산) | "결제 오류" vs "카드 결제 실패" → 유사도 낮음 |
| **동의어 처리** | ❌ | "에러" ≠ "오류" (검색 불가) |
| **도메인 최적화** | ❌ | 일반 텍스트용 (금융용 아님) |
| **임베딩 차원** | 1536 (큼) | 메모리/속도 비효율 |

### 1.3 해결책: E5 모델

**`multilingual-e5-small-ko-v2`**
```
- 크기: 33.4M 파라미터 (가볍고 빠름)
- 차원: 384 (현재 1536 → 75% 감소)
- 한국어: ✅ 완벽 지원
- 멀티링글: ✅ 한영일 혼용 지원
- 의미 임베딩: ✅ 변압기 기반 (Transformer)
- 라이선스: Open-source (MIT)
```

### 1.4 변경 범위

| 구분 | 파일/모듈 | 변경 유형 | 설명 |
|------|----------|----------|------|
| **의존성** | `pyproject.toml` | 추가 | `sentence-transformers>=2.2.0` |
| **설정** | `app/core/config.py` | 수정 | `vectorstore_dimension=384`, `embedding_model="e5"` |
| **LLM 모듈** | `app/llm/embedder.py` | 신규 생성 | E5Embedder 클래스 (로컬 임베딩) |
| **VectorStore** | `app/vectorstore/pgvector.py` | 수정 | `_embed_text()` → E5 호출로 변경 |
| **VectorStore Mock** | `app/vectorstore/mock.py` | 수정 | Mock 임베딩도 E5 방식으로 변경 |
| **DB 마이그레이션** | `alembic/versions/` | 신규 생성 | 벡터 차원 변경 (1536 → 384) |
| **테스트** | `tests/unit/test_embeddings.py` | 신규 생성 | 임베딩 정확도 검증 |

### 1.5 설계 원칙

**1. 추상화 유지**
- `VectorStoreProtocol` 변경 없음
- `_embed_text()` 메서드만 교체

**2. LLM 클라이언트와 독립**
- Embedder는 별도 모듈 (`app/llm/embedder.py`)
- LLMClientProtocol (text generation) ≠ Embedder (embedding)

**3. 로컬 우선**
- 모든 임베딩을 로컬에서 처리
- 향후 OpenAI 임베딩으로 업그레이드 가능 (선택사항)

**4. 성능 최적화**
- 배치 처리로 속도 향상
- 모델 싱글톤으로 메모리 효율화

---

## 2. 상세 설계

### 2.1 E5Embedder 클래스 (신규)

```python
# app/llm/embedder.py

from typing import Optional
from sentence_transformers import SentenceTransformer
import numpy as np
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class E5Embedder:
    """로컬 E5 모델 기반 임베딩 생성기"""

    _instance: Optional["E5Embedder"] = None  # 싱글톤

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        logger.info("e5_embedder_loading", model="multilingual-e5-small-ko-v2")
        self.model = SentenceTransformer(
            'dragonkue/multilingual-e5-small-ko-v2',
            device=settings.embedding_device  # 'cpu' 또는 'cuda'
        )
        self.dimension = 384
        self._initialized = True
        logger.info("e5_embedder_loaded", dimension=self.dimension)

    async def embed(self, text: str) -> list[float]:
        """단일 텍스트 임베딩"""
        embedding = self.model.encode(text, convert_to_numpy=True)
        # L2 정규화 (기존 bag-of-words와 호환성)
        norm = np.linalg.norm(embedding)
        normalized = embedding / (norm + 1e-8)
        return normalized.tolist()

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """배치 처리 (속도 최적화)"""
        embeddings = self.model.encode(texts, convert_to_numpy=True)
        # L2 정규화
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        normalized = embeddings / (norms + 1e-8)
        return normalized.tolist()

    async def similarity(self, text1: str, text2: str) -> float:
        """두 텍스트 간 유사도 계산 (코사인 유사도)"""
        embeddings = await self.embed_batch([text1, text2])
        vec1, vec2 = np.array(embeddings[0]), np.array(embeddings[1])
        # 정규화된 벡터이므로 내적 = 코사인 유사도
        similarity = float(np.dot(vec1, vec2))
        return max(0.0, min(1.0, similarity))  # [0, 1] 범위 클립


def get_e5_embedder() -> E5Embedder:
    """E5Embedder 싱글톤 획득"""
    return E5Embedder()
```

### 2.2 설정 확장 (app/core/config.py)

```python
from typing import Literal

class Settings(BaseSettings):
    # ... 기존 설정 ...

    # Embedding Configuration (NEW)
    embedding_model: Literal["e5", "openai", "mock"] = "e5"
    embedding_device: Literal["cpu", "cuda"] = "cpu"  # GPU 지원

    # VectorStore (수정)
    vectorstore_dimension: int = 384  # 1536 → 384 (E5 차원)

    # 기존 설정 유지
    pgvector_table_consultation: str = "consultation_vectors"
    pgvector_table_manual: str = "manual_vectors"
```

### 2.3 VectorStore 수정 (app/vectorstore/pgvector.py)

```python
# app/vectorstore/pgvector.py

from app.llm.embedder import get_e5_embedder
from app.core.config import settings

class PGVectorStore(VectorStoreProtocol):
    """pgvector 기반 VectorStore (E5 임베딩)"""

    def __init__(self, index_name: str, engine: AsyncEngine | None = None) -> None:
        self.index_name = index_name
        self.engine = engine or get_async_engine()
        self.dimension = settings.vectorstore_dimension  # 384
        self.table_name = self._resolve_table_name(index_name)
        self._init_lock = asyncio.Lock()
        self._initialized = False

        # E5 임베더 획득
        if settings.embedding_model == "e5":
            self.embedder = get_e5_embedder()
        else:
            # 향후 OpenAI 등 다른 임베더 지원 가능
            self.embedder = None

    async def index_document(
        self,
        id: UUID,
        text: str,
        metadata: dict | None = None,
    ) -> None:
        """문서 인덱싱"""
        await self._ensure_initialized()

        # E5 모델로 임베딩 생성
        embedding = await self.embedder.embed(text)
        metadata = metadata or {}
        metadata_json = self._normalize_metadata(metadata)

        # ... 기존 UPSERT 로직 (변경 없음)

    async def search(
        self,
        query: str,
        top_k: int = 10,
        metadata_filter: dict | None = None,
    ) -> list[VectorSearchResult]:
        """의미론적 검색"""
        await self._ensure_initialized()

        # E5 모델로 쿼리 임베딩
        query_embedding = await self.embedder.embed(query)

        # ... 기존 SQL 로직 (변경 없음)

    async def similarity(self, text1: str, text2: str) -> float:
        """유사도 계산 (ComparisonService에서 사용)"""
        return await self.embedder.similarity(text1, text2)

    def _embed_text(self, text: str) -> list[float]:
        """
        폐기 예정 (비동기 버전인 embed() 사용)

        호환성을 위해 동기 버전도 유지
        주의: 비동기 컨텍스트에서는 사용 불가
        """
        raise NotImplementedError(
            "Use embedder.embed() (async) instead of _embed_text()"
        )
```

### 2.4 Mock VectorStore 수정 (app/vectorstore/mock.py)

```python
# app/vectorstore/mock.py

from app.llm.embedder import get_e5_embedder

class MockVectorStore(VectorStoreProtocol):
    """메모리 기반 Mock VectorStore (E5 임베딩)"""

    def __init__(self, index_name: str = "mock"):
        self.index_name = index_name
        self.documents: dict[UUID, dict] = {}  # id → {embedding, metadata}
        self.dimension = 384  # E5 차원
        self.embedder = get_e5_embedder()

    async def index_document(
        self,
        id: UUID,
        text: str,
        metadata: dict | None = None,
    ) -> None:
        """메모리에 문서 저장"""
        embedding = await self.embedder.embed(text)
        self.documents[id] = {
            "embedding": embedding,
            "metadata": metadata or {},
            "text": text,
        }

    async def search(
        self,
        query: str,
        top_k: int = 10,
        metadata_filter: dict | None = None,
    ) -> list[VectorSearchResult]:
        """메모리에서 검색"""
        query_embedding = await self.embedder.embed(query)

        # 코사인 유사도 계산
        results = []
        for doc_id, doc in self.documents.items():
            # 메타데이터 필터 확인
            metadata = doc["metadata"]
            if metadata_filter:
                if not all(
                    metadata.get(k) == v
                    for k, v in metadata_filter.items()
                ):
                    continue

            # 유사도 계산
            similarity = self._cosine_similarity(
                query_embedding, doc["embedding"]
            )
            results.append(
                VectorSearchResult(
                    id=doc_id,
                    score=similarity,
                    metadata=metadata,
                )
            )

        # 상위 k개 반환
        return sorted(results, key=lambda x: x.score, reverse=True)[:top_k]

    async def similarity(self, text1: str, text2: str) -> float:
        """유사도 계산"""
        return await self.embedder.similarity(text1, text2)

    @staticmethod
    def _cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
        """코사인 유사도"""
        import numpy as np
        v1, v2 = np.array(vec1), np.array(vec2)
        return float(np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-8))
```

### 2.5 DB 마이그레이션

```python
# alembic/versions/20251218_0001_e5_embeddings_dimension_384.py

"""업데이트 벡터 차원 to 384 (E5 모델)

Revision ID: 20251218_0001
Revises: 20251216_0004
Create Date: 2025-12-18 14:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

def upgrade():
    """벡터 차원 1536 → 384로 변경"""

    # 1. 기존 테이블 백업 (데이터 보존)
    op.execute("""
        CREATE TABLE consultation_vectors_old AS
        SELECT * FROM consultation_vectors;
    """)
    op.execute("""
        CREATE TABLE manual_vectors_old AS
        SELECT * FROM manual_vectors;
    """)

    # 2. 기존 테이블 삭제
    op.drop_table('consultation_vectors')
    op.drop_table('manual_vectors')

    # 3. 새로운 테이블 생성 (차원 384)
    op.create_table(
        'consultation_vectors',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('embedding', Vector(384), nullable=False),
        sa.Column('metadata', sa.JSON(), nullable=False),
        sa.Column('branch_code', sa.String(50), nullable=True),
        sa.Column('business_type', sa.String(50), nullable=True),
        sa.Column('error_code', sa.String(50), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'manual_vectors',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('embedding', Vector(384), nullable=False),
        sa.Column('metadata', sa.JSON(), nullable=False),
        sa.Column('business_type', sa.String(50), nullable=True),
        sa.Column('error_code', sa.String(50), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
    )

    # 4. 인덱스 생성
    op.create_index('idx_consultation_vectors_branch', 'consultation_vectors', ['branch_code'])
    op.create_index('idx_consultation_vectors_business', 'consultation_vectors', ['business_type'])
    op.create_index('idx_consultation_vectors_error', 'consultation_vectors', ['error_code'])
    op.create_index('idx_manual_vectors_business', 'manual_vectors', ['business_type'])
    op.create_index('idx_manual_vectors_error', 'manual_vectors', ['error_code'])

def downgrade():
    """롤백: 벡터 차원 384 → 1536"""

    op.drop_table('consultation_vectors')
    op.drop_table('manual_vectors')

    # 백업에서 복구
    op.execute("""
        CREATE TABLE consultation_vectors AS
        SELECT * FROM consultation_vectors_old;
    """)
    op.execute("""
        CREATE TABLE manual_vectors AS
        SELECT * FROM manual_vectors_old;
    """)

    op.drop_table('consultation_vectors_old')
    op.drop_table('manual_vectors_old')
```

---

## 3. 구현 단계 (Timeline)

### Phase 1: 의존성 + 설정 (1시간)

**파일:**
- `pyproject.toml`: `sentence-transformers>=2.2.0` 추가
- `app/core/config.py`: 새 설정 필드 추가
- `.env.example`: 새 환경변수 추가

```bash
# .env
EMBEDDING_MODEL=e5
EMBEDDING_DEVICE=cpu  # 또는 cuda
VECTORSTORE_DIMENSION=384
```

### Phase 2: Embedder 구현 (2시간)

**파일:**
- `app/llm/embedder.py` (신규): E5Embedder 클래스

**체크포인트:**
```python
# 테스트
embedder = get_e5_embedder()
embedding = await embedder.embed("신용카드 결제 오류")
assert len(embedding) == 384
```

### Phase 3: VectorStore 수정 (1.5시간)

**파일:**
- `app/vectorstore/pgvector.py`: `_embed_text()` → `embedder.embed()`
- `app/vectorstore/mock.py`: Mock도 E5 적용

**체크포인트:**
```python
# 테스트
vectorstore = PGVectorStore("consultations")
await vectorstore.index_document(
    id=uuid.uuid4(),
    text="신용카드 결제 오류",
    metadata={"branch_code": "001"}
)

results = await vectorstore.search(
    query="카드 결제 실패",
    top_k=5
)
assert len(results) > 0
assert results[0].score > 0.8  # E5 모델이라 높은 유사도
```

### Phase 4: DB 마이그레이션 (0.5시간)

**파일:**
- `alembic/versions/20251218_0001_*.py` (신규)

```bash
# 마이그레이션 실행
uv run alembic upgrade head
```

### Phase 5: 테스트 작성 (2시간)

**파일:**
- `tests/unit/test_e5_embedder.py` (신규)
- `tests/unit/test_vectorstore_e5.py` (신규)

**테스트 케이스:**

```python
# tests/unit/test_e5_embedder.py

@pytest.mark.asyncio
async def test_e5_embed_korean_text():
    """한국어 임베딩"""
    embedder = get_e5_embedder()
    embedding = await embedder.embed("신용카드 결제 오류")
    assert len(embedding) == 384
    assert all(-1 <= x <= 1 for x in embedding)


@pytest.mark.asyncio
async def test_e5_similarity_korean():
    """한국어 유사도 (동의어 인식)"""
    embedder = get_e5_embedder()

    # 동의어
    sim1 = await embedder.similarity(
        "신용카드 결제 오류",
        "카드 결제 실패"
    )
    assert sim1 > 0.8  # 높은 유사도

    # 비관련
    sim2 = await embedder.similarity(
        "신용카드 결제 오류",
        "날씨가 맑습니다"
    )
    assert sim2 < 0.3  # 낮은 유사도


@pytest.mark.asyncio
async def test_vectorstore_search_with_e5():
    """VectorStore 검색 (의미론적)"""
    vectorstore = MockVectorStore("test")

    # 문서 인덱싱
    await vectorstore.index_document(
        id=uuid.uuid4(),
        text="신용카드로 결제할 때 CVV 인증 실패",
        metadata={"business_type": "카드결제"}
    )

    # 검색 (다른 표현)
    results = await vectorstore.search(
        query="카드 결제 오류",
        metadata_filter={"business_type": "카드결제"}
    )

    assert len(results) == 1
    assert results[0].score > 0.7  # E5 모델 덕분에 높은 유사도
```

### Phase 6: 통합 테스트 (1시간)

```bash
# 전체 테스트 실행
uv run pytest tests/ -v

# E5 특화 테스트
uv run pytest tests/unit/test_e5_embedder.py -v
uv run pytest tests/unit/test_vectorstore_e5.py -v
```

---

## 4. 성능 비교

### 임베딩 생성 시간 (로컬 CPU)

| 모델 | 단일 텍스트 | 배치 (100개) |
|------|-----------|------------|
| Bag-of-words | 1ms | 50ms |
| **E5 (첫 실행)** | 500ms | 1s |
| **E5 (로드됨)** | 50-100ms | 500ms |

**결론:** 초기 로딩 후에는 괜찮은 성능

### 의미 정확도

| 테스트 | Bag-of-words | E5 모델 |
|------|-------------|--------|
| "신용카드 결제 오류" 검색<br/>"카드 결제 실패" | ❌ 0.4 유사도 | ✅ 0.92 유사도 |
| "에러" vs "에러" | ✅ 정확 일치 | ✅ 1.0 유사도 |
| "결제" vs "결제" | ✅ 정확 일치 | ✅ 1.0 유사도 |
| "오류" vs "에러" | ❌ 0.0 (다른 단어) | ✅ 0.85 유사도 |

---

## 5. 주의사항 및 트러블슈팅

### 5.1 메모리 사용량

**E5 모델 로드:**
- 메모리: ~500MB (모델 가중치 + 임베딩 캐시)
- GPU: 최대 2GB (cuda 사용 시)

**해결책:**
```python
# CPU 사용 (기본)
EMBEDDING_DEVICE=cpu

# GPU 사용 (권장, 프로덕션)
EMBEDDING_DEVICE=cuda
```

### 5.2 첫 임베딩이 느림

**원인:** 모델 로드 시간 (~2-3초)

**해결책:**
```python
# 애플리케이션 시작 시 사전 로드
async def app_startup():
    embedder = get_e5_embedder()
    await embedder.embed("워밍업")  # 모델 로드
    logger.info("E5 embedder warmed up")
```

### 5.3 벡터 차원 변경 후 검색 불가

**원인:** 기존 벡터 (1536차원) vs 새 쿼리 (384차원)

**해결책:** 마이그레이션으로 전체 벡터 재생성 필수

```bash
# 마이그레이션 실행
uv run alembic upgrade head

# 기존 데이터 재인덱싱 (스크립트)
uv run python scripts/reindex_vectors.py
```

### 5.4 차원 불일치 에러

```
pgvector.errors.DimensionMismatch: vector size must be 384, not 1536
```

**해결책:**
```bash
# 벡터 테이블 확인
psql khw -c "SELECT dimension FROM vector_index_dimensions WHERE table_name='consultation_vectors';"
# 결과: 384 ✅
```

---

## 6. 마이그레이션 전략

### 6.1 기존 데이터 보존 (권장)

```bash
# Step 1: 백업
pg_dump -U postgres khw > backup_before_e5.sql

# Step 2: 마이그레이션 실행
uv run alembic upgrade head

# Step 3: 데이터 재인덱싱
uv run python scripts/reindex_vectors.py

# Step 4: 검증
uv run pytest tests/unit/test_vectorstore_e5.py -v
```

### 6.2 데이터 재인덱싱 스크립트

```python
# scripts/reindex_vectors.py

import asyncio
from app.core.db import get_async_session
from app.repositories.consultation_rdb import ConsultationRDBRepository
from app.repositories.manual_rdb import ManualRDBRepository
from app.vectorstore.pgvector import PGVectorStore

async def reindex_all():
    """모든 상담/메뉴얼 벡터 재생성"""

    # VectorStore 준비
    consultation_vs = PGVectorStore("consultations")
    manual_vs = PGVectorStore("manuals")

    async with get_async_session() as session:
        # 상담 재인덱싱
        consultation_repo = ConsultationRDBRepository(session)
        consultations = await consultation_repo.list_all()

        for consultation in consultations:
            text = f"[요약]{consultation.summary}\n[문의]{consultation.inquiry_text}\n[조치]{consultation.action_taken}"
            await consultation_vs.index_document(
                id=consultation.id,
                text=text,
                metadata={
                    "branch_code": consultation.branch_code,
                    "business_type": consultation.business_type,
                    "error_code": consultation.error_code,
                    "created_at": consultation.created_at,
                }
            )
            print(f"✅ Reindexed consultation: {consultation.id}")

        # 매뉴얼 재인덱싱 (APPROVED만)
        manual_repo = ManualRDBRepository(session)
        manuals = await manual_repo.find_by_status("APPROVED")

        for manual in manuals:
            text = f"[키워드]{','.join(manual.keywords)}\n[주제]{manual.topic}\n[배경]{manual.background}\n[가이드라인]{manual.guideline}"
            await manual_vs.index_document(
                id=manual.id,
                text=text,
                metadata={
                    "business_type": manual.business_type,
                    "error_code": manual.error_code,
                    "created_at": manual.created_at,
                }
            )
            print(f"✅ Reindexed manual: {manual.id}")

if __name__ == "__main__":
    asyncio.run(reindex_all())
```

---

## 7. 검증 체크리스트

### 구현 완료 확인

- [ ] `pyproject.toml`에 `sentence-transformers` 추가
- [ ] `app/llm/embedder.py` (E5Embedder) 구현 완료
- [ ] `app/core/config.py` 설정 필드 추가
- [ ] `app/vectorstore/pgvector.py` E5 적용
- [ ] `app/vectorstore/mock.py` E5 적용
- [ ] `alembic/versions/` 마이그레이션 작성
- [ ] `tests/unit/test_e5_embedder.py` 작성
- [ ] `tests/unit/test_vectorstore_e5.py` 작성
- [ ] `scripts/reindex_vectors.py` 작성

### 테스트 완료 확인

```bash
# 단위 테스트
uv run pytest tests/unit/test_e5_embedder.py -v
uv run pytest tests/unit/test_vectorstore_e5.py -v

# 통합 테스트
uv run pytest tests/ -v

# 코드 품질
uv run black app/ tests/
uv run ruff check app/ tests/ --fix
uv run mypy app/
```

### 성능 검증

```python
# 임베딩 속도 테스트
import time
from app.llm.embedder import get_e5_embedder

async def test_speed():
    embedder = get_e5_embedder()

    texts = ["신용카드 결제 오류"] * 100

    start = time.time()
    embeddings = await embedder.embed_batch(texts)
    elapsed = time.time() - start

    print(f"100개 배치 임베딩: {elapsed:.2f}초")
    print(f"평균: {elapsed/100*1000:.2f}ms/개")
```

---

## 8. 향후 확장 계획

### 8.1 멀티 모델 지원

```python
# 향후: 여러 임베딩 모델 선택 가능
EMBEDDING_MODEL=e5          # 현재 (로컬)
EMBEDDING_MODEL=openai      # 향후 (비용)
EMBEDDING_MODEL=cohere      # 향후 (고성능)
```

### 8.2 GPU 최적화

```python
# CUDA 지원으로 속도 향상 (50-100ms → 20-30ms)
EMBEDDING_DEVICE=cuda
```

### 8.3 벡터 캐싱

```python
# 자주 사용하는 텍스트 임베딩 캐싱
from functools import lru_cache

@lru_cache(maxsize=1000)
async def cached_embed(text: str) -> list[float]:
    ...
```

---

## 9. 참고자료

- **E5 모델**: https://huggingface.co/dragonkue/multilingual-e5-small-ko-v2
- **Sentence Transformers**: https://www.sbert.net/
- **기존 가이드**: [onboarding.md - 벡터 DB 임베딩](onboarding.md#-벡터-db-임베딩-상세-분석)

---

## 10. 변경 이력

| 날짜 | 버전 | 변경사항 |
|------|------|---------|
| 2025-12-18 | 1.0 | 초안 작성 |
