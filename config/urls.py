from django.contrib import admin
from django.urls import path, include
from apps.core.views import dashboard_view, architecture_docs_view
from apps.core.auth_views import login_view, logout_view, signup_view

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', dashboard_view, name='dashboard'),
    path('login/', login_view, name='login'),
    path('logout/', logout_view, name='logout'),
    path('signup/', signup_view, name='signup'),
    path('docs/architecture/', architecture_docs_view, name='architecture_docs'),
    
    # Modular Django App Endpoints
    path('inventory/', include('apps.inventory.urls', namespace='inventory')),
    path('applications/', include('apps.applications.urls', namespace='applications')),
    path('eligibility/', include('apps.eligibility.urls', namespace='eligibility')),
    path('preferences/', include('apps.preferences.urls', namespace='preferences')),
    path('compatibility/', include('apps.compatibility.urls', namespace='compatibility')),
    path('allocation/', include('apps.allocation.urls', namespace='allocation')),
    path('review/', include('apps.review.urls', namespace='review')),
    path('waitlist/', include('apps.waitlist.urls', namespace='waitlist')),
    path('publication/', include('apps.publication.urls', namespace='publication')),
    path('notifications/', include('apps.notifications.urls', namespace='notifications')),
    path('audit/', include('apps.audit.urls', namespace='audit')),
]
