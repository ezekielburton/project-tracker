"""
Public, reusable Project-mutation functions. Same effect (notification +
activity-log shape) as the equivalent project_overlay routes, so a change
made from outside the overlay — the Client Servicing table, so far — still
produces the exact history/notifications a change made in the overlay
would. Callers do their own permission checks; these assume the caller
already decided the actor may make this change.
"""
from datetime import date

from app.modules.core.shared.extensions import db
from app.modules.core.shared.lib.utils import log_activity
from app.modules.core.shared.models import ProjectSecondaryCS
from app.modules.core.shared.services.notifications import create_notification


def reassign_cs_lead(project, new_cs_lead, actor):
    """Same notification/log shape as project_overlay/deliverables.py's
    reassign-cs-lead route: notifies the new (and outgoing) CS lead."""
    previous_cs_lead = project.cs_lead
    project.cs_lead_id = new_cs_lead.id
    db.session.commit()

    create_notification(
        recipient=new_cs_lead,
        message=f'You have been assigned as CS lead on "{project.name}" by {actor.name}.',
        notification_type='cs_lead_reassigned',
        project=project,
        triggered_by=actor,
    )
    if previous_cs_lead and previous_cs_lead.id != new_cs_lead.id:
        create_notification(
            recipient=previous_cs_lead,
            message=f'{new_cs_lead.name} has taken over as CS lead on "{project.name}" (reassigned by {actor.name}).',
            notification_type='cs_lead_reassigned',
            project=project,
            triggered_by=actor,
        )
    log_activity(
        'cs_lead_reassigned',
        f'{actor.name} reassigned CS lead on "{project.name}" to {new_cs_lead.name}'
        + (f' (previously {previous_cs_lead.name})' if previous_cs_lead else ''),
        user=actor, entity_type='project', entity_name=project.name, entity_id=project.id,
    )


def set_project_owner(project, new_owner, actor):
    """Same notification/log shape as project_overlay/deliverables.py's
    set-project-owner route: notifies the new owner (unless self-claimed)."""
    previous_owner = project.project_owner
    project.project_owner_id = new_owner.id
    db.session.commit()

    if new_owner.id != actor.id:
        create_notification(
            recipient=new_owner,
            message=f'You have been assigned as Project Owner on "{project.name}" by {actor.name}.',
            notification_type='project_owner_assigned',
            project=project,
            triggered_by=actor,
        )
    log_activity(
        'project_owner_assigned',
        f'{actor.name} assigned {new_owner.name} as Project Owner on "{project.name}"'
        + (f' (previously {previous_owner.name})' if previous_owner else ''),
        user=actor, entity_type='project', entity_name=project.name, entity_id=project.id,
    )


def _dedupe(users):
    """Preserve order, drop repeats (e.g. someone who is both secondary CS
    and Project Owner should only get one notification)."""
    seen = set()
    result = []
    for user in users:
        if user.id not in seen:
            seen.add(user.id)
            result.append(user)
    return result


def _secondary_cs_recipients(project, actor):
    """Secondary CS users on this project, excluding the actor."""
    assignments = ProjectSecondaryCS.query.filter_by(project_id=project.id).all()
    return [a.user for a in assignments if a.user and a.user.id != actor.id]


def _owner_recipient(project, actor):
    """The project's owner, if set and not the actor."""
    owner = project.project_owner
    return [owner] if owner and owner.id != actor.id else []


def _designer_recipients(project, actor):
    """Designers assigned to this project, excluding the actor."""
    return [pd.designer for pd in project.assigned_designers if pd.designer and pd.designer.id != actor.id]


def _notify_due_date_changed(project, actor, new_value):
    """Due Date = the final design deadline — designers need to know, same
    as CS and the owner."""
    message = (f'The due date on "{project.name}" was changed to {new_value.strftime("%d %b %Y")} by {actor.name}.'
               if new_value else f'The due date on "{project.name}" was cleared by {actor.name}.')
    recipients = _designer_recipients(project, actor) + _secondary_cs_recipients(project, actor) + _owner_recipient(project, actor)
    for recipient in _dedupe(recipients):
        create_notification(recipient=recipient, message=message, notification_type='due_date_changed',
                             project=project, triggered_by=actor, pref_key='due_date_changed')


def _notify_job_number_changed(project, actor, new_value):
    message = (f'The job number on "{project.name}" was changed to {new_value} by {actor.name}.'
               if new_value else f'The job number on "{project.name}" was cleared by {actor.name}.')
    recipients = _secondary_cs_recipients(project, actor) + _owner_recipient(project, actor)
    for recipient in _dedupe(recipients):
        create_notification(recipient=recipient, message=message, notification_type='job_number_changed',
                             project=project, triggered_by=actor, pref_key='job_number_changed')


