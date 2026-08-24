# Copyright (c) 2026, AFMCO and contributors

import os
from pathlib import Path

import apex

APP_ROOT = str(Path(apex.__file__).resolve().parent)

NOTIFICATION_GLOB = os.path.join(APP_ROOT, "*", "notification", "*", "*.json")

