"""
EAGLE API Routers

Modular FastAPI routers extracted from main.py for better organization.
Each router handles a specific domain of the API.
"""

from .feedback import router as feedback_router
from .health import router as health_router
from .mcp import router as mcp_router
from .analytics import router as analytics_router
from .user import router as user_router
from .skills import router as skills_router
from .workspaces import router as workspaces_router
from .templates import router as templates_router
from .tenants import router as tenants_router
from .sessions import router as sessions_router
from .documents import router as documents_router
from .packages import router as packages_router
from .admin import router as admin_router
from .chat import router as chat_router

__all__ = [
    "feedback_router",
    "health_router",
    "mcp_router",
    "analytics_router",
    "user_router",
    "skills_router",
    "workspaces_router",
    "templates_router",
    "tenants_router",
    "sessions_router",
    "documents_router",
    "packages_router",
    "admin_router",
    "chat_router",
]
