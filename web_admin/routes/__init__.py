cat > web_admin/routes/__init__.py << 'EOF'
from .assortment.manage import router as assortment_manage_router
from .assortment.views import router as assortment_views_router
from .auth import router as auth_router
from .clients import router as clients_router
from .dashboard import router as dashboard_router
from .debug import router as debug_router
from .purchases import router as purchases_router
from .sellers import router as sellers_router
from .sold import router as sold_router
from .stats import router as stats_router

routers = [
    auth_router,
    dashboard_router,
    clients_router,
    purchases_router,
    sold_router,
    stats_router,
    debug_router,
    assortment_views_router,
    assortment_manage_router,
    sellers_router,
]
EOF
