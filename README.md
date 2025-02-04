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
```

# API Testing Guide with Postman

## Route Planning API

### Base URL
```
http://localhost:8000/api/
```

### Endpoints

1. Get Fuel Stations
- **Endpoint:** `/fuel-stations/`
- **Method:** GET
- **Description:** Retrieves all fuel stations
- **No request body required**

2. Calculate Route
- **Endpoint:** `/route/`
- **Method:** POST
- **Headers:**
  - Content-Type: application/json
  - X-CSRFToken: [your_csrf_token]
- **Request Body:**
```json
{
    "start_location": "New York, NY",
    "end_location": "Los Angeles, CA"
}
```

### Testing Steps in Postman

1. **Set up the environment:**
   - Open Postman
   - Create a new collection named "Fuel Route Planner"

2. **Testing GET Fuel Stations:**
   - Create new request
   - Select GET method
   - Enter URL: `http://localhost:8000/api/fuel-stations/`
   - Click Send

3. **Testing Route Calculation:**
   - Create new request
   - Select POST method
   - Enter URL: `http://localhost:8000/api/route/`
   - Go to Headers tab:
     - Add `Content-Type: application/json`
     - Add `X-CSRFToken: [copy from browser cookie]`
   - Go to Body tab:
     - Select "raw" and "JSON"
     - Enter the request body as shown above
   - Click Send

### Getting CSRF Token
1. Open your browser
2. Visit your application
3. Open Developer Tools (F12)
4. Go to Application > Cookies
5. Copy the value of csrftoken
