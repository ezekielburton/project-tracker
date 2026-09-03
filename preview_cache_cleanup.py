"""Daily maintenance: clears the reference-file preview cache. The NAS is
the source of truth for these files — the cache only speeds up video/audio
seeking, so wiping it and refetching on next preview is always safe."""
import os
from config import Config

cache_dir = os.path.join(Config.UPLOAD_FOLDER, 'preview-cache')

if os.path.isdir(cache_dir):
    removed = 0
    for name in os.listdir(cache_dir):
        path = os.path.join(cache_dir, name)
        if os.path.isfile(path):
            os.remove(path)
            removed += 1
    print(f'Removed {removed} cached preview file(s).')
else:
    print('No preview cache directory yet — nothing to do.')
