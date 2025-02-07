from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import api_view
from rest_framework import status
from django.views.generic import TemplateView
from django.core.cache import cache
from rest_framework.pagination import PageNumberPagination
import requests
from .models import FuelStation
from .serializers import  RouteRequestSerializer
from django.conf import settings
from geopy.geocoders import Nominatim
import logging
from django.views.decorators.csrf import ensure_csrf_cookie
from django.utils.decorators import method_decorator
from django.core.cache import cache
from django.contrib.sessions.backends.base import UpdateError
from shapely.geometry import LineString, Point
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json

CACHE_TIMEOUT = 300  # 5 minutes cache timeout, adjust as needed

logger = logging.getLogger(__name__)
class RoutePlannerTemplateView(TemplateView):
    template_name = 'fuelapp/route_planner.html'

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs)

class FuelStationPagination(PageNumberPagination):
    page_size = 100
    page_size_query_param = 'page_size'
    max_page_size = 8000

class RoutePlannerView(APIView):
    def cached_geocode(self, location):
        cache_key = f"geocode_{location.lower().replace(' ', '_')}"
        cached_result = cache.get(cache_key)
        
        if cached_result:
            return cached_result
        
        geolocator = Nominatim(user_agent="fuel_planner")
        result = geolocator.geocode(location)
        
        if result:
            cache.set(cache_key, result, CACHE_TIMEOUT)
        
        return result

    def get_osrm_route(self, start_lon, start_lat, end_lon, end_lat):
        cache_key = f"route_{start_lon}_{start_lat}_{end_lon}_{end_lat}"
        cached_route = cache.get(cache_key)
        
        if cached_route:
            return cached_route
        
        try:
            osrm_url = f"{settings.OSRM_ENDPOINT}/route/v1/driving/{start_lon},{start_lat};{end_lon},{end_lat}?overview=full&geometries=geojson"
            response = requests.get(osrm_url, timeout=10)
            route_data = response.json()
            
            if response.status_code != 200:
                logger.error(f"OSRM API error: Status {response.status_code}")
                return None
                
            if route_data.get('code') != 'Ok':
                logger.error(f"OSRM route error: {route_data.get('message', 'Unknown error')}")
                return None
            
            if not route_data.get('routes') or not route_data['routes'][0].get('geometry'):
                logger.error("OSRM response missing route geometry")
                return None
                
            cache.set(cache_key, route_data, CACHE_TIMEOUT)
            return route_data
            
        except requests.exceptions.RequestException as e:
            logger.error(f"OSRM request failed: {str(e)}")
            return None
        except ValueError as e:
            logger.error(f"Invalid OSRM response: {str(e)}")
            return None

    def find_nearest_stations(self, lat, lon, radius=100, limit=10):  # Increased radius and limit
        try:
            stations = FuelStation.objects.raw('''
                SELECT *, 
                       (6371 * acos(cos(radians(%s)) * cos(radians(latitude)) * 
                        cos(radians(longitude) - radians(%s)) + sin(radians(%s)) * 
                        sin(radians(latitude)))) * 0.621371 AS distance
                FROM fuelapp_fuelstation
                WHERE retail_price IS NOT NULL
                  AND latitude BETWEEN %s - %s AND %s + %s
                  AND longitude BETWEEN %s - %s AND %s + %s
                ORDER BY retail_price ASC, distance ASC
                LIMIT %s
            ''', [
                lat, lon, lat,
                lat, radius/69, lat, radius/69,  # Convert radius to degrees
                lon, radius/69, lon, radius/69,
                limit
            ])

            return [{
                'id': station.id,
                'truck_stop': station.truck_stop,
                'address': station.address,
                'city': station.city,
                'state': station.state,
                'retail_price': float(station.retail_price),
                'latitude': float(station.latitude),
                'longitude': float(station.longitude),
                'route_distance': round(float(station.distance), 1) if hasattr(station, 'distance') else None
            } for station in stations]

        except Exception as e:
            logger.error(f"Error finding stations: {str(e)}")
            return []



    def post(self, request):
        try:
            serializer = RouteRequestSerializer(data=request.data)
            if not serializer.is_valid():
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

            start = serializer.validated_data['start_location']
            end = serializer.validated_data['end_location']

            # Geocode locations
            start_location = self.cached_geocode(start)
            end_location = self.cached_geocode(end)
            
            if not start_location:
                return Response({"error": f"Could not find location: {start}"}, status=400)
            if not end_location:
                return Response({"error": f"Could not find location: {end}"}, status=400)

            # Get route
            route_data = self.get_osrm_route(
                start_location.longitude, start_location.latitude,
                end_location.longitude, end_location.latitude
            )
            
            if not route_data:
                return Response({
                    "error": "Route calculation failed",
                    "details": "Could not calculate route between the specified locations"
                }, status=400)

            # Extract route coordinates and create LineString
            coordinates = route_data['routes'][0]['geometry']['coordinates']
            route_line = LineString([(coord[0], coord[1]) for coord in coordinates])  # (lon, lat)

            # Define search buffer (10 miles)
            buffer_miles = 10
            buffer_deg = buffer_miles / 69  # Approximate degrees

            # Calculate expanded bounds for station query
            min_lon, min_lat, max_lon, max_lat = route_line.bounds
            expanded_bounds = (
                max(min_lat - buffer_deg, -90),
                max(min_lon - buffer_deg, -180),
                min(max_lat + buffer_deg, 90),
                min(max_lon + buffer_deg, 180)
            )

            # Query stations within expanded bounds
            stations = FuelStation.objects.filter(
                latitude__range=(expanded_bounds[0], expanded_bounds[2]),
                longitude__range=(expanded_bounds[1], expanded_bounds[3]),
                retail_price__isnull=False
            ).values('id', 'truck_stop', 'address', 'city', 'state', 
                    'retail_price', 'latitude', 'longitude')

            # Calculate exact distance from each station to the route
            valid_stations = []
            for station in stations:
                station_point = Point(station['longitude'], station['latitude'])
                closest_distance = route_line.distance(station_point) * 69  # Approx miles

                if closest_distance <= buffer_miles:
                    station_data = {
                        **station,
                        'route_distance': round(closest_distance, 1),
                        'retail_price': float(station['retail_price'])
                    }
                    valid_stations.append(station_data)

            # Remove duplicates and sort
            unique_stations = {s['id']: s for s in valid_stations}.values()
            sorted_stations = sorted(unique_stations, key=lambda x: (x['retail_price'], x['route_distance']))

            # Prepare response data
            total_distance = route_data['routes'][0]['distance'] / 1609.34  # meters to miles
            total_fuel = total_distance / settings.FUEL_ECONOMY
            best_price = min(s['retail_price'] for s in sorted_stations) if sorted_stations else 0
            total_cost = total_fuel * best_price

            response_data = {
                'start_location': start,
                'end_location': end,
                'start_coords': [start_location.latitude, start_location.longitude],
                'end_coords': [end_location.latitude, end_location.longitude],
                'total_distance': round(total_distance, 1),
                'total_fuel_needed': round(total_fuel, 2),
                'total_cost': round(total_cost, 2),
                'duration': route_data['routes'][0]['duration'] / 60,  # seconds to minutes
                'route_geometry': route_data['routes'][0]['geometry'],
                'stations': sorted_stations[:50],  # Top 50 by price/distance
                'best_price': best_price
            }

            return Response(response_data)

        except Exception as e:
            logger.error(f"Route calculation error: {str(e)}", exc_info=True)
            return Response({
                "error": "Internal server error",
                "details": str(e) if settings.DEBUG else None
            }, status=500)

