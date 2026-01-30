"""
API routers for JobTracker.
"""

from .occupations import router as occupations_router
from .skills import router as skills_router
from .wages import router as wages_router

__all__ = ["occupations_router", "wages_router", "skills_router"]
