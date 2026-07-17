from __future__ import annotations

import io
from dataclasses import replace
from datetime import UTC, datetime
from email.message import Message
from urllib.error import HTTPError, URLError

import pytest

from ukei.models import ResourceReference, SourceRecord, SourceStatus
from ukei.validation import MetadataValidator, ResourceValidator, UrlValidator, run_validation


class FakeResponse(io.BytesIO):
    status = 200

    def __init__(self, body: bytes = b"x") -> None:
        super().__init__(body)
        self.headers = Message()
        self.headers["Content-Type"] = "application/json"

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def geturl(self) -> str:
        return "https://example.gov.uk/final"


def test_metadata_validator_passes_complete_source(source: SourceRecord) -> None:
    results = MetadataValidator().validate(source)
    assert len(results) == 6
    assert all(result.passed for result in results)
    assert {result.check_name for result in results} == {
        "metadata.title",
        "metadata.publisher",
        "metadata.url",
        "metadata.licence",
        "metadata.provenance",
        "metadata.completeness",
    }
    score = next(result for result in results if result.check_name == "metadata.completeness")
    assert score.details["score"] == 100


def test_metadata_validator_exposes_incomplete_assertions(source: SourceRecord) -> None:
    candidate = replace(
        source,
        url="http://example.gov.uk/data",
        licence="unknown",
        provenance_url=None,
    )
    failed = [result for result in MetadataValidator().validate(candidate) if not result.passed]
    assert [result.check_name for result in failed] == [
        "metadata.url",
        "metadata.licence",
        "metadata.provenance",
        "metadata.completeness",
    ]
    assert all(result.message.startswith("FAILED:") for result in failed)


def test_metadata_score_exposes_placeholder_fields(source: SourceRecord) -> None:
    candidate = replace(
        source,
        description="",
        licence="Not supplied by discovery response; verify before reuse",
        update_frequency="not supplied by discovery response",
        formats=(),
        themes=(),
    )
    results = MetadataValidator().validate(candidate)
    score = next(result for result in results if result.check_name == "metadata.completeness")
    assert score.details == {
        "score": 60,
        "threshold": 70,
        "missing_fields": [
            "description",
            "formats",
            "licence",
            "themes",
            "update_frequency",
        ],
    }
    assert not score.passed


