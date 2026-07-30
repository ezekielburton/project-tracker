from app import db
from app.models import Notification, User, ProjectSecondaryCS, ProjectSecondaryCsRegion


# ── Private helpers ───────────────────────────────────────────────────────────

def _get_secondary_cs(project):
    """Return all secondary CS User objects for a project."""
    return [a.user for a in ProjectSecondaryCS.query.filter_by(project_id=project.id).all()]


def _secondary_cs_subscribed_to_region(project, user, region):
    """
    Return True if this secondary CS should receive notifications for the given region.
    Logic: if they have NO region preferences set → receive all regions.
            if they have preferences set → only receive for subscribed regions.
    """
    subs = ProjectSecondaryCsRegion.query.filter_by(project_id=project.id, user_id=user.id).all()
    if not subs:
        return True  # No filter set — receive everything
    return any(s.region == region for s in subs)


def _deliverable_region(deliverable):
    """Get the region of a C&CM deliverable via its project_customer → customer chain."""
    if deliverable and deliverable.project_customer and deliverable.project_customer.customer:
        return deliverable.project_customer.customer.region
    return None


def _get_project_designers(project):
    """
    Return all unique User objects assigned to any deliverable on this project,
    plus the concept and KV designers if set.
    Used by notify_of_submission_to_client and notify_of_project_approved.
    """
    seen_ids = set()
    designers = []

    # Assignments made via the chip-assign system (DeliverableAssignment rows)
    for deliverable in project.project_deliverables:
        for assignment in deliverable.disciplines:
            if assignment.designer_id not in seen_ids:
                seen_ids.add(assignment.designer_id)
                designers.append(assignment.designer)

    # Concept / KV designers set on the project itself (C&CM flow)
    for user in [project.concept_designer, project.kv_designer]:
        if user and user.id not in seen_ids:
            seen_ids.add(user.id)
            designers.append(user)

    return designers


def _send_notification_email(recipient, message, project=None):
    """
    Send an HTML email alongside an in-app notification.
    Silently does nothing if email is disabled or misconfigured.
    """
    from flask import current_app
    # If email is turned off in .env, skip silently
    if str(current_app.config.get('MAIL_ENABLED', 'false')).lower() != 'true':
        return
    # If the user has no email address, skip
    if not recipient.email:
        return
    try:
        from flask_mail import Message as MailMessage
        from app import mail

        # Build the URL — link directly to the project if one is attached
        app_url = 'https://app.vitamin-e.work'
        if project:
            button_url = f'{app_url}/projects/{project.id}'
        else:
            button_url = app_url

        project_line = f'<p style="margin:0 0 12px;color:#555555;font-size:14px;"><strong>Project:</strong> {project.name}</p>' if project else ''

        # HTML email body — inline styles required for email client compatibility
        html_body = f"""
        <table width="100%" cellpadding="0" cellspacing="0" border="0"
               style="background-color:#F5F0E8;">
            <tr>
                <td align="center" style="padding:48px 20px;">

                    <table width="520" cellpadding="0" cellspacing="0" border="0"
                           style="max-width:520px;width:100%;background-color:#ffffff;
                                  border-radius:12px;overflow:hidden;">

                        <!-- Wordmark row -->
                        <tr>
                            <td style="padding:28px 36px 0 36px;">
                                <table width="100%" cellpadding="0" cellspacing="0" border="0">
                                    <tr>
                                        <td>
                                            <span style="font-family:Arial,sans-serif;
                                                         font-size:11px;font-weight:bold;
                                                         letter-spacing:3px;color:#F27F55;
                                                         text-transform:uppercase;">
                                                VITAMIN-E
                                            </span>
                                        </td>
                                        <td align="right"></td>
                                    </tr>
                                </table>
                                <!-- Tangerine rule -->
                                <table width="100%" cellpadding="0" cellspacing="0" border="0"
                                       style="margin-top:14px;">
                                    <tr>
                                        <td style="height:2px;background-color:#F27F55;
                                                   font-size:0;line-height:0;">&nbsp;</td>
                                    </tr>
                                </table>
                            </td>
                        </tr>

                        <!-- Body -->
                        <tr>
                            <td style="padding:32px 36px 28px 36px;">
                                <p style="margin:0 0 6px;font-family:Arial,sans-serif;
                                          font-size:11px;color:#bbb;letter-spacing:2px;
                                          text-transform:uppercase;">
                                    Notification
                                </p>
                                <p style="margin:0 0 20px;font-family:Arial,sans-serif;
                                          font-size:17px;font-weight:bold;color:#1A1A1A;">
                                    Hi {recipient.name},
                                </p>
                                <p style="margin:0 0 24px;font-family:Arial,sans-serif;
                                          font-size:15px;line-height:1.7;color:#444444;">
                                    {message}
                                </p>
                                {project_line}
                                <!-- CTA button -->
                                <table cellpadding="0" cellspacing="0" border="0"
                                       style="margin-top:8px;">
                                    <tr>
                                        <td style="background-color:#F27F55;border-radius:6px;">
                                            <a href="{button_url}"
                                               style="display:inline-block;padding:12px 28px;
                                                      color:#ffffff;text-decoration:none;
                                                      font-family:Arial,sans-serif;
                                                      font-size:14px;font-weight:bold;
                                                      letter-spacing:0.5px;">
                                                Open in Vitamin-E &rarr;
                                            </a>
                                        </td>
                                    </tr>
                                </table>
                            </td>
                        </tr>

                        <!-- Footer -->
                        <tr>
                            <td style="background-color:#F5F0E8;padding:18px 36px;
                                       border-top:1px solid #ebe5d8;">
                                <p style="margin:0;font-family:Arial,sans-serif;
                                          font-size:11px;color:#aaa;line-height:1.7;">
                                    You are receiving this because you have notifications
                                    enabled for Vitamin-E.<br>
                                    Manage your preferences at
                                    <a href="{app_url}/account"
                                       style="color:#F27F55;text-decoration:none;">
                                        app.vitamin-e.work
                                    </a>
                                </p>
                            </td>
                        </tr>

                    </table>
                </td>
            </tr>
        </table>
        """

        # Plain text fallback for email clients that don't render HTML
        text_body = f"Hi {recipient.name},\n\n{message}"
        if project:
            text_body += f"\nProject: {project.name}"
        text_body += f"\n\nOpen Vitamin-E: {button_url}\n\n— Vitamin-E"

        msg = MailMessage(
            subject=f'[Vitamin-E] {message[:60]}{"..." if len(message) > 60 else ""}',
            recipients=[recipient.email],
            body=text_body,
            html=html_body
        )
        mail.send(msg)

    except Exception as e:
        current_app.logger.warning(f'Vitamin-E email notification failed for {recipient.email}: {e}')


