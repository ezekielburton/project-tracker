# Feature-detail data assembly — everything the detail modal needs to
# render one feature: the 7-stage status row (which stages are behind,
# current, or ahead), the current stage's checklist, and its logged hours.
# Kept separate from routes/features.py the same way board_data.py is kept
# separate from routes/board.py.

from app.modules.digital_innovation.lib.board_data import feature_logged_hours
from app.modules.digital_innovation.models import DI_STAGES, DI_STAGE_LABELS, DI_STAGE_COLOURS


def build_feature_detail_context(feature):
    is_closed = feature.status == 'closed'

    if is_closed:
        # The only path to 'closed' is the Implementation-stage modal (a
        # later chunk), so a closed feature has necessarily passed every
        # stage — the status row shows all 7 as done, and there's no
        # "current stage" checklist to show.
        stage_rows = [
            {'stage': s, 'label': DI_STAGE_LABELS[s], 'colour': DI_STAGE_COLOURS[s], 'state': 'done'}
            for s in DI_STAGES
        ]
        current_stage_label = None
        current_stage_colour = None
        current_steps = []
        steps_done_count = 0
        steps_total_count = 0
        is_last_stage = False
        next_stage_label = None
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
                'label': DI_STAGE_LABELS[stage],
                'colour': DI_STAGE_COLOURS[stage],
                'state': state,
            })

        current_stage_label = DI_STAGE_LABELS[feature.status]
        current_stage_colour = DI_STAGE_COLOURS[feature.status]
        # feature.steps is already sorted by sort_order (models.py's
        # relationship order_by) — same filtering approach as
        # board_data.py's _feature_progress, kept in Python for the same
        # reason: no separate query needed.
        current_steps = [s for s in feature.steps if s.stage == feature.status]
        steps_done_count = sum(1 for s in current_steps if s.is_done)
        steps_total_count = len(current_steps)
        is_last_stage = (current_index == len(DI_STAGES) - 1)
        next_stage_label = None if is_last_stage else DI_STAGE_LABELS[DI_STAGES[current_index + 1]]

    # Row state for the checklist display: done / active (the first
    # unticked step — same "what's next" step board_data.py's
    # _feature_progress already surfaces on the board card) / pending (any
    # other unticked step after it). This is purely a display hint — every
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
        'step_rows': step_rows,
        'steps_done_count': steps_done_count,
        'steps_total_count': steps_total_count,
        'is_last_stage': is_last_stage,
        'next_stage_label': next_stage_label,
        'logged_hours': feature_logged_hours(feature.id),
    }
