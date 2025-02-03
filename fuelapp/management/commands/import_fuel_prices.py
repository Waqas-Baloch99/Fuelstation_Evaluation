from django.core.management.base import BaseCommand
from fuelapp.models import FuelStation
import pandas as pd

class Command(BaseCommand):
    help = 'Import fuel prices from CSV file'

    def handle(self, *args, **options):
        try:
            # Clear existing data
            FuelStation.objects.all().delete()
            
            # Read CSV file
            csv_file = 'D:/Development/fuel/fuel_supply/fuelapp/fuel-prices-for-be-assessment.csv'
            df = pd.read_csv(csv_file)
            
            # Print first few rows and data info
            self.stdout.write("CSV Data Info:")
            self.stdout.write(str(df.info()))
            self.stdout.write("\nFirst few rows:")
            self.stdout.write(str(df.head()))
            self.stdout.write(f"\nTotal rows in CSV: {len(df)}")
            self.stdout.write(f"Oklahoma stations: {len(df[df['State'] == 'OK'])}")
            
            # Oklahoma stations coordinates
            station_coords = {
                'WOODSHED OF BIG CABIN': {'lat': 36.5432, 'lon': -95.2168},  # Big Cabin
                'LOVES TRAVEL STOP #770': {'lat': 36.5432, 'lon': -95.2168},  # Big Cabin
                'TA TULSA': {'lat': 36.1563, 'lon': -95.9928},  # Tulsa
                'FLYING J #721': {'lat': 36.1871, 'lon': -95.7594},  # Catoosa
                'LOVES TRAVEL STOP #387': {'lat': 36.3126, 'lon': -95.6163},  # Claremore
                'PETRO STOPPING CENTER #389': {'lat': 36.6387, 'lon': -95.1545},  # Vinita
                'PILOT TRAVEL CENTER #489': {'lat': 36.1540, 'lon': -95.9928},  # Tulsa
                'QUIKTRIP #7': {'lat': 36.1540, 'lon': -95.9928},  # Tulsa
            }
            
            count = 0
            for index, row in df.iterrows():
                try:
                    # Print each row being processed
                    self.stdout.write(f"\nProcessing row {index}:")
                    self.stdout.write(f"Truck Stop: {row['Truckstop Name']}")
                    self.stdout.write(f"City: {row['City']}")
                    self.stdout.write(f"State: {row['State']}")
                    
                    # Only create stations in Oklahoma
                    if row['State'] == 'OK':
                        truck_stop = row['Truckstop Name']
                        coords = station_coords.get(truck_stop)
                        
                        # If no specific coordinates, use city coordinates
                        if not coords:
                            if 'TULSA' in row['City'].upper():
                                coords = {'lat': 36.1540, 'lon': -95.9928}
                            elif 'BIG CABIN' in row['City'].upper():
                                coords = {'lat': 36.5432, 'lon': -95.2168}
                            elif 'CATOOSA' in row['City'].upper():
                                coords = {'lat': 36.1871, 'lon': -95.7594}
                        
                        if coords:
                            FuelStation.objects.create(
                                opis=str(row['OPIS Truckstop ID']),
                                truck_stop=truck_stop,
                                address=str(row['Address']),
                                city=str(row['City']),
                                state=str(row['State']),
                                rack_id=str(row['Rack ID']),
                                retail_price=float(row['Retail Price']),
                                latitude=coords['lat'],
                                longitude=coords['lon']
                            )
                            count += 1
                            self.stdout.write(
                                self.style.SUCCESS(
                                    f'Imported {truck_stop} in {row["City"]}, OK with coordinates: {coords}'
                                )
                            )
                        else:
                            self.stdout.write(
                                self.style.WARNING(
                                    f'No coordinates found for {truck_stop} in {row["City"]}, OK'
                                )
                            )
                
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f'Error on row {index + 1}: {str(e)}')
                    )
            
            self.stdout.write(
                self.style.SUCCESS(f'Successfully imported {count} Oklahoma fuel stations')
            )
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Failed to import fuel prices: {str(e)}')
            )