# ── Core factory ──────────────────────────────────────────────────────────────

def create_notification(recipient, message, notification_type, project=None,
                        triggered_by=None, pref_key=None, link=None,
                        send_email=True):
    """
    Create a single in-app notification and (optionally) send an email.

    pref_key  — the key to check against recipient.notification_prefs before
                sending the email. If None, email always fires (backwards-
                compatible for calls that predate the preference system).
                In-app notification is ALWAYS created regardless of pref.
    send_email — set to False to suppress the email entirely, regardless of
                 pref_key. Use when a separate direct email has already been
                 sent for the same event (e.g. notify_admin_of_new_feedback)
                 to avoid duplicates. In-app notification is still created.
    """
    notification = Notification(
        recipient_id=recipient.id,
        message=message,
        notification_type=notification_type,
        project_id=project.id if project else None,
        triggered_by_id=triggered_by.id if triggered_by else None,
        link=link
    )
    db.session.add(notification)
    db.session.commit()

    # Gate the email on the user's saved preference for this type.
    # Missing pref_key (legacy callers) → always send.
    # send_email=False → always skip (caller already sent a direct email).
    if send_email and (pref_key is None or recipient.wants_notification(pref_key)):
        _send_notification_email(recipient, message, project)

    return notification


# ── Notify functions ──────────────────────────────────────────────────────────

def notify_team_leads_of_new_project(project, teams_requested, triggered_by):
    """
    Notify ALL members of every team requested on a new project — both team leads and designers.
    teams_requested is a list like ['3D', '2D'].
    Team leads get a message prompting them to assign designers.
    Designers get a heads-up that a new project is coming in for their team.
    """
    for team_name in teams_requested:
        # Notify team leads — they need to action this by assigning designers
        team_leads = User.query.filter_by(role='team_lead', team=team_name).all()
        for team_lead in team_leads:
            create_notification(
                recipient=team_lead,
                message=f'A new project has come in for the {team_name} team: "{project.name}".',
                notification_type='project_created',
                project=project,
                triggered_by=triggered_by,
                pref_key='new_project'
            )

        # Notify all designers on this team — so they're aware before assignment
        designers = User.query.filter_by(role='designer', team=team_name).all()
        for designer in designers:
            create_notification(
                recipient=designer,
                message=f'A new project has come in for the {team_name} team: "{project.name}".',
                notification_type='project_created',
                project=project,
                triggered_by=triggered_by,
                pref_key='new_project'
            )


