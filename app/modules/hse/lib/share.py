"""
Sharing HSE figures: the My performance CSV, and emailing a report's
headline numbers with a link to the full report. The email carries no
attachment; the reader opens the link (they need view_hse) and can save the
PDF from there.
"""

import csv
import io
from html import escape

from flask import current_app, request

from app.modules.core.shared.lib.capabilities import can, role_label
from app.modules.core.shared.models import User
from app.modules.hse.lib.performance import trend_months

NOTE_MAX = 1000


class ShareError(Exception):
    """A send that cannot go ahead; the message is shown to the sender."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.message, self.status = message, status


# --- who can receive --------------------------------------------------------

def recipients(sender=None):
    """Active people with an email who can open HSE, sender left out, A-Z."""
    users = User.query.filter(User.is_active.is_(True), User.email.isnot(None)).all()
    return sorted((u for u in users
                   if can('view_hse', u) and (sender is None or u.id != sender.id)),
                  key=lambda u: (u.name or '').casefold())


def people(sender=None):
    """recipients() for the Email dialog's checklist."""
    return [{'id': u.id, 'name': u.name, 'role': role_label(u.role)}
            for u in recipients(sender)]


# --- the email --------------------------------------------------------------

def figures(tiles):
    """Tiles as (label, value, comparison) rows for the email."""
    out = []
    for t in tiles:
        value = '—' if t.get('value') is None else f"{t['value']}{_unit(t.get('unit'))}"
        d = t.get('delta')
        compare = f"from {d['from']}{_unit(t.get('delta_unit', t.get('unit')))}" if d else ''
        out.append((t['label'], value, compare))
    return out


def _unit(unit):
    if not unit:
        return ''
    return unit if unit == '%' else f' {unit}'


def absolute_url(path):
    """`path` on the host the sender is using. There is no ProxyFix, so the
    proxy's X-Forwarded-Proto decides http or https."""
    scheme = request.headers.get('X-Forwarded-Proto', request.scheme).split(',')[0].strip()
    return f'{scheme}://{request.host}{path}'


def mail_enabled():
    return str(current_app.config.get('MAIL_ENABLED', 'false')).lower() == 'true'


def _html(title, period, rows, link, note, sender):
    """Inline styles only: email clients ignore <style> blocks. Every
    user-typed value is escaped."""
    note_block = (f'<p style="margin:0 0 20px;padding:12px 14px;background:#F5F0E8;'
                  f'border-radius:8px;color:#3C362E;font-size:14px;line-height:1.5;">'
                  f'{escape(note).replace(chr(10), "<br>")}</p>') if note else ''
    body_rows = ''.join(
        f'<tr><td style="padding:8px 0;border-bottom:1px solid #EEE7DC;color:#3C362E;">{escape(label)}</td>'
        f'<td align="right" style="padding:8px 0;border-bottom:1px solid #EEE7DC;font-weight:bold;color:#1F1B16;">{escape(value)}</td>'
        f'<td align="right" style="padding:8px 0 8px 12px;border-bottom:1px solid #EEE7DC;color:#8A8070;font-size:12px;">{escape(compare)}</td></tr>'
        for label, value, compare in rows)
    return f"""
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#F5F0E8;">
  <tr><td align="center" style="padding:40px 20px;">
    <table width="560" cellpadding="0" cellspacing="0" border="0"
           style="max-width:560px;width:100%;background:#ffffff;border-radius:12px;font-family:Arial,sans-serif;">
      <tr><td style="padding:28px 36px 0;">
        <span style="font-size:11px;font-weight:bold;letter-spacing:3px;color:#F27F55;text-transform:uppercase;">HSE &amp; Compliance</span>
        <div style="margin-top:14px;height:2px;background:#F27F55;font-size:0;line-height:0;">&nbsp;</div>
      </td></tr>
      <tr><td style="padding:24px 36px 28px;">
        <h1 style="margin:0 0 4px;font-size:20px;color:#1F1B16;">{escape(title)}</h1>
        <p style="margin:0 0 20px;font-size:13px;color:#8A8070;">{escape(period)} · sent by {escape(sender.name)}</p>
        {note_block}
        <table width="100%" cellpadding="0" cellspacing="0" border="0" style="font-size:14px;">{body_rows}</table>
        <p style="margin:24px 0 0;">
          <a href="{escape(link)}" style="display:inline-block;padding:11px 20px;background:#F27F55;color:#ffffff;
             border-radius:8px;text-decoration:none;font-weight:bold;font-size:14px;">Open the full report</a>
        </p>
        <p style="margin:16px 0 0;font-size:12px;color:#8A8070;">You'll need to sign in. The report can be saved as a PDF from there.</p>
      </td></tr>
    </table>
  </td></tr>
</table>"""


