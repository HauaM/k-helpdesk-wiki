from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.core.exceptions import ValidationError
from app.llm.protocol import LLMResponse
from app.models.manual import ManualEntry, ManualStatus, ManualVersion
from app.services.manual_service import ManualService


class DummyLLM:
    model = "dummy-model"

    async def complete_json(self, *args, **kwargs):
        return {}

    async def complete(self, *args, **kwargs):
        return LLMResponse(content="summary")


class DummyReviewRepo:
    pass


class DummyConsultationRepo:
    pass


class FakeManualRepo:
    def __init__(
        self,
        version_entries: dict,
        consultation_entries: dict | None = None,
    ):
        self.version_entries = version_entries
        self.consultation_entries = consultation_entries or {}
        self._by_id = {}
        for entries in self.version_entries.values():
            for entry in entries:
                self._by_id[entry.id] = entry
        for entries in self.consultation_entries.values():
            for entry in entries:
                self._by_id[entry.id] = entry

    async def find_by_version(self, version_id, *, statuses=None):
        entries = self.version_entries.get(version_id, [])
        if statuses:
            entries = [entry for entry in entries if entry.status in statuses]
        return entries

    async def get_by_id(self, manual_id):
        return self._by_id.get(manual_id)

    async def find_by_consultation_id(self, consultation_id):
        return self.consultation_entries.get(consultation_id, [])


class FakeVersionRepo:
    def __init__(self, versions: list[ManualVersion]):
        self.versions = versions

    async def list_versions(self, limit: int | None = None):
        ordered = sorted(self.versions, key=lambda v: v.created_at, reverse=True)
        return ordered if limit is None else ordered[:limit]

    async def get_by_version(self, version: str):
        return next((v for v in self.versions if v.version == version), None)

    async def get_latest_version(self):
        versions = await self.list_versions(limit=1)
        return versions[0] if versions else None


def _make_version(version: str, *, created_at: datetime) -> ManualVersion:
    obj = ManualVersion(version=version)
    obj.created_at = created_at
    obj.updated_at = created_at
    return obj


def _make_entry(
    *,
    keywords: list[str],
    topic: str,
    background: str,
    guideline: str,
    business_type: str | None,
    error_code: str | None,
    status: ManualStatus,
    version_id,
    consultation_id,
) -> ManualEntry:
    entry = ManualEntry(
        keywords=keywords,
        topic=topic,
        background=background,
        guideline=guideline,
        business_type=business_type,
        error_code=error_code,
        source_consultation_id=consultation_id,
        status=status,
        version_id=version_id,
    )
    now = datetime.now(tz=timezone.utc)
    entry.created_at = now
    entry.updated_at = now
    return entry