def notify_cs_of_brief_flag(flag, project, triggered_by):
    """Notify the CS lead and secondary CS that a designer has raised a brief flag."""
    type_label = {'project': 'the project', 'concept': 'the concept', 'kv': 'the KV'}.get(
        flag.flag_type,
        f'a deliverable' if not flag.deliverable else f'"{flag.deliverable.name}"'
    )
    message = f'{triggered_by.name} flagged an issue on {type_label} in "{project.name}".'

    cs_lead = User.query.get(project.cs_lead_id)
    if cs_lead:
        create_notification(recipient=cs_lead, message=message, notification_type='brief_flag',
                            project=project, triggered_by=triggered_by,
                            pref_key='brief_flag')

    # Notify secondary CS, with region filtering for C&CM deliverable-level flags
    region = _deliverable_region(flag.deliverable) if flag.flag_type == 'deliverable' else None
    for secondary in _get_secondary_cs(project):
        if region and project.brief_type == 'ccm':
            if not _secondary_cs_subscribed_to_region(project, secondary, region):
                continue
        create_notification(recipient=secondary, message=message, notification_type='brief_flag',
                            project=project, triggered_by=triggered_by,
                            pref_key='brief_flag')


def notify_flag_reply(flag, project, triggered_by):
    """
    Notify the relevant party that a reply has been added to a flag.
    If CS replied → notify the original flagging designer.
    If designer replied → notify the CS lead.
    """
    if triggered_by.id == flag.created_by_id:
        # Designer replied — notify CS
        recipient = User.query.get(project.cs_lead_id)
        message = f'{triggered_by.name} replied to their flag on "{project.name}".'
    else:
        # CS/admin replied — notify the original flagging designer
        recipient = flag.created_by
        message = f'{triggered_by.name} responded to your flag on "{project.name}".'

    if recipient:
        create_notification(
            recipient=recipient,
            message=message,
            notification_type='brief_flag_reply',
            project=project,
            triggered_by=triggered_by,
            pref_key='flag_reply'
        )


def notify_designers_of_revision_flag(deliverable, project, triggered_by):
    """
    Notify all designers assigned to a deliverable that it has been flagged for revision.
    Uses deliverable.disciplines (DeliverableAssignment records) to find who to notify.
    """
    notified_ids = set()
    for assignment in deliverable.disciplines:
        if assignment.designer_id not in notified_ids:
            message = f'"{deliverable.name}" on "{project.name}" has been flagged for revision.'
            create_notification(
                recipient=assignment.designer,
                message=message,
                notification_type='revision_flagged',
                project=project,
                triggered_by=triggered_by,
                pref_key='revision_flag'
            )
            notified_ids.add(assignment.designer_id)


def notify_cs_of_revision_submitted(project, triggered_by):
    """Notify the CS lead and secondary CS that all flagged revisions have been submitted."""
    message = f'All flagged revisions on "{project.name}" have been submitted. (Revision #{project.revision_count})'
    cs_lead = User.query.get(project.cs_lead_id)
    if cs_lead:
        create_notification(recipient=cs_lead, message=message, notification_type='revision_submitted',
                            project=project, triggered_by=triggered_by,
                            pref_key='revision_submitted')
    for secondary in _get_secondary_cs(project):
        create_notification(recipient=secondary, message=message, notification_type='revision_submitted',
                            project=project, triggered_by=triggered_by,
                            pref_key='revision_submitted')


def notify_cs_lead_of_assignment(project, designer, team_name, triggered_by):
    """
    Notify the CS lead of a project when a designer has been assigned to a team.
    No pref_key — this is a core operational alert that always fires.
    """
    cs_lead = User.query.get(project.cs_lead_id)
    if cs_lead:
        message = f"{designer.name} has been assigned to the {team_name} team on project: {project.name}"
        create_notification(
            recipient=cs_lead,
            message=message,
            notification_type='designer_assigned',
            project=project,
            triggered_by=triggered_by
            # pref_key intentionally omitted → always sends
        )


def notify_designer_of_concept_kv_assignment(project, designer, role_label, triggered_by):
    """
    Notify a designer that they have been assigned the Concept or KV role on a project.
    role_label: 'Concept' or 'Key Visual'
    """
    message = f'You have been assigned as the {role_label} designer on "{project.name}".'
    create_notification(
        recipient=designer,
        message=message,
        notification_type='designer_assigned',
        project=project,
        triggered_by=triggered_by,
        pref_key='concept_kv_assigned'
    )


