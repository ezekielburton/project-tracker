import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app import create_app

PROJECT_ID = 39   # <-- put a real project id from your local DB here
USER_ID = 5       # <-- put a real user id (any role) from your local DB here

app = create_app()
client = app.test_client()

with client.session_transaction() as sess:
    sess['_user_id'] = str(USER_ID)
    sess['_fresh'] = True

resp = client.post(
    f'/projects/{PROJECT_ID}/overlay/submissions/draft/upload',
    data={'file': (open(__file__, 'rb'), 'test-deck.pdf'), 'scope': 'ckv'},
    content_type='multipart/form-data',
)
print(resp.status_code, resp.get_json())

# Upload a second file — should NOT be flagged main deck (first one already is)
resp2 = client.post(
    f'/projects/{PROJECT_ID}/overlay/submissions/draft/upload',
    data={'file': (open(__file__, 'rb'), 'support-file.ai'), 'scope': 'ckv'},
    content_type='multipart/form-data',
)
print(resp2.status_code, resp2.get_json())