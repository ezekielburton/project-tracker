from markupsafe import escape

from app.modules.core.shared.extensions import db
from app.modules.core.shared.models import Notification, User, ProjectSecondaryCS, ProjectSecondaryCsRegion
from app.modules.core.shared.lib.users import active_users_query


# ── Private helpers ───────────────────────────────────────────────────────────

def _get_secondary_cs(project):
    """Return all secondary CS User objects for a project."""
    return [a.user for a in ProjectSecondaryCS.query.filter_by(project_id=project.id).all()]


def _secondary_cs_subscribed_to_region(project, user, region):
    """True if this secondary CS gets notifications for region: every
    region when they have no region filter, else only subscribed ones."""
    subs = ProjectSecondaryCsRegion.query.filter_by(project_id=project.id, user_id=user.id).all()
    if not subs:
        return True
    return any(s.region == region for s in subs)


def _deliverable_region(deliverable):
    """A C&CM deliverable's region, via project_customer -> customer."""
    if deliverable and deliverable.project_customer and deliverable.project_customer.customer:
        return deliverable.project_customer.customer.region
    return None


def _get_project_designers(project):
    """Unique users assigned to any deliverable, plus the project's concept
    and KV designers."""
    seen_ids = set()
    designers = []

    # DeliverableAssignment rows
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
    """Email an in-app notification as HTML. Does nothing if mail is
    disabled; failures are logged."""
    from flask import current_app
    if str(current_app.config.get('MAIL_ENABLED', 'false')).lower() != 'true':
        return
    if not recipient.email:
        return
    try:
        from flask_mail import Message as MailMessage
        from app.modules.core.shared.extensions import mail

        # No /projects/<id> page exists; the Projects list opens a project
        # from its ?project= query (project_list.index).
        app_url = 'https://app.vitamin-e.work'
        if project:
            button_url = f'{app_url}/projects-new/?project={project.id}'
        else:
            button_url = app_url

        # Names and messages are user-typed; escape them for the HTML body.
        project_line = f'<p style="margin:0 0 12px;color:#555555;font-size:14px;"><strong>Project:</strong> {escape(project.name)}</p>' if project else ''

        # Inline styles: email clients ignore <style> blocks.
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
                                    Hi {escape(recipient.name)},
                                </p>
                                <p style="margin:0 0 24px;font-family:Arial,sans-serif;
                                          font-size:15px;line-height:1.7;color:#444444;">
                                    {escape(message)}
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
    """Create an in-app notification and optionally email it. The in-app
    notification is always created; the email is gated by pref_key (None =
    always send) and skipped entirely when send_email is False."""
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

    # pref_key None -> always email; send_email=False -> caller already emailed.
    if send_email and (pref_key is None or recipient.wants_notification(pref_key)):
        _send_notification_email(recipient, message, project)

    return notification


# ── Notify functions ──────────────────────────────────────────────────────────

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
    """Notify the other side of a flag reply: the CS lead if the flag's
    author replied, else the author."""
    if triggered_by.id == flag.created_by_id:
        recipient = User.query.get(project.cs_lead_id)
        message = f'{triggered_by.name} replied to their flag on "{project.name}".'
    else:
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


def notify_of_chat_mention(note, project, mentioned_users, triggered_by):
    """Notify each @-mentioned user (already validated by create_note()).
    The link opens the project AND its chat drawer (autoOpenFromUrl() /
    openChat() in project_list.js / project_overlay.js)."""
    from flask import url_for

    message = f'{triggered_by.name} mentioned you in "{project.name}".'
    link = url_for('project_list.index', project=project.id, chat=1)
    for user in mentioned_users:
        create_notification(
            recipient=user,
            message=message,
            notification_type='chat_mention',
            project=project,
            triggered_by=triggered_by,
            pref_key='chat_mention',
            link=link,
        )


def notify_project_owner_of_stream_uploaded(deliverable, project, stream_label, triggered_by):
    """Notify the Project Owner that a Pre-Production stream is ready to
    approve or flag. Skipped if they triggered it."""
    owner = User.query.get(project.project_owner_id) if project.project_owner_id else None
    if not owner or owner.id == triggered_by.id:
        return

    message = f'{triggered_by.name} marked {stream_label} ready for review on "{deliverable.name}" in "{project.name}".'
    create_notification(
        recipient=owner,
        message=message,
        notification_type='preprod_stream_uploaded',
        project=project,
        triggered_by=triggered_by,
        pref_key='preprod_stream_uploaded',
    )


