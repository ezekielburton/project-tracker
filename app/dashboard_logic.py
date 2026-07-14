"""
app/dashboard_logic.py

Shared computation helpers for the role-based dashboard. Kept separate from
app/routes/dashboard.py (same convention as status_tracking.py / achievements.py)
so this logic is reusable anywhere a project's status needs summarizing.
"""

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
    status_map = {
        'in_queue':              ('designer', 'Check brief and start work, or raise a flag'),
        'in_progress':           ('designer', 'Submit work'),
        'submitted':             ('cs', 'Review work internally'),
        'awaiting_review':       ('cs', 'Follow up for client feedback'),
        'revision_requested':    ('designer', 'Check revision request and start work or flag'),
        're_submitted':          ('cs', 'Review revision'),
        'approved':              ('cs', 'Release files and start production if applicable'),
        'on_hold':               ('cs', 'Unblock project'),
        'awaiting_posm_details': ('cs', 'Add POSM details when available'),
    }
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