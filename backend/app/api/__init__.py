"""
API routing modules
"""

from flask import Blueprint

graph_bp = Blueprint("graph", __name__)
simulation_bp = Blueprint("simulation", __name__)
report_bp = Blueprint("report", __name__)

from . import (  # noqa: E402 - route modules import the blueprints defined above
    graph,  # noqa: E402, F401
    report,  # noqa: E402, F401
    simulation,  # noqa: E402, F401
    simulation_access,  # noqa: E402, F401 - owner check on all three blueprints
    simulation_interview_env_routes,  # noqa: E402, F401
)
from .billing import billing_bp  # noqa: E402, F401
from .feed import feed_bp  # noqa: E402, F401
