from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve as static_serve
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

from . import views

FRONTEND_DIST = settings.BASE_DIR / 'frontend' / 'dist'

urlpatterns = [
    path('admin/', admin.site.urls),

    # --- 3Form API v1 (new) ---
    path('api/v1/', include('accounts.urls')),
    path('api/v1/', include('mes.urls')),
    path('api/v1/', include('reports.urls')),

    # --- Existing GreaterWMS endpoints (now behind the new role-based login) ---
    path('asn/', include('asn.urls')),
    path('dn/', include('dn.urls')),
    path('staff/', include('staff.urls')),
    path('binset/', include('binset.urls')),
    path('binsize/', include('binsize.urls')),
    path('binproperty/', include('binproperty.urls')),
    path('capital/', include('capital.urls')),
    path('driver/', include('driver.urls')),
    path('stock/', include('stock.urls')),
    path('company/', include('company.urls')),
    path('cyclecount/', include('cyclecount.urls')),
    path('dashboard/', include('dashboard.urls')),
    path('supplier/', include('supplier.urls')),
    path('customer/', include('customer.urls')),
    path('warehouse/', include('warehouse.urls')),
    path('goods/', include('goods.urls')),
    path('goodsunit/', include('goodsunit.urls')),
    path('goodsclass/', include('goodsclass.urls')),
    path('goodscolor/', include('goodscolor.urls')),
    path('goodsshape/', include('goodsshape.urls')),
    path('goodsspecs/', include('goodsspecs.urls')),
    path('goodsorigin/', include('goodsorigin.urls')),
    path('scanner/', include('scanner.urls')),
    path('payment/', include('payment.urls')),
    path('uploadfile/', include('uploadfile.urls')),
    # Removed on purpose: legacy 'login/' (shared never-expiring token) and
    # 'register/' (anyone could create a company) are unsafe in production.

    # --- API docs (for the AI agent and integrators) ---
    path('api/', SpectacularAPIView.as_view(), name='schema'),
    path('api/debug/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/docs/', SpectacularRedocView.as_view(url_name='schema'), name='docs'),

    # --- Files ---
    re_path(r'^favicon\.ico$', views.favicon, name='favicon'),
    re_path(r'^media/(?P<path>.*)$', static_serve, {'document_root': settings.MEDIA_ROOT}),
    re_path(r'^assets/(?P<path>.*)$', static_serve, {'document_root': FRONTEND_DIST / 'assets'}),
    re_path(r'^brand/(?P<path>.*)$', static_serve, {'document_root': FRONTEND_DIST / 'brand'}),

    # --- New Vue 3 app (client-side routes) ---
    path('', views.spa),
    re_path(r'^(login|worker|manager|pic)(/.*)?$', views.spa),
]
