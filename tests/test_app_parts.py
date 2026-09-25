import sys
sys.path.insert(0, '.')
print("0: starting")

# Simulate what app.py does at module level
import logging
import os
import threading
import uuid
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
print("1: stdlib ok")

from flask import Flask, jsonify, redirect, render_template, request, send_file, session, url_for, flash
print("2: flask ok")

import config
print("3: config ok")

from auth.routes import auth_bp
print("4: auth_bp ok")

from utils.data_loader import load_kitchens, load_ngos, load_surplus_log, load_matches, load_raw_material_log, load_exchange_log, save_surplus_log, save_matches, save_raw_material_log, save_exchange_log
print("5: data_loader ok")

print("All good - no timeout")
