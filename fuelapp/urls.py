from django.urls import path
from django.conf.urls.static import static
from django.conf import settings
from .views import (
    RoutePlannerView,
    RoutePlannerTemplateView,
    fuel_stations,
    calculate_station_route
)

urlpatterns = [
    path('', RoutePlannerTemplateView.as_view(), name='route_planner'),
    path('api/route/', RoutePlannerView.as_view(), name='route_api'),
    path('api/fuel-stations/', fuel_stations, name='fuel_stations_api'),
    path('api/station-route/', calculate_station_route, name='station-route'),
]+ static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)