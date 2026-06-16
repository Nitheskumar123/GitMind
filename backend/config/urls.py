from django.contrib import admin
from django.urls import path, include, re_path
from django.views.generic import TemplateView
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve
import os

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('core.urls')),
    path('', TemplateView.as_view(template_name='index.html'), name='landing'),
    path('dashboard/', TemplateView.as_view(template_name='dashboard.html'), name='dashboard'),
    path('ai-chat/', TemplateView.as_view(template_name='ai-chat.html'), name='ai_chat'),
    path('repository-detail.html', TemplateView.as_view(template_name='repository-detail.html'), name='repository-detail'),
    path('settings-panel.html', TemplateView.as_view(template_name='settings-panel.html'), name='settings-panel'),
    path('cognitive-debt/', TemplateView.as_view(template_name='cognitive-debt.html'), name='cognitive-debt'),
]

# Serve frontend assets in development
if settings.DEBUG:
    # Serve CSS files from frontend/css/ - both /css/ and /static/css/ paths
    urlpatterns += [
        re_path(r'^static/css/(?P<path>.*)$', serve, {'document_root': os.path.join(settings.BASE_DIR.parent, 'frontend', 'css')}),
        re_path(r'^css/(?P<path>.*)$', serve, {'document_root': os.path.join(settings.BASE_DIR.parent, 'frontend', 'css')}),
        # Serve JS files from frontend/js/ - both /js/ and /static/js/ paths
        re_path(r'^static/js/(?P<path>.*)$', serve, {'document_root': os.path.join(settings.BASE_DIR.parent, 'frontend', 'js')}),
        re_path(r'^js/(?P<path>.*)$', serve, {'document_root': os.path.join(settings.BASE_DIR.parent, 'frontend', 'js')}),
        # Serve assets files from frontend/assets/
        re_path(r'^assets/(?P<path>.*)$', serve, {'document_root': os.path.join(settings.BASE_DIR.parent, 'frontend', 'assets')}),
        re_path(r'^static/(?P<path>.*)$', serve, {'document_root': os.path.join(settings.BASE_DIR.parent, 'frontend')}),
    ]