def notify_cs_of_flag_resolved(flag, project, triggered_by):
    """Notify the CS lead and secondary CS when the designer marks a brief flag as resolved."""
    type_label = {'project': 'the project', 'concept': 'the concept', 'kv': 'the KV'}.get(
        flag.flag_type,
        f'"{flag.deliverable.name}"' if flag.deliverable else 'a deliverable'
    )
    message = f'{triggered_by.name} marked their flag on {type_label} in "{project.name}" as resolved.'
    cs_lead = User.query.get(project.cs_lead_id)
    if cs_lead:
        create_notification(recipient=cs_lead, message=message, notification_type='brief_flag_resolved',
                            project=project, triggered_by=triggered_by,
                            pref_key='flag_resolved')

    region = _deliverable_region(flag.deliverable) if flag.flag_type == 'deliverable' else None
    for secondary in _get_secondary_cs(project):
        if region and project.brief_type == 'ccm':
            if not _secondary_cs_subscribed_to_region(project, secondary, region):
                continue
        create_notification(recipient=secondary, message=message, notification_type='brief_flag_resolved',
                            project=project, triggered_by=triggered_by,
                            pref_key='flag_resolved')


def notify_cs_of_lead_change(project, new_designer, team_name, triggered_by, previous_designer=None):
    """
    Notify CS lead + secondary CS when a designer self-assigns or takes over as team lead.
    If previous_designer is provided, also notify them that they've been replaced.
    """
    if previous_designer:
        cs_message = (f'{new_designer.name} has taken over as {team_name} lead on '
                      f'"{project.name}" (previously {previous_designer.name}).')
        prev_message = (f'{new_designer.name} has taken over from you as {team_name} lead '
                        f'on "{project.name}".')
    else:
        cs_message = (f'{new_designer.name} has self-assigned as {team_name} lead '
                      f'on "{project.name}".')

    cs_lead = User.query.get(project.cs_lead_id)
    if cs_lead:
        create_notification(recipient=cs_lead, message=cs_message,
                            notification_type='lead_assigned',
                            project=project, triggered_by=triggered_by,
                            pref_key='lead_changed')
    for secondary in _get_secondary_cs(project):
        create_notification(recipient=secondary, message=cs_message,
                            notification_type='lead_assigned',
                            project=project, triggered_by=triggered_by,
                            pref_key='lead_changed')

    if previous_designer and previous_designer.id != triggered_by.id:
        create_notification(recipient=previous_designer, message=prev_message,
                            notification_type='lead_assigned',
                            project=project, triggered_by=triggered_by,
                            pref_key='lead_changed')


def notify_secondary_cs_of_deliverable_status(deliverable, project, new_status, triggered_by):
    """
    Notify secondary CS of a C&CM deliverable status change, filtered by their region subscriptions.
    Called from set_deliverable_status. Does nothing for standard briefs.
    """
    if project.brief_type != 'ccm':
        return

    secondary_cs = _get_secondary_cs(project)
    if not secondary_cs:
        return

    region = _deliverable_region(deliverable)
    status_label = new_status.replace('_', ' ').title()
    message = f'"{deliverable.name}" in "{project.name}" is now {status_label}.'

    for secondary in secondary_cs:
        if region and not _secondary_cs_subscribed_to_region(project, secondary, region):
            continue
        create_notification(recipient=secondary, message=message, notification_type='status_change',
                            project=project, triggered_by=triggered_by,
                            pref_key='deliverable_status')


def notify_cs_of_project_started(project, triggered_by):
    """Notify CS lead and secondary CS when a designer starts the project."""
    message = f'{triggered_by.name} has started work on "{project.name}".'
    cs_lead = User.query.get(project.cs_lead_id)
    if cs_lead:
        create_notification(recipient=cs_lead, message=message, notification_type='project_started',
                            project=project, triggered_by=triggered_by,
                            pref_key='project_started')
    for secondary in _get_secondary_cs(project):
        create_notification(recipient=secondary, message=message, notification_type='project_started',
                            project=project, triggered_by=triggered_by,
                            pref_key='project_started')


def notify_lead_designers_of_project_started(project, triggered_by):
    """Notify other lead designers (ProjectDesigner records) when a project is started.
    The actor who pressed Start Project is excluded — they already know.
    CS lead is notified separately via notify_cs_of_project_started."""
    from app.models import ProjectDesigner
    message = f'{triggered_by.name} has started work on "{project.name}".'
    leads = ProjectDesigner.query.filter_by(project_id=project.id).all()
    for lead in leads:
        if lead.user_id != triggered_by.id:
            create_notification(
                recipient=lead.designer,
                message=message,
                notification_type='project_started',
                project=project,
                triggered_by=triggered_by,
                pref_key='project_started'
            )


