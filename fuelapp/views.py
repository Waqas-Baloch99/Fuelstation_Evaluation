from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import api_view
from rest_framework import status
from django.views.generic import TemplateView
from django.conf import settings
from django.core.cache import cache
from django.db.models import F, FloatField, Q
from django.db.models.functions import Cast, Radians, Power, Sin, Cos, ATan2, Sqrt
import requests
import logging
import time
import math
import polyline
from geopy.distance import geodesic
from geopy.geocoders import Nominatim
from .models import FuelStation, Route, FuelStop
from .serializers import RouteSerializer, RouteRequestSerializer, FuelStationSerializer

logger = logging.getLogger(__name__)
GEOCODING_CACHE_TIMEOUT = 86400  # 24 hours in seconds
MAX_STATIONS_SEARCH = 500  # Maximum stations to consider for optimal stop

class RoutePlannerTemplateView(TemplateView):
    template_name = 'fuelapp/route_planner.html'

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs)

class RoutePlannerView(APIView):
    def post(self, request):
        start_time = time.time()
        serializer = RouteRequestSerializer(data=request.data)
        
        if not serializer.is_valid():
            logger.warning("Invalid request data: %s", serializer.errors)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            start = serializer.validated_data['start_location']
            end = serializer.validated_data['end_location']
            
            # Cache geocoding results
            start_location = self.cached_geocode(start)
            end_location = self.cached_geocode(end)
            
            if not start_location or not end_location:
                logger.error("Geocoding failed for start: %s or end: %s", start, end)
                return Response(
                    {"error": "Could not find one or both locations. Please check the addresses."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Find stations near both start and end
            start_stations = self.find_stations_near_location(
                start_location.latitude, 
                start_location.longitude
            )
            end_stations = self.find_stations_near_location(
                end_location.latitude, 
                end_location.longitude
            )

            # Get optimized route
            try:
                route_data = self.get_osrm_route(
                    start_location.longitude, start_location.latitude,
                    end_location.longitude, end_location.latitude
                )
                
                if not route_data.get('routes') or not route_data['routes'][0].get('distance'):
                    logger.error("Invalid route data received: %s", route_data)
                    return Response(
                        {"error": "Could not calculate route between these locations"},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                total_distance = route_data['routes'][0]['distance'] / 1609.34  # meters to miles
                
                # Create route and calculate fuel stops
                route = self.create_route(start, end, total_distance)
                fuel_stops = self.calculate_fuel_stops(
                    start_location, 
                    end_location, 
                    total_distance, 
                    route,
                    route_data['routes'][0]['geometry']
                )
                
                route.total_cost = sum(stop.cost for stop in fuel_stops)
                route.save()
                
                logger.info("Route calculation completed in %.2fs", time.time()-start_time)
                
                response_data = {
                    'start_location': start,
                    'end_location': end,
                    'start_coords': [start_location.latitude, start_location.longitude],
                    'end_coords': [end_location.latitude, end_location.longitude],
                    'total_distance': total_distance,
                    'total_fuel_needed': round(total_distance / settings.FUEL_ECONOMY, 2),
                    'total_cost': route.total_cost,
                    'route_geometry': route_data['routes'][0]['geometry'],
                    'nearby_stations': {
                        'start': [
                            {
                                'truck_stop': s['truck_stop'],
                                'address': s['address'],
                                'city': s['city'],
                                'state': s['state'],
                                'retail_price': float(s['retail_price']),
                                'distance': round(s['distance'], 1),
                                'latitude': float(s['latitude']),
                                'longitude': float(s['longitude'])
                            }
                            for s in start_stations
                        ],
                        'end': [
                            {
                                'truck_stop': s['truck_stop'],
                                'address': s['address'],
                                'city': s['city'],
                                'state': s['state'],
                                'retail_price': float(s['retail_price']),
                                'distance': round(s['distance'], 1),
                                'latitude': float(s['latitude']),
                                'longitude': float(s['longitude'])
                            }
                            for s in end_stations
                        ]
                    },
                    'fuel_stops': [
                        {
                            'fuel_station': {
                                'truck_stop': stop.fuel_station.truck_stop,
                                'address': stop.fuel_station.address,
                                'city': stop.fuel_station.city,
                                'state': stop.fuel_station.state,
                                'retail_price': float(stop.fuel_station.retail_price),
                                'latitude': float(stop.fuel_station.latitude),
                                'longitude': float(stop.fuel_station.longitude)
                            },
                            'distance_from_start': stop.distance_from_start,
                            'fuel_amount': stop.fuel_amount,
                            'cost': float(stop.cost)
                        }
                        for stop in fuel_stops
                    ]
                }
                
                return Response(response_data)
                
            except requests.exceptions.RequestException as e:
                logger.error("OSRM service error: %s", str(e))
                return Response(
                    {"error": "Route calculation service is temporarily unavailable"},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE
                )
                
        except Exception as e:
            logger.exception("Route calculation error")
            return Response(
                {"error": f"Could not calculate route: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def cached_geocode(self, address):
        cache_key = f"geocode_{address}"
        if cached := cache.get(cache_key):
            return cached
            
        geolocator = Nominatim(user_agent="fuel_planner", timeout=10)
        try:
            location = geolocator.geocode(address, country_codes='us')
            if location:
                cache.set(cache_key, location, GEOCODING_CACHE_TIMEOUT)
                return location
        except Exception as e:
            logger.error("Geocoding error: %s", str(e))
        return None

    def get_osrm_route(self, start_lon, start_lat, end_lon, end_lat):
        cache_key = f"route_{start_lon}_{start_lat}_{end_lon}_{end_lat}"
        if cached := cache.get(cache_key):
            return cached
            
        url = f"{settings.OSRM_ENDPOINT}/route/v1/driving/{start_lon},{start_lat};{end_lon},{end_lat}?overview=full&geometries=geojson"
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        route_data = response.json()
        cache.set(cache_key, route_data, 3600)  # Cache for 1 hour
        return route_data

    def create_route(self, start, end, distance):
        return Route.objects.create(
            start_location=start,
            end_location=end,
            total_distance=distance,
            total_cost=0.0
        )

    def calculate_fuel_stops(self, start_loc, end_loc, total_distance, route, geometry):
        fuel_stops = []
        remaining_distance = total_distance
        
        try:
            # Extract route coordinates
            route_coords = [(coord[1], coord[0]) for coord in geometry['coordinates']]
            
            # Calculate number of stops needed based on fuel economy and tank range
            tank_range = settings.MAX_FUEL_RANGE * 0.8  # 80% of max range for safety
            num_stops_needed = max(1, math.ceil(total_distance / tank_range))
            
            logger.info(f"Planning route: {total_distance:.1f} miles, need {num_stops_needed} stops")
            
            # Calculate stop points
            for stop_num in range(num_stops_needed):
                # Calculate target distance for this stop
                target_distance = (stop_num + 1) * (total_distance / num_stops_needed)
                
                # Find corresponding point in route coordinates
                point_index = int((target_distance / total_distance) * len(route_coords))
                if point_index >= len(route_coords):
                    point_index = len(route_coords) - 1
                    
                point = route_coords[point_index]
                
                # Search for stations with increasing radius until found
                search_radius = 50  # Start with 50-mile radius
                station = None
                
                while not station and search_radius <= 200:  # Max 200-mile radius
                    station = self.find_optimal_station(point[0], point[1], max_distance=search_radius)
                    if not station:
                        search_radius *= 1.5  # Increase search radius by 50%
                        logger.info(f"No station found within {search_radius} miles, expanding search")
                
                if station:
                    # Calculate fuel needed for this segment
                    distance_covered = min(tank_range, remaining_distance)
                    fuel_needed = distance_covered / settings.FUEL_ECONOMY
                    fuel_cost = fuel_needed * float(station.retail_price)
                    
                    logger.info(f"Adding fuel stop: {station.truck_stop} at {distance_covered:.1f} miles")
                    
                    fuel_stops.append(FuelStop.objects.create(
                        route=route,
                        fuel_station=station,
                        distance_from_start=target_distance,
                        fuel_amount=fuel_needed,
                        cost=fuel_cost,
                        stop_number=len(fuel_stops) + 1
                    ))
                    
                    remaining_distance -= distance_covered
                else:
                    logger.warning(f"Could not find station near point {point}")
            
            # If no stops found, try finding any station along the route
            if not fuel_stops and total_distance > 0:
                # Try several points along the route
                test_points = [
                    (0.25, "quarter"), 
                    (0.5, "middle"), 
                    (0.75, "three-quarter")
                ]
                
                for ratio, desc in test_points:
                    index = int(len(route_coords) * ratio)
                    point = route_coords[index]
                    station = self.find_optimal_station(point[0], point[1], max_distance=200)
                    
                    if station:
                        logger.info(f"Found backup station at {desc} point: {station.truck_stop}")
                        fuel_needed = total_distance / settings.FUEL_ECONOMY
                        fuel_cost = fuel_needed * float(station.retail_price)
                        
                        fuel_stops.append(FuelStop.objects.create(
                            route=route,
                            fuel_station=station,
                            distance_from_start=total_distance * ratio,
                            fuel_amount=fuel_needed,
                            cost=fuel_cost,
                            stop_number=1
                        ))
                        break
            
            if fuel_stops:
                logger.info(f"Found {len(fuel_stops)} fuel stops for the route")
            else:
                logger.warning("No fuel stops found for the route")
            
            return fuel_stops
            
        except Exception as e:
            logger.error(f"Error calculating fuel stops: {str(e)}")
            return []

    def find_optimal_station(self, lat, lon, max_distance=100):
        try:
            # Calculate approximate search area with larger radius
            earth_radius = 3958.8  # miles
            delta_lat = (max_distance / earth_radius) * (180 / math.pi)
            delta_lon = (max_distance / (earth_radius * math.cos(lat * math.pi/180))) * (180 / math.pi)

            # First filter by bounding box
            stations = FuelStation.objects.filter(
                latitude__range=(lat - delta_lat, lat + delta_lat),
                longitude__range=(lon - delta_lon, lon + delta_lon),
                retail_price__isnull=False
            ).values('id', 'truck_stop', 'address', 'city', 'state', 
                    'retail_price', 'latitude', 'longitude')

            # Calculate actual distances and sort
            stations_with_distance = []
            for station in stations:
                try:
                    distance = geodesic(
                        (lat, lon),
                        (station['latitude'], station['longitude'])
                    ).miles
                    
                    if distance <= max_distance:
                        stations_with_distance.append({
                            **station,
                            'distance': distance
                        })
                except Exception as e:
                    logger.warning(f"Error calculating distance for station {station['id']}: {str(e)}")
                    continue

            # Sort by a weighted combination of price and distance
            def score_station(station):
                price = float(station['retail_price'])
                distance = station['distance']
                # Weight price more heavily than distance
                return price + (distance / max_distance) * 0.5

            stations_with_distance.sort(key=score_station)

            # Return the best station
            if stations_with_distance:
                best_station = stations_with_distance[0]
                logger.info(f"Found station: {best_station['truck_stop']} at {best_station['distance']:.1f} miles with price ${float(best_station['retail_price']):.3f}")
                return FuelStation.objects.get(id=best_station['id'])
            else:
                logger.warning(f"No stations found within {max_distance} miles of ({lat}, {lon})")
                # Try with an even larger radius if no stations found
                if max_distance < 200:  # Only retry once with larger radius
                    return self.find_optimal_station(lat, lon, max_distance * 2)
            
            return None
            
        except Exception as e:
            logger.error(f"Error finding optimal station: {str(e)}")
            return None

    def find_stations_near_location(self, lat, lon, radius=50, limit=5):
        """Find the cheapest stations near a location"""
        try:
            # Calculate search area
            earth_radius = 3958.8  # miles
            delta_lat = (radius / earth_radius) * (180 / math.pi)
            delta_lon = (radius / (earth_radius * math.cos(lat * math.pi/180))) * (180 / math.pi)

            # Find stations within bounding box
            stations = FuelStation.objects.filter(
                latitude__range=(lat - delta_lat, lat + delta_lat),
                longitude__range=(lon - delta_lon, lon + delta_lon),
                retail_price__isnull=False
            ).values('id', 'truck_stop', 'address', 'city', 'state', 
                    'retail_price', 'latitude', 'longitude')

            # Calculate actual distances and filter
            stations_with_distance = []
            for station in stations:
                try:
                    distance = geodesic(
                        (lat, lon),
                        (station['latitude'], station['longitude'])
                    ).miles
                    
                    if distance <= radius:
                        stations_with_distance.append({
                            **station,
                            'distance': distance
                        })
                except Exception as e:
                    logger.warning(f"Error calculating distance for station {station['id']}: {str(e)}")
                    continue

            # Sort by price and distance
            stations_with_distance.sort(key=lambda x: (float(x['retail_price']), x['distance']))
            return stations_with_distance[:limit]

        except Exception as e:
            logger.error(f"Error finding stations near location: {str(e)}")
            return []

    def create_error_response(self, message, start_loc, end_loc, distance, route_data):
        return Response({
            "error": f"{message}: {round(distance)} miles (max {settings.MAX_FUEL_RANGE} miles)",
            "start_coords": [start_loc.latitude, start_loc.longitude],
            "end_coords": [end_loc.latitude, end_loc.longitude],
            "total_distance": distance,
            "route_geometry": route_data['routes'][0]['geometry']
        }, status=status.HTTP_400_BAD_REQUEST)

    def create_success_response(self, route, start_loc, end_loc, distance, route_data):
        serializer = RouteSerializer(route)
        return Response({
            **serializer.data,
            'start_coords': [start_loc.latitude, start_loc.longitude],
            'end_coords': [end_loc.latitude, end_loc.longitude],
            'total_fuel_needed': round(distance / settings.FUEL_ECONOMY, 2),
            'route_geometry': route_data['routes'][0]['geometry']
        })

@api_view(['GET'])
def fuel_stations(request):
    try:
        queryset = FuelStation.objects.filter(
            latitude__isnull=False, 
            longitude__isnull=False
        ).values(
            'id', 'truck_stop', 'address', 
            'city', 'state', 'retail_price',
            'latitude', 'longitude'
        ).order_by('retail_price')
        
        # Convert to list for JSON serialization
        stations = list(queryset)
        
        return Response({
            'stations': stations,
            'total_stations': len(stations)
        })
    
    except Exception as e:
        logger.error("Fuel stations error: %s", str(e))
        return Response(
            {"error": "Could not retrieve stations"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )