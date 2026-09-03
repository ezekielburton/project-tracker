"""Coverage for the small pure helpers models.py added alongside the
revision stage and internal/external track: DI_STAGES/DI_STAGE_LABELS
picking up 'revision', DI_PROJECT_TRACKS, and stage_label() - the
internal-vs-external relabeling used everywhere a stage name is shown
(board.py, feature_detail.py, snapshots.py)."""
from app.modules.digital_innovation.models import (
    DI_STAGES, DI_STAGE_LABELS, DI_PROJECT_TRACKS, stage_label,
)


def test_di_stages_includes_revision_between_management_review_and_implementation():
    assert 'revision' in DI_STAGES
    review_index = DI_STAGES.index('management_review')
    revision_index = DI_STAGES.index('revision')
    implementation_index = DI_STAGES.index('implementation')
    assert revision_index == review_index + 1
    assert implementation_index == revision_index + 1


def test_di_stages_has_eight_stages_each_with_a_label():
    assert len(DI_STAGES) == 8
    for stage in DI_STAGES:
        assert stage in DI_STAGE_LABELS


def test_di_project_tracks_is_internal_and_external():
    assert DI_PROJECT_TRACKS == ('internal', 'external')


def test_stage_label_relabels_management_review_for_an_external_track():
    assert stage_label('management_review', 'external') == 'Client Review'


def test_stage_label_keeps_management_review_for_an_internal_track():
    assert stage_label('management_review', 'internal') == 'Management Review'


def test_stage_label_defaults_to_internal_when_no_track_given():
    assert stage_label('management_review') == 'Management Review'


def test_stage_label_passes_through_every_other_stage_regardless_of_track():
    for stage in DI_STAGES:
        if stage == 'management_review':
            continue
        assert stage_label(stage, 'external') == DI_STAGE_LABELS[stage]
        assert stage_label(stage, 'internal') == DI_STAGE_LABELS[stage]
