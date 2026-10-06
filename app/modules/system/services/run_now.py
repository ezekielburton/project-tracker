"""Run now without a shell: the web app drops a trigger file named after the
job, holding the admin's user id. A systemd path unit per job sees it and
starts the job's own service; job_run() takes the file and records who."""
import os

from config import Config
from app.modules.system.lib.job_list import BY_KEY


class NotRunnable(ValueError):
    """The job isn't on the list or must not be started by hand."""


def _folder(folder):
    return folder or Config.RUN_NOW_DIR


def request_run(job_key, user_id, folder=None):
    """Ask for `job_key` to start now on behalf of `user_id`."""
    job = BY_KEY.get(job_key)
    if job is None or not job.run_now:
        raise NotRunnable(job_key)
    folder = _folder(folder)
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, job.key), 'w', encoding='utf-8') as f:
        f.write(str(int(user_id)))


def claim(job_key, folder=None):
    """Take this job's trigger file if there is one: the user id that asked, or None."""
    path = os.path.join(_folder(folder), job_key)
    try:
        with open(path, encoding='utf-8') as f:
            text = f.read().strip()
        os.remove(path)
    except OSError:
        return None
    return int(text) if text.isdigit() else None


def pending(folder=None):
    """Job keys with a Run now request waiting."""
    try:
        return sorted(name for name in os.listdir(_folder(folder)) if name in BY_KEY)
    except OSError:
        return []
