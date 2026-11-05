"""工作稿可以未完成，发布完整性、非法连线与URL在服务边界明确校验。"""

import pytest
from pydantic import ValidationError

from app.core.exceptions import AppError
from app.domain.roadmap_policy import publication_issues, require_editable
from app.schemas.roadmap import RoadmapSave


def test_drafts_allow_empty_content_and_optional_minutes_but_publish_locates_missing_content():
    draft = RoadmapSave(
        title="路线",
        expected_version=0,
        stages=[{"id": "tmp_s", "title": "基础", "nodes": [{"id": "tmp_n"}]}],
    )
    assert draft.stages[0].nodes[0].estimated_minutes is None
    assert any(x.get("nodeId") == "tmp_n" for x in publication_issues(draft))


@pytest.mark.parametrize(
    "edges",
    [
        [{"source": "tmp_s", "target": "tmp_s"}],
        [{"source": "tmp_s", "target": "tmp_missing"}],
    ],
)
def test_invalid_edges_rejected(edges):
    with pytest.raises(ValidationError):
        RoadmapSave(title="路线", expected_version=0, stages=[{"id": "tmp_s"}], connections=edges)


@pytest.mark.parametrize("url", ["javascript:alert(1)", "file:///secret", "https://u:p@host/a"])
def test_unsafe_resource_links_rejected(url):
    with pytest.raises(ValidationError):
        RoadmapSave(title="路线", expected_version=0, cover_url=url)


@pytest.mark.parametrize("status,archived", [("disabled", False), ("draft", True)])
def test_locked_states_reject_editing(status, archived):
    with pytest.raises(AppError):
        require_editable(status, archived)


def test_reference_minutes_cannot_exceed_database_integer_range():
    with pytest.raises(ValidationError):
        RoadmapSave(
            title="路线",
            expected_version=0,
            stages=[{"id": "tmp_s", "nodes": [{"id": "tmp_n", "estimatedMinutes": 2147483648}]}],
        )


def test_published_working_copy_remains_editable():
    require_editable("published", False)


def test_publication_still_requires_mainline():
    draft = RoadmapSave(title="路线", expected_version=1)
    issues = publication_issues(draft)
    assert not any(i["field"] == "licenseCode" for i in issues)
    assert any(i["field"] == "stages" for i in issues)


@pytest.mark.parametrize("license_code", ["UNSPECIFIED", "custom"])
def test_publication_does_not_require_license_selection_or_url(license_code):
    draft = RoadmapSave(
        title="路线",
        expected_version=1,
        description="从基础开始学习",
        license_code=license_code,
        stages=[
            {
                "id": "tmp_s",
                "title": "基础",
                "nodes": [
                    {
                        "id": "tmp_n",
                        "title": "变量",
                        "content": "理解变量",
                        "resources": [
                            {
                                "id": "tmp_r",
                                "title": "教程",
                                "resourceType": "article",
                                "resourceUrl": "https://example.com/tutorial",
                            }
                        ],
                    }
                ],
            }
        ],
    )
    assert publication_issues(draft) == []


def test_optional_nodes_cannot_count_toward_progress():
    with pytest.raises(ValidationError):
        RoadmapSave(
            title="路线",
            expected_version=1,
            stages=[{"id": "tmp_s", "nodes": [{"id": "tmp_n", "isOptional": True}]}],
        )