def test_url_validator_records_bounded_response(
    source: SourceRecord, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("ukei.validation.live.urlopen", lambda *_args, **_kwargs: FakeResponse())
    result = UrlValidator(2).validate(source)[0]
    assert result.passed
    assert result.check_name == "live.url"
    assert result.details["status_code"] == 200
    assert result.details["final_url"] == "https://example.gov.uk/final"
    assert result.details["content_type"] == "application/json"


@pytest.mark.parametrize(
    "url",
    ["http://example.gov.uk/data", "https://localhost/data", "https://127.0.0.1/data"],
)
def test_url_validator_blocks_nonpublic_targets(source: SourceRecord, url: str) -> None:
    result = UrlValidator().validate(replace(source, url=url))[0]
    assert not result.passed
    assert "blocked" in result.message


@pytest.mark.parametrize(
    ("exception", "reason", "status"),
    [
        (
            HTTPError("https://example.gov.uk", 503, "Unavailable", Message(), None),
            "HTTP 503",
            503,
        ),
        (URLError("offline"), "offline", None),
    ],
)
def test_url_validator_records_failures(
    source: SourceRecord,
    monkeypatch: pytest.MonkeyPatch,
    exception: Exception,
    reason: str,
    status: int | None,
) -> None:
    def fail(*_args: object, **_kwargs: object) -> None:
        raise exception

    monkeypatch.setattr("ukei.validation.live.urlopen", fail)
    result = UrlValidator().validate(source)[0]
    assert not result.passed
    assert reason in result.message
    assert result.details["status_code"] == status


def test_validation_report_never_promotes_candidate(
    source: SourceRecord, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("ukei.validation.live.urlopen", lambda *_args, **_kwargs: FakeResponse())
    report = run_validation((source,), UrlValidator())
    assert report.all_passed
    assert report.sources[0].status_after is SourceStatus.CANDIDATE
    assert report.to_dict()["passed_count"] == 1


def test_failed_live_check_degrades_active_but_not_retired(
    source: SourceRecord, monkeypatch: pytest.MonkeyPatch
) -> None:
    def offline(*_args: object, **_kwargs: object) -> None:
        raise URLError("offline")

    monkeypatch.setattr("ukei.validation.live.urlopen", offline)
    report = run_validation(
        (source, replace(source, source_id="retired-source", status=SourceStatus.RETIRED)),
        UrlValidator(),
    )
    assert report.sources[0].status_after is SourceStatus.DEGRADED
    assert report.sources[1].status_after is SourceStatus.RETIRED
    assert report.to_dict()["degraded_count"] == 1


def test_resource_validator_records_url_licence_and_recency(
    source: SourceRecord, monkeypatch: pytest.MonkeyPatch
) -> None:
    resource = ResourceReference(
        resource_id="csv-1",
        url="https://example.gov.uk/data.csv",
        name="Readings",
        format="CSV",
        media_type="text/csv",
        licence="Open Government Licence 3.0",
        last_modified=datetime(2026, 7, 1, tzinfo=UTC),
        provenance_url=source.provenance_url,
        authoritative=True,
    )
    monkeypatch.setattr("ukei.validation.live.urlopen", lambda *_args, **_kwargs: FakeResponse())
    report = run_validation(
        (replace(source, resources=(resource,)),),
        resource_validator=ResourceValidator(),
    )
    checks = {result.check_name: result for result in report.sources[0].results}
    assert checks["resource.url"].passed
    assert checks["resource.url"].details["resource_id"] == "csv-1"
    assert checks["resource.licence"].passed
    assert checks["resource.recency"].passed
    assert report.sources[0].status_after is SourceStatus.CANDIDATE
    assert report.to_dict()["resource_count"] == 1
    assert report.to_dict()["resources"] is True


def test_resource_validator_flags_absence_and_staleness(source: SourceRecord) -> None:
    absent = ResourceValidator().validate(source)
    assert absent[0].check_name == "resource.presence"
    assert not absent[0].passed

    stale = ResourceReference(
        resource_id="old-1",
        url="http://example.gov.uk/old.csv",
        licence="unknown",
        last_modified=datetime(2020, 1, 1, tzinfo=UTC),
    )
    results = ResourceValidator().validate(replace(source, resources=(stale,)))
    assert not next(result for result in results if result.check_name == "resource.licence").passed
    recency = next(result for result in results if result.check_name == "resource.recency")
    assert recency.passed
    assert recency.details["outcome"] == "stale_warning"


def test_failed_resource_url_degrades_candidate(
    source: SourceRecord, monkeypatch: pytest.MonkeyPatch
) -> None:
    resource = ResourceReference(
        resource_id="resource-1",
        url="https://example.gov.uk/data.csv",
        licence="OGL-3.0",
        last_modified=datetime(2026, 7, 1, tzinfo=UTC),
    )

    def offline(*_args: object, **_kwargs: object) -> None:
        raise URLError("offline")

    monkeypatch.setattr("ukei.validation.live.urlopen", offline)
    report = run_validation(
        (replace(source, resources=(resource,)),),
        resource_validator=ResourceValidator(),
    )
    assert report.sources[0].status_after is SourceStatus.DEGRADED


def test_http_policy_block_does_not_claim_resource_is_unreachable(source: SourceRecord) -> None:
    resource = ResourceReference(
        resource_id="legacy-http",
        url="http://example.gov.uk/data.csv",
        licence="OGL-3.0",
        last_modified=datetime(2026, 7, 1, tzinfo=UTC),
    )
    report = run_validation(
        (replace(source, resources=(resource,)),), resource_validator=ResourceValidator()
    )
    url_result = next(
        result for result in report.sources[0].results if result.check_name == "resource.url"
    )
    assert url_result.details["outcome"] == "blocked_by_policy"
    assert report.sources[0].status_after is SourceStatus.CANDIDATE


def test_arcgis_service_metadata_is_semantically_checked(
    source: SourceRecord, monkeypatch: pytest.MonkeyPatch
) -> None:
    resource = ResourceReference(
        resource_id="feature-service",
        url="https://services.arcgis.com/example/FeatureServer",
        format="Feature Service",
        licence="Open Government Licence 3.0",
        last_modified=datetime(2024, 1, 1, tzinfo=UTC),
    )
    responses = iter(
        (
            FakeResponse(),
            FakeResponse(b'{"currentVersion": 11.3, "layers": [{"id": 0}], "tables": []}'),
        )
    )
    monkeypatch.setattr("ukei.validation.live.urlopen", lambda *_args, **_kwargs: next(responses))
    monkeypatch.setattr(
        "ukei.validation.resources.urlopen", lambda *_args, **_kwargs: next(responses)
    )
    report = run_validation(
        (replace(source, resources=(resource,)),), resource_validator=ResourceValidator()
    )
    service = next(
        result for result in report.sources[0].results if result.check_name == "resource.service"
    )
    assert service.passed
    assert service.details["layer_count"] == 1


def test_validation_rejects_empty_batch_and_timeout() -> None:
    with pytest.raises(ValueError, match="at least one"):
        run_validation(())
    with pytest.raises(ValueError, match="greater than zero"):
        UrlValidator(0)
    with pytest.raises(ValueError, match="greater than zero"):
        ResourceValidator(max_resources_per_source=0)