def notify_of_submission_to_client(project, triggered_by):
    """
    Notify the project's CS lead, secondary CS, and assigned designers when CS
    submits a deck to the client. The triggering user is excluded.
    No blanket role broadcast — only people actually on the project receive this.
    """
    message = f'"{project.name}" has been submitted to the client.'

    recipients = []
    recipient_ids = set()

    # CS lead
    if project.cs_lead and project.cs_lead.id not in recipient_ids:
        recipients.append(project.cs_lead)
        recipient_ids.add(project.cs_lead.id)

    # Secondary CS
    for secondary in _get_secondary_cs(project):
        if secondary.id not in recipient_ids:
            recipients.append(secondary)
            recipient_ids.add(secondary.id)

    # Designers assigned to any deliverable on this project
    for designer in _get_project_designers(project):
        if designer.id not in recipient_ids:
            recipients.append(designer)
            recipient_ids.add(designer.id)

    for recipient in recipients:
        if recipient.id == triggered_by.id:
            continue
        create_notification(
            recipient=recipient,
            message=message,
            notification_type='submitted_to_client',
            project=project,
            triggered_by=triggered_by,
            pref_key='project_submitted_client'
        )


def notify_of_ckv_posm_pending(project, triggered_by):
    """
    Notify secondary CS and designers when C&KV is approved on a C&KV-only brief
    and the CS has chosen to add POSM — project is back in progress.
    """
    message = f'"{project.name}" — Concept & KV approved. Project is back in progress to add POSM details.'

    recipients = []
    recipient_ids = set()

    for secondary in _get_secondary_cs(project):
        if secondary.id not in recipient_ids:
            recipients.append(secondary)
            recipient_ids.add(secondary.id)

    for designer in _get_project_designers(project):
        if designer.id not in recipient_ids:
            recipients.append(designer)
            recipient_ids.add(designer.id)

    for recipient in recipients:
        if recipient.id == triggered_by.id:
            continue
        create_notification(
            recipient=recipient,
            message=message,
            notification_type='project_updated',
            project=project,
            triggered_by=triggered_by,
            pref_key='project_updated'
        )


def notify_of_posm_details_added(project, triggered_by):
    """
    Notify the project's assigned designers (project.assigned_designers —
    the ProjectDesigner rows shown in every dashboard's "Assigned Designers"
    column) when CS adds POSM customer details to a project that was paused
    in 'awaiting_posm_details' status (the "Pause" choice from the C&KV-only
    approval prompt — see notify_of_ckv_posm_pending for the sibling "Add
    POSM" choice, which notifies immediately instead of waiting for this).

    Deliberately uses project.assigned_designers rather than
    _get_project_designers() (which is deliverable/concept/kv based) — at
    this point no POSM deliverables have been assigned to anyone yet, so
    that helper would likely return nothing useful. assigned_designers is
    the project-level team assignment made back when the project was first
    briefed, which is who actually needs to know work has resumed.

    Only fires once — see the had_no_customers_before check in
    update_project() (projects_brief.py) that gates the call site. The
    project's status stays 'awaiting_posm_details' after this; a designer
    must explicitly click "Resume" (resume_posm_project route) to move it
    to in_progress, rather than this notification doing it automatically.
    """
    message = f'"{project.name}" — POSM customer details have been added. Resume the project to continue.'

    recipients = []
    recipient_ids = set()
    for assignment in project.assigned_designers:
        designer = assignment.designer
        if designer.id not in recipient_ids:
            recipients.append(designer)
            recipient_ids.add(designer.id)

    for recipient in recipients:
        if recipient.id == triggered_by.id:
            continue
        create_notification(
            recipient=recipient,
            message=message,
            notification_type='project_updated',
            project=project,
            triggered_by=triggered_by,
            pref_key='project_updated'
        )


def notify_of_project_approved(project, triggered_by):
    """
    Notify the project's CS lead, secondary CS, and assigned designers when a
    project reaches full approval. The approving user is excluded.
    No blanket role broadcast — only people actually on the project receive this.
    """
    message = f'"{project.name}" has been approved!'

    recipients = []
    recipient_ids = set()

    # CS lead
    if project.cs_lead and project.cs_lead.id not in recipient_ids:
        recipients.append(project.cs_lead)
        recipient_ids.add(project.cs_lead.id)

    # Secondary CS
    for secondary in _get_secondary_cs(project):
        if secondary.id not in recipient_ids:
            recipients.append(secondary)
            recipient_ids.add(secondary.id)

    # Designers assigned to this project
    for designer in _get_project_designers(project):
        if designer.id not in recipient_ids:
            recipients.append(designer)
            recipient_ids.add(designer.id)

    for recipient in recipients:
        if recipient.id == triggered_by.id:
            continue
        create_notification(
            recipient=recipient,
            message=message,
            notification_type='project_approved',
            project=project,
            triggered_by=triggered_by,
            pref_key='project_approved'
        )


