"""
app/dashboard_logic.py

Shared computation helpers for the role-based dashboard. Kept separate from
app/routes/dashboard.py (same convention as status_tracking.py / achievements.py)
so this logic is reusable anywhere a project's status needs summarizing.
"""

# Project-level statuses where the underlying deliverables/channels can
# genuinely be at different real-world stages from one another — 'briefed'
# (nothing started), 'on_hold', 'approved', 'handed_to_production',
# 'awaiting_posm_details' and friends are all effectively single-state
# brackets where the project-level value IS the accurate answer already,
# so _deliverable_level_action() below only ever runs inside this set.
# C&CM projects only ever sit in 'in_progress' while their channels are
# actually moving (see needs_client_approval()'s docstring for why
# 'submitted_to_client'/'revision_in_queue' never appear at the project
# level for C&CM) — 'in_progress' alone still covers them correctly here.
_ACTIVE_PROJECT_STATUSES = {'in_progress', 'submitted_to_client', 'revision_in_queue'}

# Ordered most- to least-urgent — the FIRST raw status from this list that
# shows up anywhere among a project's deliverables (Standard) or channels
# + concept/kv (C&CM) wins and becomes the project's one Next Action.
# 'approved'/'handed_to_production' are deliberately excluded — those
# contribute no signal here, same as they mean "nothing to do" at the
# project level. Guidance text reuses status_map's own wording below so
# the two never drift into saying the same thing two different ways.
_DELIVERABLE_PRIORITY = [
    ('internal_review',     ('cs', 'Check Internal Submission')),
    ('internal_revision',   ('designer', 'Address internal revision and resubmit')),
    ('revision_in_queue',   ('designer', 'Check client revision request and start work, or raise a flag')),
    ('in_queue',            ('designer', 'Check brief and start work, or raise a flag')),
    ('submitted_to_client', ('cs', 'Follow up with client')),
]


def _deliverable_level_action(project):
    """
    Added M10 (20 Aug 2026), per Ezekiel: the dashboard should keep
    showing exactly ONE next action per project (never enumerate
    deliverables in the UI — "that would make the dashboard pointless"),
    but that one action was silently computed from project.project_status
    alone, which doesn't move once a project is actively being worked —
    two deliverables could be in revision and one already back with the
    client and the project would still show whatever generic guidance
    project_status.get() gave it. This picks the single most urgent real
    signal from the actual deliverables/channels instead, still returning
    exactly one (role, guidance) pair — the UI doesn't change, only which
    one thing it's told to show.

    Returns None (meaning: use the plain status_map lookup instead) when
    project.project_status isn't in _ACTIVE_PROJECT_STATUSES, or when none
    of _DELIVERABLE_PRIORITY's tracked raw statuses appear anywhere on the
    project (e.g. every deliverable is already 'approved') — both cases
    mean the existing project-level guidance is already the right answer.
    """
    if project.project_status not in _ACTIVE_PROJECT_STATUSES:
        return None

    if project.brief_type == 'ccm':
        # Channels + Concept & KV — C&CM's real per-scope progress never
        # lives on project.project_status itself (see needs_client_
        # approval()'s docstring), so this is the ONLY place that signal
        # comes from for a C&CM project's Next Action.
        raw_statuses = {c.status for c in project.posm_channels}
        if project.has_concept and project.concept_status:
            raw_statuses.add(project.concept_status)
        if project.has_kv and project.kv_status:
            raw_statuses.add(project.kv_status)
    else:
        raw_statuses = {d.status for d in project.project_deliverables}

    for raw_status, action in _DELIVERABLE_PRIORITY:
        if raw_status in raw_statuses:
            return action
    return None


