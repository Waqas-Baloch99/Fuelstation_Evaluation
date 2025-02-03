from django.core.management.base import BaseCommand
from fuelapp.models import FuelStation
import pandas as pd
import random

class Command(BaseCommand):
    help = 'Import fuel prices from CSV file'
    
    STATE_CENTROIDS = {
        'AL': (32.806671, -86.791130),
        'AK': (61.370716, -152.404419),
        'AZ': (33.729759, -111.431221),
        'AR': (34.969704, -92.373123),
        'CA': (36.116203, -119.681564),
        'CO': (39.059811, -105.311104),
        'CT': (41.597782, -72.755371),
        'DE': (39.318523, -75.507141),
        'FL': (27.766279, -81.686783),
        'GA': (33.040619, -83.643074),
        'HI': (21.094318, -157.498337),
        'ID': (44.240459, -114.478828),
        'IL': (40.349457, -88.986137),
        'IN': (39.849426, -86.258278),
        'IA': (42.011539, -93.210526),
        'KS': (38.526600, -96.726486),
        'KY': (37.668140, -84.670067),
        'LA': (31.169546, -91.867805),
        'ME': (44.693947, -69.381927),
        'MD': (39.063946, -76.802101),
        'MA': (42.230171, -71.530106),
        'MI': (43.326618, -84.536095),
        'MN': (45.694454, -93.900192),
        'MS': (32.741646, -89.678696),
        'MO': (38.456085, -92.288368),
        'MT': (46.921925, -110.454353),
        'NE': (41.125370, -98.268082),
        'NV': (38.313515, -117.055374),
        'NH': (43.452492, -71.563896),
        'NJ': (40.298904, -74.521011),
        'NM': (34.840515, -106.248482),
        'NY': (42.165726, -74.948051),
        'NC': (35.630066, -79.806419),
        'ND': (47.528912, -99.784012),
        'OH': (40.388783, -82.764915),
        'OK': (35.565342, -96.928917),
        'OR': (44.572021, -122.070938),
        'PA': (40.590752, -77.209755),
        'RI': (41.680893, -71.511780),
        'SC': (33.856892, -80.945007),
        'SD': (44.299782, -99.438828),
        'TN': (35.747845, -86.692345),
        'TX': (31.054487, -97.563461),
        'UT': (40.150032, -111.862434),
        'VT': (44.045876, -72.710686),
        'VA': (37.769337, -78.169968),
        'WA': (47.400902, -121.490494),
        'WV': (38.491226, -80.954453),
        'WI': (44.268543, -89.616508),
        'WY': (42.755966, -107.302490)
    }

    def get_state_coordinates(self, state):
        state = state.upper().strip()
        base_lat, base_lon = self.STATE_CENTROIDS.get(state, (37.0902, -95.7129))
        return {
            'lat': round(base_lat + random.uniform(-1.5, 1.5), 6),
            'lon': round(base_lon + random.uniform(-1.5, 1.5), 6)
        }

    def handle(self, *args, **options):
        try:
            csv_file = 'D:/Development/fuel/fuel_supply/fuelapp/fuel-prices-for-be-assessment.csv'
            df = pd.read_csv(csv_file)
            
            required_columns = ['OPIS Truckstop ID', 'Truckstop Name', 'Address', 
                              'City', 'State', 'Rack ID', 'Retail Price']
            
            if not all(col in df.columns for col in required_columns):
                missing = [col for col in required_columns if col not in df.columns]
                raise ValueError(f"Missing columns: {', '.join(missing)}")

            df = df.dropna(subset=required_columns)
            df = df[df['Retail Price'] > 0]
            
            FuelStation.objects.all().delete()
            
            batch_size = 100
            stations = []
            
            for _, row in df.iterrows():
                try:
                    state = str(row['State']).strip().upper()[:2]
                    coords = self.get_state_coordinates(state)
                    
                    stations.append(FuelStation(
                        opis=str(row['OPIS Truckstop ID']),
                        truck_stop=str(row['Truckstop Name']),
                        address=str(row['Address']),
                        city=str(row['City']),
                        state=state,
                        rack_id=str(row['Rack ID']),
                        retail_price=float(row['Retail Price']),
                        latitude=coords['lat'],
                        longitude=coords['lon']
                    ))
                    
                    if len(stations) >= batch_size:
                        FuelStation.objects.bulk_create(stations)
                        stations = []
                        self.stdout.write(f"Imported {batch_size} stations...")
                        
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f"Skipping row {_}: {str(e)}"))

            if stations:
                FuelStation.objects.bulk_create(stations)
                
            self.stdout.write(self.style.SUCCESS(f"Successfully imported {len(df)} fuel stations"))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Import failed: {str(e)}"))