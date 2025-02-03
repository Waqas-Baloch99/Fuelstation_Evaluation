from rest_framework import serializers
from .models import FuelStation, Route, FuelStop

class FuelStationSerializer(serializers.ModelSerializer):
    class Meta:
        model = FuelStation
        fields = ['id', 'truck_stop', 'address', 'city', 'state', 'retail_price', 'latitude', 'longitude']

class FuelStopSerializer(serializers.ModelSerializer):
    fuel_station = FuelStationSerializer()
    
    class Meta:
        model = FuelStop
        fields = ['fuel_station', 'distance_from_start', 'fuel_amount', 'cost', 'stop_number']

class RouteSerializer(serializers.ModelSerializer):
    fuel_stops = FuelStopSerializer(many=True, read_only=True)
    total_cost = serializers.FloatField()
    total_distance = serializers.FloatField()
    
    class Meta:
        model = Route
        fields = ['start_location', 'end_location', 'total_distance', 'total_cost', 'fuel_stops']

class RouteRequestSerializer(serializers.Serializer):
    start_location = serializers.CharField(max_length=255)
    end_location = serializers.CharField(max_length=255) 