def needs_client_approval(project):
    """
    Added M10 (20 Aug 2026) for the Pending Approval dashboard card,
    replacing a flat `project.project_status == 'submitted_to_client'`
    filter that only ever matched Standard briefs. Traced through
    overlay_submissions_draft_submit_to_client (project_overlay.py): its
    POSM-channel branch sets channel.status = 'submitted_to_client' and
    its C&CM Concept & KV branch sets project.concept_status/kv_status —
    record_project_status(project, 'submitted_to_client', ...) is only
    ever called from the Standard-brief branch. So a C&CM project with
    every channel sitting with the client never had project.project_status
    move at all, and the old filter silently never surfaced it here.
    """
    if project.brief_type == 'ccm':
        if any(c.status == 'submitted_to_client' for c in project.posm_channels):
            return True
        if project.has_concept and project.concept_status == 'submitted_to_client':
            return True
        if project.has_kv and project.kv_status == 'submitted_to_client':
            return True
        return False
    return project.project_status == 'submitted_to_client'


def get_next_action_owner(project):
    """
    Returns {'user': ..., 'role': <str>, 'guidance': <str>}.

    'user' is polymorphic:
      - None         — nobody assigned yet
      - a User       — one specific person (CS lead, lead designer, concept/kv designer)
      - a list[User] — every designer assigned to the specific deliverable a
                        flag was raised against (one assignee per team, e.g. 3D + Technical)

    Open flags take priority over status — someone actively blocked on a
    reply matters more than the project's normal workflow stage.
    """
    open_flags = [f for f in project.brief_flags if not f.is_resolved]

    if open_flags:
        # Oldest first — the longest-blocked flag drives whose turn it is.
        flag = min(open_flags, key=lambda f: f.created_at)

        # create_flag() always adds an initial BriefFlagMessage, so messages
        # is never actually empty in practice — flag.created_by is a defensive
        # fallback only, in case a flag is ever created some other way.
        last_author = flag.messages[-1].author if flag.messages else flag.created_by
        cs_roles = ('cs', 'admin', 'management')

        if last_author.role in cs_roles:
            # CS spoke last — designer's turn. Distinguish "CS just raised
            # this" (exactly one message, the initial one) from "CS replied
            # after the designer responded" (more than one).
            is_first_message = len(flag.messages) <= 1
            guidance = 'Review flag and adjust work' if is_first_message else 'Review response and resolve or reply'

            if flag.flag_type == 'deliverable' and flag.deliverable:
                designers = [a.designer for a in flag.deliverable.disciplines]
                user = designers or None
            elif flag.flag_type == 'concept':
                user = project.concept_designer
            elif flag.flag_type == 'kv':
                user = project.kv_designer
            else:  # 'project' — no single deliverable to point at
                user = project.lead_designer

            return {'user': user, 'role': 'designer', 'guidance': guidance}

        # Designer (or team lead) spoke last — CS's turn.
        return {'user': project.cs_lead, 'role': 'cs', 'guidance': 'Review flag and provide information'}

    # No open flags — fall back to status.
    #
    # REBUILT 15 Jul 2026, per Ezekiel: "If a project is in internal review -
    # the next action across all sections should show 'Check Internal
    # Submission'. If a project is in submitted to client status, the next
    # action should show 'Follow up with client'." While making that change,
    # audited this whole map against the ACTUAL current project_status
    # values (VALID list in projects_detail.py's set_project_status route:
    # briefed, in_queue, in_progress, submitted, internal_review,
    # internal_revision, submitted_to_client, revision_in_queue,
    # revision_in_progress, approved, on_hold, awaiting_posm_details) and
    # found this map was built for an OLDER status scheme (awaiting_review /
    # revision_requested / re_submitted — none of which are in the current
    # VALID list at all) that had drifted out of sync with the real
    # submission flow (see the "Project Submission Routes" flow comment
    # above upload_submission() in projects_detail.py, and the
    # record_project_status() call sites across projects_submission.py /
    # projects_detail.py / projects_approval.py). Any project sitting in
    # 'briefed', 'internal_revision', 'revision_in_queue', or
    # 'revision_in_progress' was silently falling through to the generic
    # ('cs', 'Check project status') default below — confirmed via grep that
    # none of those four ever matched a status_map key before this rebuild.
    # 'in_queue', 'submitted', 'internal_review', 'internal_revision',
    # 'revision_in_progress', and 'awaiting_posm_details' are no longer SET
    # anywhere in live code (confirmed again at M10 cutover, 20 Aug 2026 —
    # grepped every record_project_status() call site across the current
    # codebase and found none of these six as a literal argument). The
    # "still reachable via a manual admin status-dropdown override" escape
    # hatch this comment used to cite is itself gone now — that was
    # projects_detail.py's set_project_status route, deleted whole with the
    # old detail page (M10 task #4); there is no surviving way to write an
    # arbitrary project_status value anymore, only the fixed literals each
    # overlay route passes to record_project_status(). So these six are
    # fully unreachable through any live code path today — kept anyway,
    # defensively, purely for pre-M10 historical rows that may still sit at
    # one of these raw values in the database, so a lookup against old data
    # doesn't fall back to the generic default either.
    #
    # 'handed_to_production' added 18 Aug 2026 — a real status now (see
    # project_preproduction.py's _cascade_handed_to_production), and was
    # falling through to the generic default same as the four above before
    # this rebuild did. Dashboard bug fix same day: this status is now
    # also excluded from every "active work" list (_scoped_projects et al
    # in dashboard.py) same as 'approved', so in practice this entry only
    # matters for the active_only=False call sites (e.g. what-changed)
    # that still look a handed-off project's guidance up.
    #
    # 'pre_production' added at M10 cutover (20 Aug 2026) to match
    # app/status_vocabulary.py's own 'kept here for completeness in case
    # that changes' branch for the same raw value — not written anywhere as
    # a real project_status today (Standard projects surface Pre-Production
    # per-deliverable instead, via _post_approval_deliverable_status), so
    # this entry is forward-looking only, same reasoning as the six above.
    status_map = {
        'briefed':               ('designer', 'Start the project'),  # start-project route requires 'briefed' + a requested-team designer/team_lead (or admin) to fire it
        'in_queue':              ('designer', 'Check brief and start work, or raise a flag'),
        'in_progress':           ('designer', 'Submit work'),
        'submitted':             ('cs', 'Review work internally'),
        'internal_review':       ('cs', 'Check Internal Submission'),
        'internal_revision':     ('designer', 'Address internal revision and resubmit'),
        'submitted_to_client':   ('cs', 'Follow up with client'),
        'revision_in_queue':     ('designer', 'Check client revision request and start work, or raise a flag'),
        'revision_in_progress':  ('designer', 'Submit revised work'),
        'approved':              ('cs', 'Release files and start production if applicable'),
        'handed_to_production':  ('cs', 'No action needed — handed to production'),
        'pre_production':        ('cs', 'No action needed — in pre-production'),
        'on_hold':               ('cs', 'Unblock project'),
        'awaiting_posm_details': ('cs', 'Add POSM details when available'),
    }
    # Deliverable/channel-level signal takes precedence when there is one —
    # see _deliverable_level_action()'s docstring above. Falls back to the
    # plain project-level lookup exactly as before when it returns None.
    deliverable_action = _deliverable_level_action(project)
    if deliverable_action is not None:
        role, guidance = deliverable_action
    else:
        role, guidance = status_map.get(project.project_status, ('cs', 'Check project status'))

    if role == 'designer':
        # C&CM projects still in the concept/KV phase: point at whichever of
        # concept_designer/kv_designer is actually set. Otherwise (standard
        # briefs, or C&CM past concept/KV) there's no single deliverable in
        # play at the whole-project level, so fall back to lead_designer —
        # same "project level = lead designer" rule you gave for flags.
        if project.brief_type == 'ccm' and (project.has_concept or project.has_kv):
            designers = [d for d in (project.concept_designer, project.kv_designer) if d]
            user = designers or project.lead_designer
        else:
            user = project.lead_designer
    else:
        user = project.cs_lead

    return {'user': user, 'role': role, 'guidance': guidance}


