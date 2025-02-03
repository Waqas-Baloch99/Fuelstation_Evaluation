# views.py
from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import api_view
from rest_framework import status
from django.views.generic import TemplateView
import requests
from .models import FuelStation, Route, FuelStop
from .serializers import RouteSerializer, RouteRequestSerializer, FuelStationSerializer
from django.conf import settings
from geopy.distance import geodesic
from geopy.geocoders import Nominatim
import logging
import time
import polyline

logger = logging.getLogger(__name__)

class RoutePlannerTemplateView(TemplateView):
    template_name = 'fuelapp/route_planner.html'

class RoutePlannerView(APIView):
    def post(self, request):
        try:
            serializer = RouteRequestSerializer(data=request.data)
            if not serializer.is_valid():
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
            start = serializer.validated_data['start_location']
            end = serializer.validated_data['end_location']
            
            # Geocode locations with debug output
            geolocator = Nominatim(user_agent="fuel_planner")
            start_location = geolocator.geocode(start)
            print(f"Start location: {start} -> {start_location.latitude}, {start_location.longitude}")
            time.sleep(1)
            end_location = geolocator.geocode(end)
            print(f"End location: {end} -> {end_location.latitude}, {end_location.longitude}")
            
            if not start_location or not end_location:
                return Response(
                    {"error": "Could not find one or both locations"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Get route from OSRM
            osrm_url = f"{settings.OSRM_ENDPOINT}/route/v1/driving/{start_location.longitude},{start_location.latitude};{end_location.longitude},{end_location.latitude}?overview=full&geometries=geojson"
            route_response = requests.get(osrm_url)
            route_data = route_response.json()
            
            if route_response.status_code != 200 or route_data.get('code') != 'Ok':
                return Response(
                    {"error": "Could not calculate route"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Calculate total distance and fuel needed
            total_distance = route_data['routes'][0]['distance'] / 1609.34  # Convert meters to miles
            total_fuel_needed = total_distance / settings.FUEL_ECONOMY  # 10 mpg
            
            # Check if distance is greater than MAX_FUEL_RANGE
            if total_distance > settings.MAX_FUEL_RANGE:
                return Response({
                    "error": f"This route is {round(total_distance)} miles long. Cannot travel more than {settings.MAX_FUEL_RANGE} miles without refueling.",
                    "start_coords": [start_location.latitude, start_location.longitude],
                    "end_coords": [end_location.latitude, end_location.longitude],
                    "total_distance": total_distance,
                    "route_geometry": route_data['routes'][0]['geometry']
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Create route object
            route = Route.objects.create(
                start_location=start,
                end_location=end,
                total_distance=total_distance,
                total_cost=0.0
            )
            
            # Find cheapest fuel station near start for initial fuel
            initial_station = self.find_nearest_cheapest_station(
                start_location.latitude,
                start_location.longitude
            )
            
            if not initial_station:
                return Response(
                    {"error": "No fuel stations found near start location"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Calculate fuel stops
            remaining_distance = total_distance
            current_lat = start_location.latitude
            current_lon = start_location.longitude
            total_fuel_cost = 0
            stop_number = 1
            
            while remaining_distance > 0:
                # Calculate how far we can go with a full tank
                distance_possible = min(remaining_distance, settings.MAX_FUEL_RANGE)
                fuel_needed = distance_possible / settings.FUEL_ECONOMY
                
                # Find nearest cheapest station
                fraction = distance_possible / total_distance
                next_lat = current_lat + (end_location.latitude - start_location.latitude) * fraction
                next_lon = current_lon + (end_location.longitude - start_location.longitude) * fraction
                
                station = self.find_nearest_cheapest_station(next_lat, next_lon)
                
                if station:
                    fuel_cost = fuel_needed * float(station.retail_price)
                    total_fuel_cost += fuel_cost
                    
                    FuelStop.objects.create(
                        route=route,
                        fuel_station=station,
                        distance_from_start=total_distance - remaining_distance + distance_possible,
                        fuel_amount=fuel_needed,
                        cost=fuel_cost,
                        stop_number=stop_number
                    )
                    
                    stop_number += 1
                    current_lat = next_lat
                    current_lon = next_lon
                
                remaining_distance -= distance_possible
            
            route.total_cost = total_fuel_cost
            route.save()
            
            serializer = RouteSerializer(route)
            return Response({
                **serializer.data,
                'start_coords': [start_location.latitude, start_location.longitude],
                'end_coords': [end_location.latitude, end_location.longitude],
                'total_fuel_needed': round(total_fuel_needed, 2),
                'route_geometry': route_data['routes'][0]['geometry']
            })
            
        except Exception as e:
            logger.error(f"Route calculation error: {str(e)}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def find_nearest_cheapest_station(self, lat, lon, max_distance=50):
        """Find the cheapest station within max_distance miles."""
        stations = []
        all_stations = FuelStation.objects.exclude(latitude__isnull=True).exclude(longitude__isnull=True)
        print(f"Searching for stations near ({lat}, {lon})")
        print(f"Total stations with coordinates: {all_stations.count()}")
        
        for station in all_stations:
            try:
                distance = geodesic((lat, lon), (station.latitude, station.longitude)).miles
                print(f"Station: {station.truck_stop} in {station.city}, OK")
                print(f"  Coordinates: ({station.latitude}, {station.longitude})")
                print(f"  Distance: {distance:.2f} miles")
                print(f"  Price: ${float(station.retail_price):.3f}")
                
                if distance <= max_distance:
                    stations.append((station, distance, float(station.retail_price)))
            except Exception as e:
                print(f"Error calculating distance for station {station.truck_stop}: {str(e)}")
        
        if not stations:
            print(f"No stations found within {max_distance} miles")
            return None
        
        # Sort by price first, then by distance
        stations.sort(key=lambda x: (x[2], x[1]))
        chosen_station = stations[0][0]
        print(f"Selected station: {chosen_station.truck_stop}")
        print(f"  Distance: {stations[0][1]:.2f} miles")
        print(f"  Price: ${float(chosen_station.retail_price):.3f}")
        return chosen_station

@api_view(['GET'])
def fuel_stations(request):
    stations = FuelStation.objects.all()
    print(f"Found {stations.count()} stations")
    # Debug output for stations with coordinates
    stations_with_coords = stations.exclude(latitude__isnull=True).exclude(longitude__isnull=True)
    print(f"Stations with coordinates: {stations_with_coords.count()}")
    for station in stations_with_coords:
        print(f"Station: {station.truck_stop}, Lat: {station.latitude}, Lon: {station.longitude}")
    serializer = FuelStationSerializer(stations, many=True)
    return Response(serializer.data)