def _text(title, period, rows, link, note, sender):
    lines = [title, f'{period} · sent by {sender.name}', '']
    if note:
        lines += [note, '']
    lines += [f'{label}: {value}' + (f' ({compare})' if compare else '')
              for label, value, compare in rows]
    lines += ['', f'Open the full report: {link}']
    return '\n'.join(lines)


def send(sender, recipient_ids, note, title, period, rows, link):
    """Email the figures to the chosen people, copying the sender. Returns
    the recipients. Raises ShareError when mail is off, nobody valid was
    picked, the note is too long, or sending fails."""
    if not mail_enabled():
        raise ShareError('Email is switched off on this server.', 503)
    allowed = {u.id: u for u in recipients(sender)}
    chosen = [allowed[i] for i in dict.fromkeys(recipient_ids or ())
              if isinstance(i, int) and i in allowed]
    if not chosen:
        raise ShareError('Pick at least one person to send it to.')
    note = str(note or '').strip()
    if len(note) > NOTE_MAX:
        raise ShareError(f'Keep the note under {NOTE_MAX} characters.')

    from flask_mail import Message
    from app.modules.core.shared.extensions import mail

    message = Message(
        subject=f'[HSE] {title} — {period}',
        recipients=[u.email for u in chosen],
        cc=[sender.email] if sender.email else None,
        reply_to=sender.email or None,
        body=_text(title, period, rows, link, note, sender),
        html=_html(title, period, rows, link, note, sender),
    )
    try:
        mail.send(message)
    except Exception as e:  # SMTP errors vary by provider
        current_app.logger.warning(f'HSE report email failed: {e}')
        raise ShareError('The email could not be sent. Try again in a minute.', 502)
    return chosen


# --- the My performance CSV -------------------------------------------------

def performance_csv(model):
    """The My performance page as CSV rows: the tiles against the previous
    period, reporting, compliance, open actions by age, and the twelve-month
    trend."""
    buffer = io.StringIO()
    w = csv.writer(buffer)
    window = model['window']
    w.writerow(['HSE My performance', window['label']])
    w.writerow([])
    w.writerow(['Measure', 'This period', 'Previous period', 'Unit'])
    for t in model['tiles']:
        d = t.get('delta')
        w.writerow([t['label'], _blank(t['value']), _blank(d['from']) if d else '', t.get('unit') or ''])
    r = model['reporting']
    w.writerow(['Near misses per incident', _blank(r['ratio']),
                _blank(r['delta']['from']) if r.get('delta') else '', ''])
    w.writerow([])
    c = model['compliance']
    w.writerow(['Compliance', 'Count'])
    w.writerow(['Items valid today', f"{c['valid']} of {c['total']}"])
    w.writerow(['Renewed before expiry', f"{c['renewals']['on_time']} of {c['renewals']['renewed']}"])
    w.writerow(['Lapsed in period', c['lapsed_count']])
    w.writerow([])
    w.writerow(['Open actions by age', 'Count'])
    for b in model['ageing']['buckets']:
        w.writerow([b['label'], b['count']])
    w.writerow([])
    w.writerow(['Month', 'Inspections planned', 'Inspections completed', 'Average days to close'])
    months = trend_months(window['end'])
    for month, cover, age in zip(months, model['_cover'], model['_ageing']):
        w.writerow([month['start'].strftime('%b %Y'), cover['planned'], cover['done'],
                    _blank(age['days'])])
    return buffer.getvalue()


def _blank(value):
    return '' if value is None else value