def guidance_for_viewer(owner_info, viewer):
    """
    Returns the "Next Action" text a specific VIEWER should see for a
    project — not necessarily the same text get_next_action_owner()
    returned, which is role-neutral (it just answers "whose turn is it and
    what should they do", regardless of who's looking at it).

    Added 15 Jul 2026, per Ezekiel: "for designers and team leads, they
    dont need to see the next action that is only for client servicing
    (e.g follow up with client) it should show no action required." A
    CS-role action — 'Follow up with client', 'Check Internal Submission',
    'Release files and start production if applicable', 'Unblock project',
    'Add POSM details when available', 'Review work internally', or the
    flag-reply guidance 'Review flag and provide information' — isn't
    something a designer/team lead can act on no matter which specific
    project it's attached to, so it's replaced with a flat "No action
    required" for that viewer. CS/management/admin viewers (and a
    designer/team-lead viewer looking at a project where the action IS
    theirs, i.e. owner_info['role'] == 'designer') see the real guidance
    unchanged.

    `viewer` is whatever `user` a card's compute function was called with
    (the scope_user — see _resolve_dashboard_scope() in dashboard.py) so
    this correctly reflects what a previewed CS/designer tab would show
    too, not just the real logged-in user.
    """
    if viewer.role in ('designer', 'team_lead') and owner_info['role'] == 'cs':
        return 'No action required'
    return owner_info['guidance']