def _notify_client_spoc_changed(project, actor, new_value):
    from app.modules.core.shared.models import Contact
    contact = Contact.query.get(new_value) if new_value else None
    message = (f'The Client SPOC on "{project.name}" was changed to {contact.name} by {actor.name}.'
               if contact else f'The Client SPOC on "{project.name}" was cleared by {actor.name}.')
    recipients = _secondary_cs_recipients(project, actor) + _owner_recipient(project, actor)
    for recipient in _dedupe(recipients):
        create_notification(recipient=recipient, message=message, notification_type='client_spoc_changed',
                             project=project, triggered_by=actor, pref_key='client_spoc_changed')


class FieldError(ValueError):
    """A field value that failed validation. Message is safe to show."""


def _parse_date(value):
    if value in (None, ''):
        return None
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise FieldError('must be a valid date')


def _parse_money(value):
    if value in (None, ''):
        return None
    try:
        amount = float(value)
    except (TypeError, ValueError):
        raise FieldError('must be a number')
    if amount < 0:
        raise FieldError('must not be negative')
    return amount


def _parse_text(max_len):
    def parse(value):
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        if len(text) > max_len:
            raise FieldError(f'must be {max_len} characters or fewer')
        return text
    return parse


def _parse_contact_id(value):
    if value in (None, ''):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        raise FieldError('must be a valid contact')


# field name -> (Project attribute, parser). The brief's "writes back to
# the project" fields minus CS lead / project owner, which are relationship
# reassignments handled by the two functions above instead.
DETAIL_FIELDS = {
    'job_number': ('job_number', _parse_text(100)),
    'contact_id': ('contact_id', _parse_contact_id),
    'installation_date': ('installation_date', _parse_date),
    'value': ('value', _parse_money),
    'first_output_deadline': ('first_output_deadline', _parse_date),
}

DETAIL_FIELD_LABELS = {
    'job_number': 'Job Number',
    'contact_id': 'Client SPOC',
    'installation_date': 'Installation Date',
    'value': 'Project Value',
    'first_output_deadline': 'Due Date',
}


def save_detail_field(project, actor, field_name, raw_value):
    """Validates and saves one of DETAIL_FIELDS, logging it the same way
    project_overlay/details.py's overlay_details_save logs a Details-tab
    edit. Raises FieldError for an invalid value or a value that fails a
    business rule (job number already taken, contact not on this
    project's client). Does nothing (no log, no commit) if the value
    didn't actually change. Returns the stored value."""
    entry = DETAIL_FIELDS.get(field_name)
    if entry is None:
        raise FieldError('that field cannot be edited here')
    attr_name, parser = entry
    new_value = parser(raw_value)

    if field_name == 'job_number' and new_value is not None:
        from app.modules.core.shared.models import Project
        clash = Project.query.filter(Project.job_number == new_value, Project.id != project.id).first()
        if clash:
            raise FieldError('already used by another project')

    if field_name == 'contact_id' and new_value is not None:
        from app.modules.core.shared.models import Contact
        contact = Contact.query.get(new_value)
        if not contact or contact.client_id != project.client_id:
            raise FieldError("must be one of this project's client's contacts")

    old_value = getattr(project, attr_name)
    if old_value == new_value:
        return new_value

    setattr(project, attr_name, new_value)
    db.session.commit()

    # The brief's three "notify on change" writeback fields (Chunk 5).
    # CS lead / Project Owner reassignment already notify via the two
    # functions above — this covers the rest.
    if field_name == 'first_output_deadline':
        _notify_due_date_changed(project, actor, new_value)
    elif field_name == 'job_number':
        _notify_job_number_changed(project, actor, new_value)
    elif field_name == 'contact_id':
        _notify_client_spoc_changed(project, actor, new_value)

    label = DETAIL_FIELD_LABELS.get(field_name, field_name)
    log_activity(
        'project_edited',
        f'{actor.name} edited {label} on "{project.name}"',
        user=actor, entity_type='project', entity_name=project.name, entity_id=project.id,
        changes=[{
            'field': field_name,
            'label': label,
            'old': old_value.isoformat() if hasattr(old_value, 'isoformat') else old_value,
            'new': new_value.isoformat() if hasattr(new_value, 'isoformat') else new_value,
        }],
    )
    return new_value