def broadcast_update_email(version, subject_line, intro_line, blog_url):
    """
    Send a one-off update announcement email to every active user.
    Creates an in-app notification AND sends an HTML email to each user.
    Called manually by an admin via /admin/broadcast-update.
    """
    from flask import current_app

    if str(current_app.config.get('MAIL_ENABLED', 'false')).lower() != 'true':
        current_app.logger.warning('broadcast_update_email: MAIL_ENABLED is not true, skipping.')
        return 0

    try:
        from flask_mail import Message as MailMessage
        from app import mail
    except Exception as e:
        current_app.logger.warning(f'broadcast_update_email: mail import failed: {e}')
        return 0

    app_url = 'https://app.vitamin-e.work'
    sent = 0

    users = User.query.all()

    for user in users:
        if not user.email:
            continue

        # ── In-app notification ──────────────────────────────────────
        notif = Notification(
            recipient_id=user.id,
            message=intro_line,
            notification_type='system_update',
        )
        db.session.add(notif)

        # ── HTML email ───────────────────────────────────────────────
        html_body = f"""
        <table width="100%" cellpadding="0" cellspacing="0" border="0"
               style="background-color:#F5F0E8;">
            <tr>
                <td align="center" style="padding:48px 20px;">

                    <table width="520" cellpadding="0" cellspacing="0" border="0"
                           style="max-width:520px;width:100%;background-color:#ffffff;
                                  border-radius:12px;overflow:hidden;">

                        <!-- Wordmark -->
                        <tr>
                            <td style="padding:28px 36px 0 36px;">
                                <table width="100%" cellpadding="0" cellspacing="0" border="0">
                                    <tr>
                                        <td>
                                            <span style="font-family:Arial,sans-serif;
                                                         font-size:11px;font-weight:bold;
                                                         letter-spacing:3px;color:#F27F55;
                                                         text-transform:uppercase;">
                                                VITAMIN-E
                                            </span>
                                        </td>
                                        <td align="right"></td>
                                    </tr>
                                </table>
                                <table width="100%" cellpadding="0" cellspacing="0" border="0"
                                       style="margin-top:14px;">
                                    <tr>
                                        <td style="height:2px;background-color:#F27F55;
                                                   font-size:0;line-height:0;">&nbsp;</td>
                                    </tr>
                                </table>
                            </td>
                        </tr>

                        <!-- Body -->
                        <tr>
                            <td style="padding:32px 36px 28px 36px;">
                                <p style="margin:0 0 6px;font-family:Arial,sans-serif;
                                          font-size:11px;color:#bbb;letter-spacing:2px;
                                          text-transform:uppercase;">
                                    App Update &mdash; {version}
                                </p>
                                <p style="margin:0 0 20px;font-family:Arial,sans-serif;
                                          font-size:17px;font-weight:bold;color:#1A1A1A;">
                                    Hi {user.name},
                                </p>
                                <p style="margin:0 0 24px;font-family:Arial,sans-serif;
                                          font-size:15px;line-height:1.7;color:#444444;">
                                    {intro_line}
                                </p>
                                <p style="margin:0 0 24px;font-family:Arial,sans-serif;
                                          font-size:15px;line-height:1.7;color:#444444;">
                                    Read the full update post to see everything that's new.
                                </p>
                                <table cellpadding="0" cellspacing="0" border="0"
                                       style="margin-top:8px;">
                                    <tr>
                                        <td style="background-color:#F27F55;border-radius:6px;">
                                            <a href="{blog_url}"
                                               style="display:inline-block;padding:12px 28px;
                                                      color:#ffffff;text-decoration:none;
                                                      font-family:Arial,sans-serif;
                                                      font-size:14px;font-weight:bold;
                                                      letter-spacing:0.5px;">
                                                Read the Update &rarr;
                                            </a>
                                        </td>
                                    </tr>
                                </table>
                            </td>
                        </tr>

                        <!-- Footer -->
                        <tr>
                            <td style="background-color:#F5F0E8;padding:18px 36px;
                                       border-top:1px solid #ebe5d8;">
                                <p style="margin:0;font-family:Arial,sans-serif;
                                          font-size:11px;color:#aaa;line-height:1.7;">
                                    You are receiving this because you are a member of
                                    Vitamin-E.<br>
                                    <a href="{app_url}/account"
                                       style="color:#F27F55;text-decoration:none;">
                                        Manage notification preferences
                                    </a>
                                </p>
                            </td>
                        </tr>

                    </table>
                </td>
            </tr>
        </table>
        """

        text_body = (
            f"Hi {user.name},\n\n{intro_line}\n\n"
            f"Read the full update post: {blog_url}\n\n— Vitamin-E"
        )

        try:
            msg = MailMessage(
                subject=subject_line,
                recipients=[user.email],
                body=text_body,
                html=html_body
            )
            mail.send(msg)
            sent += 1
        except Exception as e:
            current_app.logger.warning(f'broadcast_update_email: failed for {user.email}: {e}')

    db.session.commit()
    return sent