def nearest_deadline(project):
    """
    The single deadline get_project_rag() and the dashboard's due/overdue
    counts both key off. Extracted into its own function (rather than left
    inline inside get_project_rag) because /dashboard/api/summary needs the
    exact same "which deadline counts" answer to bucket projects into
    due-today / due-this-week / overdue — duplicating the rule in two places
    would risk them drifting apart later. Returns a date, or None if the
    project has nothing to point at.

    Standard projects: nearest Deliverable.design_deadline, falling back to
    project.execution_date (the "Final Deadline" field in the UI — it's
    stored on execution_date, there's no column literally named final_deadline)
    if no deliverable has a deadline set.

    C&CM projects: nearest ProjectCustomer.design_deadline among customers
    that are still pending (not cancelled, not yet approved). Deliberately
    does NOT fall back to execution_date, per spec. NOTE: Gulf countries
    (Kuwait/Qatar/Bahrain/Oman) are tracked at the channel level
    (ProjectPosmChannel), which has no deadline field today — a Gulf-only
    C&CM project with no UAE customers will always return None here until
    that's added.
    """
    if project.brief_type == 'ccm':
        candidates = [
            pc.design_deadline for pc in project.project_customers
            if pc.design_deadline and not pc.cancelled and pc.status != 'approved'
        ]
    else:
        candidates = [d.design_deadline for d in project.project_deliverables if d.design_deadline]
        if not candidates and project.execution_date:
            candidates = [project.execution_date]

    return min(candidates) if candidates else None


def rag_for_deadline(deadline):
    """
    Shared RAG (red/yellow/green) threshold logic, keyed off a single date.
    Red = due today or overdue, Yellow = due within 2 calendar days,
    Green = 3+ days away or no deadline at all.

    Factored out of get_project_rag() below so anything needing a RAG
    colour based on ONE specific deadline (rather than a whole project's
    nearest deadline) can reuse the exact same thresholds instead of
    re-deriving them separately and risking the two drifting apart. (Originally
    factored out for the dashboard's deep-dive zone, since removed 13 Jul
    2026 — see CLAUDE.md; kept as its own function since other callers may
    still want it.)
    """
    from datetime import date

    if deadline is None:
        return 'green'

    days_out = (deadline - date.today()).days

    if days_out <= 0:
        return 'red'
    elif days_out <= 2:
        return 'yellow'
    return 'green'


def get_project_rag(project):
    """
    Returns 'red', 'yellow', or 'green' based on nearest_deadline(project).
    See rag_for_deadline() above for the actual threshold logic — this is
    now just "the whole-project deadline, run through the shared rule".
    """
    return rag_for_deadline(nearest_deadline(project))


