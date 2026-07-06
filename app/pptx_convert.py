import subprocess
import tempfile
import os
from pathlib import Path

SOFFICE_PATH = os.environ.get('SOFFICE_PATH', 'soffice')


def convert_pptx_to_pdf(file_bytes):
    with tempfile.TemporaryDirectory() as tmp_dir:
        input_path = os.path.join(tmp_dir, 'input.pptx')

        with open(input_path, 'wb') as f:
            f.write(file_bytes)

        profile_dir = Path(tmp_dir) / 'lo_profile'
        profile_uri = profile_dir.as_uri()

        result = subprocess.run(
            [
                SOFFICE_PATH,
                f'-env:UserInstallation={profile_uri}',
                '--headless', '--convert-to', 'pdf',
                '--outdir', tmp_dir, input_path
            ],
            capture_output=True,
            timeout=60,
        )

        # --- TEMPORARY DIAGNOSTICS — remove once we know what's happening ---
        print('RETURN CODE:', result.returncode)
        print('STDOUT:', result.stdout.decode(errors='replace'))
        print('STDERR:', result.stderr.decode(errors='replace'))
        print('TMP DIR CONTENTS:', os.listdir(tmp_dir))
        # ----------------------------------------------------------------

        if result.returncode != 0:
            raise RuntimeError(
                f'PPTX to PDF conversion failed: {result.stderr.decode(errors="replace")}'
            )

        output_path = os.path.join(tmp_dir, 'input.pdf')

        with open(output_path, 'rb') as f:
            return f.read()