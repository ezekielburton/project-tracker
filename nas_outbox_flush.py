"""Every 2 minutes (nas-outbox-flush.timer): push files queued on the server
while the NAS was down, then delete the server copies."""
from app import create_app
from app.modules.core.shared.services.nas_outbox import flush
from app.modules.system.services.jobs import job_run

with job_run('nas-outbox-flush') as run:
    app = create_app()
    with app.app_context():
        sent, left = flush()
    run.details = {'sent': sent, 'queued': left}
    if sent or left:
        run.message = f'Sent {sent} queued file(s) to the NAS; {left} still queued.'
        print(run.message)
