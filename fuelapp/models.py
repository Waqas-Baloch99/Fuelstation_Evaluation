from django.db import models

# Create your models here.

class FuelStation(models.Model):
    opis = models.CharField(max_length=50)
    truck_stop = models.CharField(max_length=200)
    address = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=2)
    rack_id = models.CharField(max_length=50)
    retail_price = models.DecimalField(max_digits=5, decimal_places=3)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    last_updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.truck_stop} - {self.city}, {self.state}"

class Route(models.Model):
    start_location = models.CharField(max_length=255)
    end_location = models.CharField(max_length=255)
    total_distance = models.FloatField()  # in miles
    total_cost = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Route from {self.start_location} to {self.end_location}"

class FuelStop(models.Model):
    route = models.ForeignKey(Route, related_name='fuel_stops', on_delete=models.CASCADE)
    fuel_station = models.ForeignKey(FuelStation, on_delete=models.CASCADE)
    distance_from_start = models.FloatField()  # distance in miles from start
    fuel_amount = models.FloatField()  # amount of fuel in gallons
    cost = models.DecimalField(max_digits=8, decimal_places=2)
    stop_number = models.IntegerField()  # order of stops

    class Meta:
        ordering = ['stop_number']

    def __str__(self):
        return f"Stop {self.stop_number} at {self.fuel_station.name}"