def notify_admin_of_new_feedback(item_type, title, submitted_by, url_path):
    """
    Send a direct email to Ezekiel when someone submits a feature request or bug report.
    item_type: 'Feature Request' or 'Bug Report'
    No in-app notification — this is an admin alert only.
    """
    from flask import current_app
    if str(current_app.config.get('MAIL_ENABLED', 'false')).lower() != 'true':
        return

    try:
        from flask_mail import Message as MailMessage
        from app import mail

        app_url   = 'https://app.vitamin-e.work'
        button_url = f'{app_url}{url_path}'

        html_body = f"""
        <table width="100%" cellpadding="0" cellspacing="0" border="0"
               style="background-color:#F5F0E8;">
            <tr><td align="center" style="padding:48px 20px;">
                <table width="520" cellpadding="0" cellspacing="0" border="0"
                       style="max-width:520px;width:100%;background-color:#ffffff;
                              border-radius:12px;overflow:hidden;">
                    <tr><td style="padding:28px 36px 0 36px;">
                        <span style="font-family:Arial,sans-serif;font-size:11px;font-weight:bold;
                                     letter-spacing:3px;color:#F27F55;text-transform:uppercase;">
                            VITAMIN-E
                        </span>
                        <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top:14px;">
                            <tr><td style="height:2px;background-color:#F27F55;font-size:0;line-height:0;">&nbsp;</td></tr>
                        </table>
                    </td></tr>
                    <tr><td style="padding:32px 36px 28px 36px;">
                        <p style="margin:0 0 6px;font-family:Arial,sans-serif;font-size:11px;
                                   color:#bbb;letter-spacing:2px;text-transform:uppercase;">
                            {item_type}
                        </p>
                        <p style="margin:0 0 20px;font-family:Arial,sans-serif;font-size:17px;
                                   font-weight:bold;color:#1A1A1A;">
                            New {item_type}
                        </p>
                        <p style="margin:0 0 8px;font-family:Arial,sans-serif;font-size:15px;
                                   line-height:1.7;color:#444444;">
                            <strong>{submitted_by.name}</strong> submitted a new {item_type.lower()}:
                        </p>
                        <p style="margin:0 0 24px;font-family:Arial,sans-serif;font-size:16px;
                                   font-weight:bold;color:#1A1A1A;">
                            &ldquo;{title}&rdquo;
                        </p>
                        <table cellpadding="0" cellspacing="0" border="0" style="margin-top:8px;">
                            <tr>
                                <td style="background-color:#F27F55;border-radius:6px;">
                                    <a href="{button_url}"
                                       style="display:inline-block;padding:12px 28px;color:#ffffff;
                                              text-decoration:none;font-family:Arial,sans-serif;
                                              font-size:14px;font-weight:bold;letter-spacing:0.5px;">
                                        View in Vitamin-E &rarr;
                                    </a>
                                </td>
                            </tr>
                        </table>
                    </td></tr>
                    <tr><td style="background-color:#F5F0E8;padding:18px 36px;border-top:1px solid #ebe5d8;">
                        <p style="margin:0;font-family:Arial,sans-serif;font-size:11px;color:#aaa;">
                            Vitamin-E &middot; Admin Alert
                        </p>
                    </td></tr>
                </table>
            </td></tr>
        </table>
        """

        text_body = (
            f"New {item_type} from {submitted_by.name}:\n\n"
            f'"{title}"\n\n'
            f"View it: {button_url}\n\n— Vitamin-E"
        )

        msg = MailMessage(
            subject=f'[Vitamin-E] New {item_type}: {title[:50]}{"..." if len(title) > 50 else ""}',
            recipients=['ezekiel@vitamin.works'],
            body=text_body,
            html=html_body
        )
        mail.send(msg)

    except Exception as e:
        current_app.logger.warning(f'notify_admin_of_new_feedback: email failed: {e}')


