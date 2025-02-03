# Fuel Station Route Planner 🚗⛽

[![GitHub stars](https://img.shields.io/github/stars/Waqas-Baloch99/Fuelstation_Evaluation?style=social)](https://github.com/Waqas-Baloch99/Fuelstation_Evaluation)
[![Django](https://img.shields.io/badge/Django-4.2-092E20?logo=django&logoColor=green)](https://www.djangoproject.com/)
[![OpenStreetMap](https://img.shields.io/badge/OpenStreetMap-7EBC6F?logo=openstreetmap&logoColor=white)](https://www.openstreetmap.org/)

A web application that calculates optimal fuel stops for long-distance journeys within the USA, prioritizing cost-effectiveness based on current fuel prices.

**Repository**: [github.com/Waqas-Baloch99/Fuelstation_Evaluation](https://github.com/Waqas-Baloch99/Fuelstation_Evaluation)


## Features ✨

- **Route Optimization** between any two US locations
- **Cost Calculation** based on real fuel prices
- **Interactive Map Visualization** with Leaflet.js
- **500-Mile Range Simulation** for electric vehicles
- **CSV Data Import** for fuel stations
- **REST API** for route calculations

## Installation 🛠️

```bash
# Clone repository
git clone https://github.com/Waqas-Baloch99/Fuelstation_Evaluation.git
cd Fuelstation_Evaluation

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set up database
python manage.py migrate

# Import sample data (optional)
python manage.py import_fuel_prices fuelapp/data/sample_fuel_prices.csv

# Start server
python manage.py runserver
