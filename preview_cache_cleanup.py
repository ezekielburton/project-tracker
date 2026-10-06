"""Daily maintenance: clears the reference-file preview cache. The NAS is
the source of truth for these files — the cache only speeds up video/audio
seeking, so wiping it and refetching on next preview is always safe."""
import os
from config import Config
from app.modules.system.services.jobs import job_run

cache_dir = os.path.join(Config.UPLOAD_FOLDER, 'preview-cache')

with job_run('preview-cache-cleanup') as run:
    removed = freed = 0
    if os.path.isdir(cache_dir):
        for name in os.listdir(cache_dir):
            path = os.path.join(cache_dir, name)
            if os.path.isfile(path):
                freed += os.path.getsize(path)
                os.remove(path)
                removed += 1
    run.message = f'Removed {removed} cached preview file(s).'
    run.bytes_reclaimed = freed or None
    print(run.message)
