# Builds the feature-detail modal's context: the stage status row, the
# move-to-stage options, the current stage's checklist and logged hours.

from app.modules.digital_innovation.lib.board_data import feature_logged_hours
from app.modules.digital_innovation.models import DI_STAGES, DI_STAGE_COLOURS, stage_label


def build_feature_detail_context(feature):
    # Decides the 'management_review' label via stage_label().
    track = feature.project.track
    is_closed = feature.status == 'closed'

    if is_closed:
        # A feature can only be closed from Implementation, so every stage
        # shows as done and there is no current checklist.
        stage_rows = [
            {'stage': s, 'label': stage_label(s, track), 'colour': DI_STAGE_COLOURS[s], 'state': 'done'}
            for s in DI_STAGES
        ]
        current_stage_label = None
        current_stage_colour = None
        current_steps = []
        steps_done_count = 0
        steps_total_count = 0
        is_last_stage = False
    else:
        current_index = DI_STAGES.index(feature.status)
        stage_rows = []
        for i, stage in enumerate(DI_STAGES):
            if i < current_index:
                state = 'done'
            elif i == current_index:
                state = 'current'
            else:
                state = 'future'
            stage_rows.append({
                'stage': stage,
                'label': stage_label(stage, track),
                'colour': DI_STAGE_COLOURS[stage],
                'state': state,
            })

        current_stage_label = stage_label(feature.status, track)
        current_stage_colour = DI_STAGE_COLOURS[feature.status]
        # feature.steps is already ordered by sort_order (relationship order_by).
        current_steps = [s for s in feature.steps if s.stage == feature.status]
        steps_done_count = sum(1 for s in current_steps if s.is_done)
        steps_total_count = len(current_steps)
        is_last_stage = (current_index == len(DI_STAGES) - 1)

    # Every stage is offered: movement has no completion gate. Empty once closed.
    stage_options = [] if is_closed else [
        {'stage': s, 'label': stage_label(s, track)} for s in DI_STAGES
    ]

    # Display state only: done / active (first unticked) / pending. Every
    # current-stage step stays tickable.
    step_rows = []
    active_found = False
    for step in current_steps:
        if step.is_done:
            state = 'done'
        elif not active_found:
            state = 'active'
            active_found = True
        else:
            state = 'pending'
        step_rows.append({'step': step, 'state': state})

    return {
        'is_closed': is_closed,
        'stage_rows': stage_rows,
        'current_stage_label': current_stage_label,
        'current_stage_colour': current_stage_colour,
        'stage_options': stage_options,
        'step_rows': step_rows,
        'steps_done_count': steps_done_count,
        'steps_total_count': steps_total_count,
        'is_last_stage': is_last_stage,
        'logged_hours': feature_logged_hours(feature.id),
    }
