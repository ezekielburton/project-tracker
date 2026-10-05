"""Every 2 minutes (nas-outbox-flush.timer): push files queued on the server
while the NAS was down, then delete the server copies."""
from app import create_app
from app.modules.core.shared.services.nas_outbox import flush

app = create_app()
with app.app_context():
    sent, left = flush()
    if sent or left:
        print(f'Sent {sent} queued file(s) to the NAS; {left} still queued.')