async def test_diff_versions_detects_added_removed_modified():
    v1 = _make_version("1", created_at=datetime(2024, 1, 1, tzinfo=timezone.utc))
    v2 = _make_version("2", created_at=datetime(2024, 2, 1, tzinfo=timezone.utc))

    consultation_id = uuid4()
    base_entry = _make_entry(
        keywords=["a"],
        topic="Topic1",
        background="Background1",
        guideline="Guide1",
        business_type="biz",
        error_code="E1",
        status=ManualStatus.APPROVED,
        version_id=v1.id,
        consultation_id=consultation_id,
    )
    removed_entry = _make_entry(
        keywords=["b"],
        topic="Topic2",
        background="Background2",
        guideline="Guide2",
        business_type="biz2",
        error_code="E2",
        status=ManualStatus.APPROVED,
        version_id=v1.id,
        consultation_id=consultation_id,
    )
    modified_entry = _make_entry(
        keywords=["a", "c"],
        topic="Topic1",
        background="Background1 updated",
        guideline="Guide1",
        business_type="biz",
        error_code="E1",
        status=ManualStatus.APPROVED,
        version_id=v2.id,
        consultation_id=consultation_id,
    )
    added_entry = _make_entry(
        keywords=["d"],
        topic="Topic3",
        background="Background3",
        guideline="Guide3",
        business_type="biz3",
        error_code="E3",
        status=ManualStatus.APPROVED,
        version_id=v2.id,
        consultation_id=consultation_id,
    )

    manual_repo = FakeManualRepo(
        {
            v1.id: [base_entry, removed_entry],
            v2.id: [modified_entry, added_entry],
        }
    )
    version_repo = FakeVersionRepo([v1, v2])
    service = ManualService(
        session=None,
        llm_client=DummyLLM(),
        vectorstore=None,
        manual_repo=manual_repo,
        review_repo=DummyReviewRepo(),
        version_repo=version_repo,
        consultation_repo=DummyConsultationRepo(),
    )

    # Use base_entry.id instead of "default" string
    diff = await service.diff_versions(
        base_entry.id,  # Fixed: Use actual UUID instead of "default"
        base_version=None,
        compare_version=None,
        summarize=False,
    )

    assert diff.base_version == "1"
    assert diff.compare_version == "2"
    assert len(diff.added_entries) == 1
    assert len(diff.removed_entries) == 1
    assert len(diff.modified_entries) == 1
    assert diff.modified_entries[0].logical_key == "biz::E1"
    assert "background" in diff.modified_entries[0].changed_fields
    assert "keywords" in diff.modified_entries[0].changed_fields


@pytest.mark.asyncio
async def test_diff_versions_requires_two_versions():
    v1 = _make_version("1", created_at=datetime(2024, 1, 1, tzinfo=timezone.utc))
    
    # Create an entry with v1 version
    entry_v1 = _make_entry(
        topic="Topic1",
        version_id=v1.id,
    )
    
    manual_repo = FakeManualRepo({v1.id: [entry_v1]})
    version_repo = FakeVersionRepo([v1])
    service = ManualService(
        session=None,
        llm_client=DummyLLM(),
        vectorstore=None,
        manual_repo=manual_repo,
        review_repo=DummyReviewRepo(),
        version_repo=version_repo,
        consultation_repo=DummyConsultationRepo(),
    )

    # Use entry_v1.id instead of "default" string
    with pytest.raises(ValidationError):
        await service.diff_versions(
            entry_v1.id,  # Fixed: Use actual UUID instead of "default"
            base_version=None,
            compare_version=None,
        )


@pytest.mark.asyncio
async def test_diff_draft_with_active_overrides_base_entry():
    v1 = _make_version("1", created_at=datetime(2024, 1, 1, tzinfo=timezone.utc))
    consultation_id = uuid4()
    base_entry = _make_entry(
        keywords=["x"],
        topic="TopicX",
        background="Base background",
        guideline="GuideX",
        business_type="biz",
        error_code="E1",
        status=ManualStatus.APPROVED,
        version_id=v1.id,
        consultation_id=consultation_id,
    )
    draft_entry = _make_entry(
        keywords=["x", "y"],
        topic="TopicX",
        background="Draft background updated",
        guideline="GuideX",
        business_type="biz",
        error_code="E1",
        status=ManualStatus.DRAFT,
        version_id=None,
        consultation_id=consultation_id,
    )

    manual_repo = FakeManualRepo(
        {v1.id: [base_entry]},
        consultation_entries={consultation_id: [draft_entry]},
    )
    version_repo = FakeVersionRepo([v1])
    service = ManualService(
        session=None,
        llm_client=DummyLLM(),
        vectorstore=None,
        manual_repo=manual_repo,
        review_repo=DummyReviewRepo(),
        version_repo=version_repo,
        consultation_repo=DummyConsultationRepo(),
    )

    diff = await service.diff_draft_with_active(draft_entry.id, summarize=False)

    assert diff.base_version == "1"
    assert diff.compare_version == "DRAFT"
    assert not diff.added_entries
    assert not diff.removed_entries
    assert len(diff.modified_entries) == 1
    assert diff.modified_entries[0].before.background == "Base background"
    assert diff.modified_entries[0].after.background == "Draft background updated"
