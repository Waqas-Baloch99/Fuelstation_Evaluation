# views.py
from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import api_view
from rest_framework import status
from django.views.generic import TemplateView
from django.core.cache import cache
from django.db.models import F
from rest_framework.pagination import PageNumberPagination
import requests
from .models import FuelStation, Route, FuelStop
from .serializers import RouteSerializer, RouteRequestSerializer, FuelStationSerializer
from django.conf import settings
from geopy.distance import geodesic
from geopy.geocoders import Nominatim
import logging
import time
import math
import polyline
from django.views.decorators.csrf import ensure_csrf_cookie
from django.utils.decorators import method_decorator
from concurrent.futures import ThreadPoolExecutor
from django.core.cache import cache

logger = logging.getLogger(__name__)
CACHE_TIMEOUT = 86400  # 24 hours

@method_decorator(ensure_csrf_cookie, name='dispatch')
class RoutePlannerTemplateView(TemplateView):
    template_name = 'fuelapp/route_planner.html'

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs)

class FuelStationPagination(PageNumberPagination):
    page_size = 100
    page_size_query_param = 'page_size'
    max_page_size = 1000

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
        
        osrm_url = f"{settings.OSRM_ENDPOINT}/route/v1/driving/{start_lon},{start_lat};{end_lon},{end_lat}?overview=full&geometries=geojson"
        response = requests.get(osrm_url, timeout=10)
        route_data = response.json()
        
        if response.status_code == 200 and route_data.get('code') == 'Ok':
            cache.set(cache_key, route_data, CACHE_TIMEOUT)
            
        return route_data

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
                'distance': round(float(station.distance), 1)
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

            # Get locations
            start_location = self.cached_geocode(start)
            end_location = self.cached_geocode(end)

            if not start_location or not end_location:
                return Response(
                    {"error": "Could not find one or both locations"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Get route data
            route_data = self.get_osrm_route(
                start_location.longitude, start_location.latitude,
                end_location.longitude, end_location.latitude
            )

            if not route_data.get('routes'):
                return Response(
                    {"error": "Could not calculate route"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            total_distance = route_data['routes'][0]['distance'] / 1609.34
            total_fuel_needed = total_distance / settings.FUEL_ECONOMY

            # Get all stations along the route
            coordinates = route_data['routes'][0]['geometry']['coordinates']
            route_points = [
                (coord[1], coord[0]) for coord in coordinates[::len(coordinates)//5]
            ]  # Sample points along route

            all_stations = []
            for lat, lon in route_points:
                stations = self.find_nearest_stations(lat, lon)
                all_stations.extend(stations)

            # Remove duplicates and sort by price
            seen = set()
            unique_stations = []
            for station in all_stations:
                if station['id'] not in seen:
                    seen.add(station['id'])
                    unique_stations.append(station)

            unique_stations.sort(key=lambda x: (x['retail_price'], x['distance']))

            # Calculate best fuel price
            if unique_stations:
                min_price = min(s['retail_price'] for s in unique_stations)
                total_cost = total_fuel_needed * min_price
            else:
                total_cost = 0

            response_data = {
                'start_location': start,
                'end_location': end,
                'start_coords': [start_location.latitude, start_location.longitude],
                'end_coords': [end_location.latitude, end_location.longitude],
                'total_distance': total_distance,
                'total_fuel_needed': total_fuel_needed,
                'total_cost': total_cost,
                'route_geometry': route_data['routes'][0]['geometry'],
                'stations': unique_stations[:50],  # Return top 50 stations
                'best_price': min_price if unique_stations else 0
            }

            return Response(response_data)

        except Exception as e:
            logger.exception("Route calculation error")
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

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
            retail_price__isnull=False
        ).values(
            'id', 'truck_stop', 'address', 'city', 
            'state', 'retail_price', 'latitude', 'longitude'
        ).order_by('retail_price')[:1000]

        data = [{
            **station,
            'retail_price': float(station['retail_price']),
            'latitude': float(station['latitude']),
            'longitude': float(station['longitude'])
        } for station in stations]

        cache.set(cache_key, data, CACHE_TIMEOUT)
        return Response(data)
        
    except Exception as e:
        logger.error(f"Error fetching fuel stations: {str(e)}")
        return Response(
            {"error": "Could not fetch fuel stations"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )