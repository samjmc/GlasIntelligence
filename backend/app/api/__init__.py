"""
API routing modules
"""

from flask import Blueprint

graph_bp = Blueprint('graph', __name__)
simulation_bp = Blueprint('simulation', __name__)
report_bp = Blueprint('report', __name__)

from . import graph  # noqa: E402, F401
from . import simulation  # noqa: E402, F401
from . import report  # noqa: E402, F401
from . import simulation_interview_env_routes  # noqa: E402, F401
from .billing import billing_bp  # noqa: E402, F401
from .feed import feed_bp  # noqa: E402, F401

