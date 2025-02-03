from django.contrib import admin
from .models import FuelStation, Route, FuelStop

@admin.register(FuelStation)
class FuelStationAdmin(admin.ModelAdmin):
    list_display = ('truck_stop', 'city', 'state', 'retail_price')
    list_filter = ('state',)
    search_fields = ('truck_stop', 'city', 'state')

@admin.register(Route)
class RouteAdmin(admin.ModelAdmin):
    list_display = ('start_location', 'end_location', 'total_distance', 'total_cost')

@admin.register(FuelStop)
class FuelStopAdmin(admin.ModelAdmin):
    list_display = ('route', 'fuel_station', 'stop_number', 'cost')