def notify_all_of_new_blog_post(post, triggered_by, send_inapp=True, send_email=True):
    """
    Notify all users of a new or updated blog post.
    send_inapp: create in-app notifications (skips the author) — runs synchronously.
    send_email: send HTML email to all users (skips the author) — runs in a background
                thread so slow SMTP never blocks the request worker.
    """
    import threading
    from flask import current_app

    message = f'New app update posted: {post.title}'
    blog_url = f'https://app.vitamin-e.work/blog#post-{post.id}'
    email_enabled = str(current_app.config.get('MAIL_ENABLED', 'false')).lower() == 'true'

    users = User.query.all()

    # ── In-app notifications (fast DB writes — keep synchronous) ──────────────
    if send_inapp:
        for user in users:
            if user.id == triggered_by.id:
                continue
            notif = Notification(
                recipient_id=user.id,
                message=message,
                notification_type='system_update',
                triggered_by_id=triggered_by.id,
                link=f'/blog#post-{post.id}'
            )
            db.session.add(notif)
        db.session.commit()

    # ── Email notifications (slow SMTP — run in background thread) ────────────
    if send_email and email_enabled:
        # Collect everything we need as plain values before leaving the request context.
        post_title   = post.title
        post_id      = post.id
        version_tag  = post.version_tag or ''
        email_targets = [(u.name, u.email) for u in users
                         if u.id != triggered_by.id and u.email]

        app = current_app._get_current_object()

        def _send_emails():
            with app.app_context():
                try:
                    from flask_mail import Message as MailMessage
                    from app import mail as mail_obj
                except Exception:
                    app.logger.warning('notify_all_of_new_blog_post: flask_mail not available')
                    return

                version_line = (
                    f'<p style="margin:0 0 16px;font-family:Arial,sans-serif;font-size:13px;'
                    f'color:#F27F55;letter-spacing:2px;text-transform:uppercase;">{version_tag}</p>'
                ) if version_tag else ''

                for name, email in email_targets:
                    html_body = f"""
            <table width="100%" cellpadding="0" cellspacing="0" border="0"
                   style="background-color:#F5F0E8;">
                <tr><td align="center" style="padding:48px 20px;">
                    <table width="520" cellpadding="0" cellspacing="0" border="0"
                           style="max-width:520px;width:100%;background-color:#ffffff;border-radius:12px;overflow:hidden;">
                        <tr><td style="padding:28px 36px 0 36px;">
                            <span style="font-family:Arial,sans-serif;font-size:11px;font-weight:bold;
                                         letter-spacing:3px;color:#F27F55;text-transform:uppercase;">VITAMIN-E</span>
                            <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top:14px;">
                                <tr><td style="height:2px;background-color:#F27F55;font-size:0;line-height:0;">&nbsp;</td></tr>
                            </table>
                        </td></tr>
                        <tr><td style="padding:32px 36px 28px 36px;">
                            <p style="margin:0 0 6px;font-family:Arial,sans-serif;font-size:11px;color:#bbb;
                                       letter-spacing:2px;text-transform:uppercase;">App Update</p>
                            <p style="margin:0 0 20px;font-family:Arial,sans-serif;font-size:17px;
                                       font-weight:bold;color:#1A1A1A;">Hi {name},</p>
                            {version_line}
                            <p style="margin:0 0 8px;font-family:Arial,sans-serif;font-size:19px;
                                       font-weight:bold;color:#1A1A1A;">{post_title}</p>
                            <p style="margin:0 0 28px;font-family:Arial,sans-serif;font-size:15px;
                                       line-height:1.7;color:#444444;">
                                A new update has been posted to Vitamin-E. Click below to read it.
                            </p>
                            <a href="{blog_url}"
                               style="display:inline-block;padding:12px 28px;background-color:#F27F55;
                                      color:#ffffff;font-family:Arial,sans-serif;font-size:14px;
                                      font-weight:bold;text-decoration:none;border-radius:6px;">
                                Read Update
                            </a>
                        </td></tr>
                        <tr><td style="padding:20px 36px;border-top:1px solid #F5F0E8;">
                            <p style="margin:0;font-family:Arial,sans-serif;font-size:11px;color:#aaa;">
                                Vitamin-E · Internal Platform
                            </p>
                        </td></tr>
                    </table>
                </td></tr>
            </table>"""

                    try:
                        msg = MailMessage(
                            subject=f'Vitamin-E Update — {post_title}',
                            recipients=[email],
                            html=html_body
                        )
                        mail_obj.send(msg)
                    except Exception as e:
                        app.logger.warning(
                            f'notify_all_of_new_blog_post: email failed for {email}: {e}'
                        )

        threading.Thread(target=_send_emails, daemon=True).start()