def _clash_severity(deliverables):
    """
    Classifies a same-designer, same-day group of 2+ deliverables (added
    10 Jul 2026, per Ezekiel's exact rule):

    'clash'     — a real, certain conflict: the group spans MORE THAN ONE
                  PROJECT (a designer can't split themselves across two
                  different projects' client-facing work on the same day,
                  no matter what time either is actually due), OR every
                  deliverable is on the SAME project AND shares the exact
                  same design_deadline_time.
    'potential' — everything else: same project, same day, but different
                  (or missing/unset) times. This MIGHT be fine depending on
                  how much daylight sits between the two times, so it's
                  flagged as worth a second look rather than a certain
                  conflict — deliberately NOT treated as equal to 'clash'.

    A missing time on either side counts as "not the same time" (falls
    through to 'potential') rather than being treated as a match — no time
    set isn't evidence the two ARE at the same time, it's just unknown, and
    a false "clash" is worse than a false "potential" here (the whole point
    of the two-tier system is not crying wolf on every same-day pairing).
    """
    project_ids = {d.project_id for d in deliverables}
    if len(project_ids) > 1:
        return 'clash'

    times = {d.design_deadline_time for d in deliverables}
    if len(times) == 1 and None not in times:
        return 'clash'

    return 'potential'


def compute_clashes(projects):
    """
    Two designers can be double-booked two ways:
      by_deliverable — same designer assigned (via DeliverableAssignment) to
                        2+ deliverables due the same day. Each group also
                        carries a 'severity' — see _clash_severity() above —
                        distinguishing a certain 'clash' from a same-project,
                        different-time 'potential' one.
      by_project     — same designer assigned (via ProjectDesigner) to 2+
                        projects sharing the same Final Deadline (execution_date).
                        No severity split here — execution_date has no time
                        component at all, so there's no "same time" case to
                        distinguish a potential clash from a real one; every
                        group here is treated as a real clash.

    `projects` is whatever list the caller already scoped by role — this
    function doesn't do its own querying, so the same result is reusable by
    both /dashboard/api/summary (which only needs the counts) and
    /dashboard/api/clashes (which needs the full breakdown).
    """
    from collections import defaultdict

    deliverable_groups = defaultdict(list)
    for p in projects:
        for d in p.project_deliverables:
            if not d.design_deadline:
                continue
            # set(), not a plain loop over d.disciplines — a designer can be
            # assigned to this ONE deliverable under two different teams
            # (DeliverableAssignment is upserted by (deliverable_id, team),
            # not (deliverable_id, designer_id) — see assign_deliverable() in
            # projects_detail.py), which would otherwise append the SAME
            # deliverable into this designer's bucket twice and make it look
            # like it's clashing with itself. Same failure mode the
            # by_project grouping below already guards against with its own
            # set() — this dedupe was missing here (found during the UI
            # verification pass, Chunk 10).
            designer_ids = {a.designer_id for a in d.disciplines}
            for designer_id in designer_ids:
                deliverable_groups[(designer_id, d.design_deadline)].append(d)

    by_deliverable = [
        {
            'designer_id': designer_id,
            'date': dl_date,
            'deliverables': deliverables,
            'severity': _clash_severity(deliverables),
        }
        for (designer_id, dl_date), deliverables in deliverable_groups.items()
        if len(deliverables) > 1
    ]

    # set(), not list() — a designer assigned to the same project under two
    # different teams (two separate ProjectDesigner rows) must not look like
    # two different projects clashing with themselves.
    project_groups = defaultdict(set)
    for p in projects:
        if not p.execution_date:
            continue
        for pd in p.assigned_designers:
            project_groups[(pd.user_id, p.execution_date)].add(p)

    by_project = [
        {'designer_id': designer_id, 'date': dl_date, 'projects': list(plist)}
        for (designer_id, dl_date), plist in project_groups.items()
        if len(plist) > 1
    ]

    return {'by_deliverable': by_deliverable, 'by_project': by_project}