def notify_designer_of_stream_approved(deliverable, project, stream_label, designer, triggered_by):
    """Tell the designer their Pre-Production stream was approved and to
    email the files to Production. No-op if no designer or they triggered it."""
    if not designer or designer.id == triggered_by.id:
        return

    message = (f'{stream_label} on "{deliverable.name}" in "{project.name}" has been approved — '
               f'please share the files with Production by email.')
    create_notification(
        recipient=designer,
        message=message,
        notification_type='preprod_stream_approved',
        project=project,
        triggered_by=triggered_by,
        pref_key='preprod_stream_approved',
    )


def notify_designer_of_concept_kv_assignment(project, designer, role_label, triggered_by):
    """Notify a designer of their Concept or KV role (role_label: 'Concept'
    or 'Key Visual')."""
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
    """Notify CS lead + secondary CS when a designer self-assigns or takes
    over as team lead; also tell previous_designer they were replaced."""
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


def notify_of_submission_to_client(project, triggered_by):
    """Notify the project's CS lead, secondary CS and assigned designers
    (not the actor) that a deck was submitted to the client."""
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


def notify_of_project_approved(project, triggered_by):
    """Notify the project's CS lead, secondary CS and assigned designers
    (not the actor) that the project was approved."""
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


def notify_admin_of_new_feedback(item_type, title, submitted_by, url_path):
    """Email the hardcoded admin address about a new feature request or bug
    report (item_type). Email only, no in-app notification."""
    from flask import current_app
    if str(current_app.config.get('MAIL_ENABLED', 'false')).lower() != 'true':
        return

    try:
        from flask_mail import Message as MailMessage
        from app.modules.core.shared.extensions import mail

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
                            {escape(item_type)}
                        </p>
                        <p style="margin:0 0 20px;font-family:Arial,sans-serif;font-size:17px;
                                   font-weight:bold;color:#1A1A1A;">
                            New {escape(item_type)}
                        </p>
                        <p style="margin:0 0 8px;font-family:Arial,sans-serif;font-size:15px;
                                   line-height:1.7;color:#444444;">
                            <strong>{escape(submitted_by.name)}</strong> submitted a new {escape(item_type.lower())}:
                        </p>
                        <p style="margin:0 0 24px;font-family:Arial,sans-serif;font-size:16px;
                                   font-weight:bold;color:#1A1A1A;">
                            &ldquo;{escape(title)}&rdquo;
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
    """Notify every user but the author of a new or updated blog post.
    In-app notifications are written synchronously; emails go from a
    background thread so slow SMTP never blocks the request."""
    import threading
    from flask import current_app

    message = f'New app update posted: {post.title}'
    blog_url = f'https://app.vitamin-e.work/blog#post-{post.id}'
    email_enabled = str(current_app.config.get('MAIL_ENABLED', 'false')).lower() == 'true'

    users = active_users_query().all()

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
        # Plain values only: the thread can't touch request-bound ORM objects.
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
                    from app.modules.core.shared.extensions import mail as mail_obj
                except Exception:
                    app.logger.warning('notify_all_of_new_blog_post: flask_mail not available')
                    return

                version_line = (
                    f'<p style="margin:0 0 16px;font-family:Arial,sans-serif;font-size:13px;'
                    f'color:#F27F55;letter-spacing:2px;text-transform:uppercase;">{escape(version_tag)}</p>'
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
                                       font-weight:bold;color:#1A1A1A;">Hi {escape(name)},</p>
                            {version_line}
                            <p style="margin:0 0 8px;font-family:Arial,sans-serif;font-size:19px;
                                       font-weight:bold;color:#1A1A1A;">{escape(post_title)}</p>
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


# ── Request Editing Access (project_overlay/details.py) ─────────────────────

def notify_cs_of_edit_access_request(project, requester):
    """Notify the CS lead and every secondary CS (who can approve or deny)
    that a designer requested editing access."""
    message = f'{requester.name} requested editing access to "{project.name}".'

    cs_lead = User.query.get(project.cs_lead_id)
    if cs_lead:
        create_notification(recipient=cs_lead, message=message, notification_type='edit_access_requested',
                            project=project, triggered_by=requester,
                            pref_key='edit_access_requested')

    for secondary in _get_secondary_cs(project):
        create_notification(recipient=secondary, message=message, notification_type='edit_access_requested',
                            project=project, triggered_by=requester,
                            pref_key='edit_access_requested')


def notify_designer_of_edit_access_decision(edit_access_request, approved, triggered_by):
    """Tell the requesting designer their editing-access request was
    approved or denied."""
    recipient = edit_access_request.user
    project = edit_access_request.project
    if not recipient or not project:
        return
    verb = 'approved' if approved else 'denied'
    message = f'{triggered_by.name} {verb} your request for editing access on "{project.name}".'
    create_notification(
        recipient=recipient, message=message,
        notification_type='edit_access_approved' if approved else 'edit_access_denied',
        project=project, triggered_by=triggered_by,
        pref_key='edit_access_decided'
    )