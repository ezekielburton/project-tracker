# Feature-detail data assembly - everything the detail modal needs to
# render one feature: the 8-stage status row (which stages are behind,
# current, or ahead), the move-to-stage picker's options, the current
# stage's checklist, and its logged hours. Kept separate from
# routes/features.py the same way board_data.py is kept separate from
# routes/board.py.

from app.modules.digital_innovation.lib.board_data import feature_logged_hours
from app.modules.digital_innovation.models import DI_STAGES, DI_STAGE_COLOURS, stage_label


def build_feature_detail_context(feature):
    # Board-level, not per-feature (models.py) - decides whether
    # 'management_review' reads as 'Management Review' or 'Client Review'
    # everywhere below, via stage_label().
    track = feature.project.track
    is_closed = feature.status == 'closed'

    if is_closed:
        # The only path to 'closed' is the Implementation-stage modal (a
        # later chunk), so a closed feature has necessarily passed every
        # stage - the status row shows all 8 as done, and there's no
        # "current stage" checklist to show.
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
        # feature.steps is already sorted by sort_order (models.py's
        # relationship order_by) - same filtering approach as
        # board_data.py's _feature_progress, kept in Python for the same
        # reason: no separate query needed.
        current_steps = [s for s in feature.steps if s.stage == feature.status]
        steps_done_count = sum(1 for s in current_steps if s.is_done)
        steps_total_count = len(current_steps)
        is_last_stage = (current_index == len(DI_STAGES) - 1)

    # Move-to-stage picker options - every stage in DI_STAGES, track-aware
    # label, offered regardless of the current stage's completion (see
    # step_engine.move_to_stage: movement is unconstrained, forward or
    # backward, per Ezekiel's confirmed free-movement model). Not shown
    # at all once the feature is closed - there's nowhere to move it.
    stage_options = [] if is_closed else [
        {'stage': s, 'label': stage_label(s, track)} for s in DI_STAGES
    ]

    # Row state for the checklist display: done / active (the first
    # unticked step - same "what's next" step board_data.py's
    # _feature_progress already surfaces on the board card) / pending (any
    # other unticked step after it). This is purely a display hint - every
    # current-stage step stays individually tickable regardless of this,
    # per Ezekiel's "edit steps at any time" rule (step_engine.py).
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
