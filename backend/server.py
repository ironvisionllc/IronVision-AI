"""Emergent preview entrypoint (supervisor runs `uvicorn server:app`). Docker uses `app.main:app` directly.
If the pod was restarted and PostgreSQL/supervisor programs are gone, re-provision them in the background."""
import os
import subprocess

if os.path.exists("/etc/supervisor/conf.d/supervisord_mono.conf") and not os.path.exists("/etc/supervisor/conf.d/aegis.conf"):
    subprocess.Popen(["bash", "/app/scripts/pod_bootstrap.sh"], stdout=open("/tmp/aegis_bootstrap.log", "ab"),
                     stderr=subprocess.STDOUT, start_new_session=True)

from app.main import app  # noqa: E402,F401