@api_view(['GET'])
def fuel_stations(request):
    try:
        cache_key = 'all_fuel_stations'
        cached_data = cache.get(cache_key)
        
        if cached_data:
            return Response(cached_data)

        stations = FuelStation.objects.filter(
            latitude__isnull=False,
            longitude__isnull=False,
            retail_price__isnull=False,
            city__isnull=False,
            state__isnull=False
        ).values(
            'id', 'truck_stop', 'address', 'city', 
            'state', 'retail_price', 'latitude', 'longitude'
        ).order_by('retail_price')

        def get_location_coordinates(station):
            cache_key = f"station_location_{station['city']}_{station['state']}"
            cached_coords = cache.get(cache_key)
            
            if cached_coords:
                return cached_coords

            try:
                if station['latitude'] and station['longitude']:
                    coords = {
                        'latitude': float(station['latitude']),
                        'longitude': float(station['longitude'])
                    }
                else:
                    address = f"{station['address']}, {station['city']}, {station['state']}, USA"
                    geolocator = Nominatim(user_agent="fuel_planner")
                    location = geolocator.geocode(address)
                    if location:
                        coords = {
                            'latitude': location.latitude,
                            'longitude': location.longitude
                        }
                    else:
                        return None
                
                cache.set(cache_key, coords, CACHE_TIMEOUT)
                return coords
            except Exception as e:
                logger.error(f"Geocoding error for {station['city']}, {station['state']}: {str(e)}")
                return None

        data = []
        for station in stations:
            coords = get_location_coordinates(station)
            if coords:
                data.append({
                    **station,
                    'retail_price': float(station['retail_price']),
                    'latitude': coords['latitude'],
                    'longitude': coords['longitude']
                })

        cache.set(cache_key, data, CACHE_TIMEOUT)
        return Response(data)
        
    except Exception as e:
        logger.error(f"Error fetching fuel stations: {str(e)}")
        return Response(
            {"error": "Could not fetch fuel stations"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@csrf_exempt
def calculate_station_route(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST method is allowed'}, status=405)
    
    try:
        data = json.loads(request.body)
        start_coords = data.get('start_coords')
        station_coords = data.get('station_coords')

        if not start_coords or not station_coords:
            return JsonResponse({'error': 'Missing coordinates'}, status=400)

        # Convert coordinates to string format required by OSRM
        start_str = f"{start_coords[1]},{start_coords[0]}"
        station_str = f"{station_coords[1]},{station_coords[0]}"

        # Call OSRM service for route
        osrm_url = f"{settings.OSRM_SERVER}/route/v1/driving/{start_str};{station_str}"
        params = {
            'overview': 'full',
            'geometries': 'geojson',
            'steps': 'true'
        }
        
        response = requests.get(osrm_url, params=params)
        route_data = response.json()

        if response.status_code != 200:
            return JsonResponse({'error': 'Route calculation failed'}, status=500)

        return JsonResponse({
            'route_geometry': route_data['routes'][0]['geometry'],
            'distance': route_data['routes'][0]['distance'],
            'duration': route_data['routes'][0]['duration']
        })

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON data'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

def your_view_function(request):  # replace with actual function name
    try:
        # your code here
        pass
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)