from flask import Flask, render_template, request, session, jsonify, redirect, url_for, send_file
import requests
import json
from datetime import datetime, timedelta
import calendar
import random
import sqlite3
import time
from urllib.parse import urlencode
import secrets
import io
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
import os
import threading
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

app = Flask(__name__)
app.secret_key = 'your-super-secret-key-here-12345'

# Your API key from OpenWeatherMap
API_KEY = '262f1a565be35ad2653cb72a53f2be13'

# ===== GOOGLE OAUTH CONFIGURATION =====
# Replace with your actual Google OAuth credentials from Google Cloud Console
GOOGLE_CLIENT_ID = 'your-google-client-id.apps.googleusercontent.com'
GOOGLE_CLIENT_SECRET = 'your-google-client-secret'
GOOGLE_REDIRECT_URI = 'http://localhost:5000/google_callback'

# ===== FACEBOOK OAUTH CONFIGURATION =====
FACEBOOK_APP_ID = 'your-facebook-app-id'
FACEBOOK_APP_SECRET = 'your-facebook-app-secret'
FACEBOOK_REDIRECT_URI = 'http://localhost:5000/facebook_callback'

# ===== APPLE OAUTH CONFIGURATION (DEMO MODE) =====
APPLE_CLIENT_ID = 'com.weatherapp.service'
APPLE_REDIRECT_URI = 'http://localhost:5000/apple_callback'

# ===== DATABASE SETUP =====
def init_db():
    conn = sqlite3.connect('weather_app.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT,
            email TEXT,
            phone TEXT,
            verified BOOLEAN DEFAULT 0,
            social_provider TEXT,
            social_id TEXT,
            default_city TEXT,
            bio TEXT,
            temp_unit TEXT DEFAULT 'c',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create search history table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS search_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            city TEXT,
            temperature INTEGER,
            description TEXT,
            searched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # Create alerts table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            city TEXT,
            temp_threshold INTEGER,
            alert_type TEXT,
            is_active BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # Create widget tokens table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS widget_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            token TEXT UNIQUE,
            city TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # Add default demo users
    cursor.execute('SELECT * FROM users WHERE username = ?', ('admin',))
    if not cursor.fetchone():
        cursor.execute('''
            INSERT INTO users (username, password, email, verified)
            VALUES (?, ?, ?, ?)
        ''', ('admin', 'admin123', 'admin@example.com', 1))
    
    cursor.execute('SELECT * FROM users WHERE username = ?', ('user',))
    if not cursor.fetchone():
        cursor.execute('''
            INSERT INTO users (username, password, email, verified)
            VALUES (?, ?, ?, ?)
        ''', ('user', 'user123', 'user@example.com', 1))
    
    conn.commit()
    conn.close()

init_db()

# ===== DATABASE FUNCTIONS =====
def get_db_connection():
    conn = sqlite3.connect('weather_app.db')
    conn.row_factory = sqlite3.Row
    return conn

def get_user_by_username(username):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
    user = cursor.fetchone()
    conn.close()
    return user

def get_user_by_email(email):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE email = ?', (email,))
    user = cursor.fetchone()
    conn.close()
    return user

def create_user(username, password, email='', phone=''):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO users (username, password, email, phone, verified)
            VALUES (?, ?, ?, ?, ?)
        ''', (username, password, email, phone, 1))
        conn.commit()
        user_id = cursor.lastrowid
        conn.close()
        return user_id
    except:
        conn.close()
        return None

def get_user_profile(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
    user = cursor.fetchone()
    conn.close()
    return user

def update_user_profile(user_id, default_city=None, bio=None, temp_unit='c'):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE users 
        SET default_city = ?, bio = ?, temp_unit = ?
        WHERE id = ?
    ''', (default_city, bio, temp_unit, user_id))
    conn.commit()
    conn.close()

# ===== SEARCH HISTORY FUNCTIONS =====
def save_search_history(user_id, city, weather_data):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO search_history (user_id, city, temperature, description)
        VALUES (?, ?, ?, ?)
    ''', (user_id, city, weather_data.get('temperature'), weather_data.get('description')))
    conn.commit()
    conn.close()

def get_search_history(user_id, limit=20):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM search_history 
        WHERE user_id = ? 
        ORDER BY searched_at DESC 
        LIMIT ?
    ''', (user_id, limit))
    history = cursor.fetchall()
    conn.close()
    return history

def get_most_searched_cities(user_id, limit=5):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT city, COUNT(*) as count 
        FROM search_history 
        WHERE user_id = ? 
        GROUP BY city 
        ORDER BY count DESC 
        LIMIT ?
    ''', (user_id, limit))
    cities = cursor.fetchall()
    conn.close()
    return cities

# ===== ALERT FUNCTIONS =====
def save_user_alert(user_id, city, temp_threshold, alert_type='temperature'):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO user_alerts (user_id, city, temp_threshold, alert_type)
        VALUES (?, ?, ?, ?)
    ''', (user_id, city, temp_threshold, alert_type))
    conn.commit()
    conn.close()

def get_user_alerts(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM user_alerts 
        WHERE user_id = ? AND is_active = 1
        ORDER BY created_at DESC
    ''', (user_id,))
    alerts = cursor.fetchall()
    conn.close()
    return alerts

def delete_user_alert(alert_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE user_alerts SET is_active = 0 WHERE id = ?', (alert_id,))
    conn.commit()
    conn.close()

# ===== WIDGET FUNCTIONS =====
def generate_widget_token(user_id, city):
    token = secrets.token_urlsafe(16)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO widget_tokens (user_id, token, city)
        VALUES (?, ?, ?)
    ''', (user_id, token, city))
    conn.commit()
    conn.close()
    return token

def get_widget_data(token):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM widget_tokens WHERE token = ?
    ''', (token,))
    widget = cursor.fetchone()
    conn.close()
    return widget

# ===== WEATHER FUNCTIONS =====
def get_weather(city):
    url = f'https://api.openweathermap.org/data/2.5/weather?q={city}&appid={API_KEY}&units=metric'
    try:
        response = requests.get(url)
        data = response.json()
        if response.status_code == 200:
            return {
                'city': data.get('name', city.title()),
                'country': data['sys']['country'],
                'temperature': round(data['main']['temp']),
                'feels_like': round(data['main']['feels_like']),
                'description': data['weather'][0]['description'].title(),
                'humidity': data['main']['humidity'],
                'wind_speed': round(data['wind']['speed']),
                'icon': data['weather'][0]['icon'],
                'pressure': data['main']['pressure'],
                'visibility': data.get('visibility', 10000) // 1000,
                'sunrise': datetime.fromtimestamp(data['sys']['sunrise']).strftime('%H:%M'),
                'sunset': datetime.fromtimestamp(data['sys']['sunset']).strftime('%H:%M'),
                'lat': data['coord']['lat'], 'lon': data['coord']['lon'],
                'timezone': data.get('timezone', 0)
            }
        return None
    except:
        return None

def get_forecast(city):
    url = f'https://api.openweathermap.org/data/2.5/forecast?q={city}&appid={API_KEY}&units=metric'
    try:
        response = requests.get(url)
        data = response.json()
        if response.status_code == 200:
            forecast_list = []
            for i in range(0, 40, 8):
                if i < len(data['list']):
                    f = data['list'][i]
                    forecast_list.append({
                        'date': f['dt_txt'].split(' ')[0],
                        'day': datetime.strptime(f['dt_txt'].split(' ')[0], '%Y-%m-%d').strftime('%a'),
                        'temperature': round(f['main']['temp']),
                        'description': f['weather'][0]['description'].title(),
                        'icon': f['weather'][0]['icon'],
                        'humidity': f['main']['humidity']
                    })
            return forecast_list[:5]
        return None
    except:
        return None

def get_hourly_forecast(city):
    url = f'https://api.openweathermap.org/data/2.5/forecast?q={city}&appid={API_KEY}&units=metric'
    try:
        response = requests.get(url)
        data = response.json()
        if response.status_code == 200:
            hourly = []
            for i, item in enumerate(data['list'][:8]):
                hourly.append({
                    'time': datetime.fromtimestamp(item['dt']).strftime('%H:%M'),
                    'temp': round(item['main']['temp']),
                    'icon': item['weather'][0]['icon'],
                    'description': item['weather'][0]['description'].title()
                })
            return hourly
        return None
    except:
        return None

def get_air_quality(lat, lon):
    url = f'http://api.openweathermap.org/data/2.5/air_pollution?lat={lat}&lon={lon}&appid={API_KEY}'
    try:
        response = requests.get(url)
        data = response.json()
        if response.status_code == 200:
            aqi = data['list'][0]['main']['aqi']
            comp = data['list'][0]['components']
            aqi_labels = {
                1: {'label': 'Good', 'color': '#00e400', 'emoji': '🟢'},
                2: {'label': 'Fair', 'color': '#ffff00', 'emoji': '🟡'},
                3: {'label': 'Moderate', 'color': '#ff7e00', 'emoji': '🟠'},
                4: {'label': 'Poor', 'color': '#ff0000', 'emoji': '🔴'},
                5: {'label': 'Very Poor', 'color': '#99004c', 'emoji': '🟣'}
            }
            return {
                'aqi': aqi, 'label': aqi_labels[aqi]['label'],
                'color': aqi_labels[aqi]['color'], 'emoji': aqi_labels[aqi]['emoji'],
                'pm25': round(comp.get('pm2_5', 0), 1),
                'pm10': round(comp.get('pm10', 0), 1),
                'no2': round(comp.get('no2', 0), 1)
            }
        return None
    except:
        return None

def get_weather_alerts(weather):
    alerts = []
    if weather:
        temp = weather['temperature']
        desc = weather['description'].lower()
        wind = weather['wind_speed']
        
        if temp > 40:
            alerts.append({'type': 'danger', 'icon': '🔥', 'message': 'Extreme heat! Stay hydrated!'})
        elif temp > 35:
            alerts.append({'type': 'warning', 'icon': '☀️', 'message': 'Very hot! Drink water and stay in shade.'})
        elif temp < 5:
            alerts.append({'type': 'danger', 'icon': '❄️', 'message': 'Extreme cold! Dress warmly!'})
        elif temp < 10:
            alerts.append({'type': 'warning', 'icon': '🥶', 'message': 'Cold weather! Wear warm clothes.'})
        
        if 'rain' in desc:
            alerts.append({'type': 'info', 'icon': '🌧️', 'message': 'Rain expected! Take an umbrella.'})
        elif 'storm' in desc or 'thunder' in desc:
            alerts.append({'type': 'danger', 'icon': '⚡', 'message': 'Thunderstorms! Stay indoors.'})
        elif 'snow' in desc:
            alerts.append({'type': 'warning', 'icon': '❄️', 'message': 'Snow expected! Drive carefully.'})
        
        if wind > 40:
            alerts.append({'type': 'warning', 'icon': '💨', 'message': f'Strong winds ({wind} km/h)!'})
    return alerts

def get_weather_emoji(description):
    desc = description.lower()
    if 'clear' in desc: return '☀️'
    elif 'cloud' in desc: return '☁️'
    elif 'rain' in desc: return '🌧️'
    elif 'storm' in desc: return '⛈️'
    elif 'snow' in desc: return '❄️'
    elif 'fog' in desc: return '🌫️'
    else: return '🌤️'

def get_temperature_trend(forecast, unit='c'):
    if not forecast:
        return [], []
    labels, temps = [], []
    for day in forecast:
        labels.append(day['day'])
        temp = day['temperature']
        if unit == 'f':
            temp = round((temp * 9/5) + 32)
        temps.append(temp)
    return labels, temps

def get_weather_stats(forecast, unit='c'):
    if not forecast:
        return None
    temps = [day['temperature'] for day in forecast]
    rainy = sum(1 for day in forecast if 'rain' in day['description'].lower())
    return {
        'high': max(temps), 'low': min(temps),
        'average': round(sum(temps) / len(temps)),
        'rainy_days': rainy
    }

def get_greeting():
    hour = datetime.now().hour
    if 5 <= hour < 12:
        return "🌅 Good Morning", "Have a wonderful day ahead! ☀️"
    elif 12 <= hour < 17:
        return "☀️ Good Afternoon", "Hope you're having a great day! 🌤️"
    elif 17 <= hour < 21:
        return "🌆 Good Evening", "Relax and enjoy the evening! 🌅"
    else:
        return "🌙 Good Night", "Sweet dreams! 😴"

def get_current_time():
    return datetime.now().strftime('%H:%M')

def get_weather_radar(lat, lon):
    windy_embed = f'https://embed.windy.com/embed2.html?lat={lat}&lon={lon}&zoom=6&level=surface&overlay=radar&menu=&message=true&marker=&calendar=now&pressure=&type=map&location=coordinates&detail=&detailLat={lat}&detailLon={lon}&metricTemp=°C&metricWind=km/h'
    return {'windy_url': windy_embed}

def get_uv_index(lat, lon):
    url = f'https://api.openweathermap.org/data/2.5/uvi?lat={lat}&lon={lon}&appid={API_KEY}'
    try:
        response = requests.get(url)
        data = response.json()
        if response.status_code == 200:
            uv_value = data.get('value', 0)
            if uv_value <= 2:
                level = 'Low'; color = '#00e400'; advice = 'Safe to stay outside'
            elif uv_value <= 5:
                level = 'Moderate'; color = '#ffff00'; advice = 'Wear sunscreen and hat'
            elif uv_value <= 7:
                level = 'High'; color = '#ff7e00'; advice = 'Seek shade during midday'
            elif uv_value <= 10:
                level = 'Very High'; color = '#ff0000'; advice = 'Avoid sun exposure 11am-4pm'
            else:
                level = 'Extreme'; color = '#99004c'; advice = 'Stay indoors if possible'
            return {'value': round(uv_value, 1), 'level': level, 'color': color, 'advice': advice}
        return None
    except:
        return None

def get_world_time(timezone_offset):
    try:
        utc_time = datetime.utcnow()
        local_time = datetime.fromtimestamp(utc_time.timestamp() + timezone_offset)
        return local_time.strftime('%H:%M')
    except:
        return '--:--'

def get_nearby_cities(lat, lon):
    url = f'https://api.openweathermap.org/data/2.5/find?lat={lat}&lon={lon}&cnt=5&appid={API_KEY}&units=metric'
    try:
        response = requests.get(url)
        data = response.json()
        if response.status_code == 200:
            cities = []
            for item in data.get('list', []):
                cities.append({
                    'name': item.get('name', 'Unknown'),
                    'temperature': round(item['main']['temp']),
                    'description': item['weather'][0]['description'].title(),
                    'icon': item['weather'][0]['icon']
                })
            return cities
        return None
    except:
        return None

def get_weather_by_coords(lat, lon):
    url = f'https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={API_KEY}&units=metric'
    try:
        response = requests.get(url)
        data = response.json()
        if response.status_code == 200:
            return {
                'city': data.get('name', 'Unknown'),
                'country': data['sys']['country'],
                'temperature': round(data['main']['temp']),
                'feels_like': round(data['main']['feels_like']),
                'description': data['weather'][0]['description'].title(),
                'humidity': data['main']['humidity'],
                'wind_speed': round(data['wind']['speed']),
                'icon': data['weather'][0]['icon'],
                'pressure': data['main']['pressure'],
                'visibility': data.get('visibility', 10000) // 1000,
                'sunrise': datetime.fromtimestamp(data['sys']['sunrise']).strftime('%H:%M'),
                'sunset': datetime.fromtimestamp(data['sys']['sunset']).strftime('%H:%M'),
                'lat': data['coord']['lat'], 'lon': data['coord']['lon'],
                'timezone': data.get('timezone', 0)
            }
        return None
    except:
        return None

# ===== WEATHER COMPARISON =====
def compare_weather(city1, city2):
    weather1 = get_weather(city1)
    weather2 = get_weather(city2)
    
    if not weather1 or not weather2:
        return None
    
    return {
        'city1': weather1,
        'city2': weather2,
        'comparison': {
            'temp_diff': weather1['temperature'] - weather2['temperature'],
            'humidity_diff': weather1['humidity'] - weather2['humidity'],
            'wind_diff': weather1['wind_speed'] - weather2['wind_speed']
        }
    }

# ===== PDF GENERATION =====
def generate_weather_pdf(weather, forecast, city_name):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []
    
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#667eea'),
        spaceAfter=30
    )
    story.append(Paragraph(f"🌤️ Weather Report: {city_name}", title_style))
    story.append(Spacer(1, 12))
    
    story.append(Paragraph("Current Weather", styles['Heading2']))
    story.append(Spacer(1, 6))
    
    weather_data = [
        ['Temperature', f"{weather['temperature']}°C"],
        ['Feels Like', f"{weather['feels_like']}°C"],
        ['Description', weather['description']],
        ['Humidity', f"{weather['humidity']}%"],
        ['Wind Speed', f"{weather['wind_speed']} km/h"],
        ['Pressure', f"{weather['pressure']} hPa"],
        ['Visibility', f"{weather['visibility']} km"],
        ['Sunrise/Sunset', f"{weather['sunrise']} / {weather['sunset']}"]
    ]
    
    table = Table(weather_data, colWidths=[2*inch, 3*inch])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f7fafc')),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 12),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ('TOPPADDING', (0, 0), (-1, -1), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.grey)
    ]))
    story.append(table)
    story.append(Spacer(1, 20))
    
    if forecast:
        story.append(Paragraph("5-Day Forecast", styles['Heading2']))
        story.append(Spacer(1, 6))
        
        forecast_data = [['Day', 'Temperature', 'Description', 'Humidity']]
        for day in forecast:
            forecast_data.append([
                day['day'],
                f"{day['temperature']}°C",
                day['description'],
                f"{day['humidity']}%"
            ])
        
        forecast_table = Table(forecast_data, colWidths=[1.2*inch, 1.5*inch, 2.5*inch, 1.5*inch])
        forecast_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#667eea')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey)
        ]))
        story.append(forecast_table)
    
    story.append(Spacer(1, 30))
    story.append(Paragraph(f"Report generated on: {datetime.now().strftime('%Y-%m-%d %H:%M')}", styles['Normal']))
    
    doc.build(story)
    buffer.seek(0)
    return buffer

# ===== CHATBOT FUNCTION =====
def get_weather_chatbot_response(query, weather_data=None):
    """Smart chatbot responses - no API key needed!"""
    query_lower = query.lower()
    
    if weather_data:
        if 'temperature' in query_lower or 'hot' in query_lower or 'cold' in query_lower or 'temp' in query_lower:
            temp = weather_data['temperature']
            if temp > 30:
                return f"It's quite hot at {temp}°C! Stay hydrated and wear light clothes. ☀️"
            elif temp < 10:
                return f"It's cold at {temp}°C! Bundle up and stay warm. ❄️"
            else:
                return f"The temperature is {temp}°C, quite pleasant! 🌤️"
        
        if 'rain' in query_lower or 'umbrella' in query_lower or 'raining' in query_lower:
            desc = weather_data['description'].lower()
            if 'rain' in desc or 'shower' in desc or 'drizzle' in desc:
                return "It's raining! Don't forget your umbrella! 🌧️"
            elif 'thunder' in desc or 'storm' in desc:
                return "There might be storms! Stay indoors and stay safe! ⛈️"
            else:
                return "No rain expected right now. You can leave your umbrella at home! ☀️"
        
        if 'humidity' in query_lower or 'humid' in query_lower:
            humidity = weather_data['humidity']
            if humidity > 80:
                return f"The humidity is {humidity}%. It's very humid! Stay hydrated. 💧"
            elif humidity > 60:
                return f"The humidity is {humidity}%. It's a bit humid. 💧"
            else:
                return f"The humidity is {humidity}%. Quite comfortable! 👍"
        
        if 'wind' in query_lower:
            wind = weather_data['wind_speed']
            if wind > 30:
                return f"Wind speed is {wind} km/h. It's quite windy! Secure loose items. 💨"
            elif wind > 15:
                return f"Wind speed is {wind} km/h. Light breeze. 💨"
            else:
                return f"Wind speed is {wind} km/h. Calm weather! ☀️"
        
        if 'weather' in query_lower or 'current' in query_lower or 'now' in query_lower:
            return f"The current weather in {weather_data['city']} is {weather_data['temperature']}°C with {weather_data['description']}. Humidity is {weather_data['humidity']}% and wind speed is {weather_data['wind_speed']} km/h."
        
        if 'wear' in query_lower or 'dress' in query_lower or 'clothes' in query_lower:
            temp = weather_data['temperature']
            if temp > 30:
                return "It's hot! Wear light cotton clothes, sunglasses, and a hat. Don't forget sunscreen! 🕶️"
            elif temp < 10:
                return "It's cold! Wear a warm jacket, scarf, and gloves. Stay cozy! 🧣"
            else:
                return "The weather is pleasant! A light jacket or t-shirt should be fine. 👕"
    
    if 'hello' in query_lower or 'hi' in query_lower or 'hey' in query_lower:
        return "Hello! 👋 How can I help you with the weather today?"
    
    if 'help' in query_lower:
        return "I can help you with weather questions! Ask me about temperature, rain, humidity, wind, or what to wear. Just ask! 🌤️"
    
    if 'thank' in query_lower:
        return "You're welcome! Stay safe and enjoy the weather! 🌤️"
    
    if 'good morning' in query_lower:
        return "Good morning! 🌅 Ready to check today's weather?"
    
    if 'good night' in query_lower:
        return "Good night! 🌙 Sweet dreams!"
    
    if 'city' in query_lower:
        if weather_data:
            return f"You asked about {weather_data['city']}. {weather_data['temperature']}°C with {weather_data['description']}."
        return "Please tell me which city you want to know about. I need a city name to check the weather! 🏙️"
    
    return "I'm your weather assistant! 🌤️ Ask me about temperature, rain, humidity, wind, or what to wear. I'm here to help!"

# ===== TEMPERATURE ALERTS =====
def check_temperature_alerts(weather):
    alerts = []
    if weather:
        temp = weather['temperature']
        desc = weather['description'].lower()
        
        if temp > 40:
            alerts.append({
                'type': 'danger',
                'icon': '🔥',
                'title': 'Extreme Heat Alert!',
                'message': f'Temperature is {temp}°C. Stay hydrated!',
                'color': '#ef4444'
            })
        elif temp > 35:
            alerts.append({
                'type': 'warning',
                'icon': '☀️',
                'title': 'High Temperature Alert!',
                'message': f'Temperature is {temp}°C. Drink water!',
                'color': '#f59e0b'
            })
        elif temp < 0:
            alerts.append({
                'type': 'danger',
                'icon': '❄️',
                'title': 'Extreme Cold Alert!',
                'message': f'Temperature is {temp}°C. Dress warmly!',
                'color': '#3b82f6'
            })
        elif temp < 10:
            alerts.append({
                'type': 'warning',
                'icon': '🥶',
                'title': 'Cold Weather Alert!',
                'message': f'Temperature is {temp}°C. Wear warm clothes.',
                'color': '#60a5fa'
            })
        
        if 'storm' in desc or 'thunder' in desc:
            alerts.append({
                'type': 'danger',
                'icon': '⛈️',
                'title': 'Storm Alert!',
                'message': 'Thunderstorms expected. Stay indoors!',
                'color': '#8b5cf6'
            })
    return alerts

# ===== THEMES =====
THEMES = {
    'default': {'name': 'Default', 'class': 'theme-default'},
    'ocean': {'name': 'Ocean', 'class': 'theme-ocean'},
    'sunset': {'name': 'Sunset', 'class': 'theme-sunset'},
    'forest': {'name': 'Forest', 'class': 'theme-forest'},
    'night': {'name': 'Night', 'class': 'theme-night'}
}

# ===== LANGUAGES =====
LANGUAGES = {
    'en': {
        'name': 'English', 'flag': '🇬🇧', 
        'title': '🌤️ Weather App',
        'subtitle': 'Your personal weather assistant', 
        'placeholder': 'Search city...',
        'search': 'Search', 
        'recent': 'Recent', 
        'favorites': '⭐ Favorites',
        'add_favorite': '⭐ Add to Favorites', 
        'feels_like': 'Feels like',
        'humidity': 'Humidity', 
        'wind_speed': 'Wind Speed', 
        'pressure': 'Pressure',
        'visibility': 'Visibility', 
        'sunrise': 'Sunrise/Sunset',
        'forecast': '📊 5-Day Forecast', 
        'air_quality': 'Air Quality',
        'good': 'Good', 
        'fair': 'Fair', 
        'moderate': 'Moderate',
        'poor': 'Poor', 
        'very_poor': 'Very Poor', 
        'share': '📤 Share',
        'copy': '📋 Copy', 
        'error': 'Could not find weather for',
        'updated': 'Updated', 
        'location': '📍 Location', 
        'hourly': '⏰ Hourly Forecast',
        'stats': '📊 Weather Statistics', 
        'high': '🔥 High', 
        'low': '❄️ Low',
        'average': '📊 Average', 
        'rainy_days': '🌧️ Rainy Days',
        'nearby': '📍 Nearby Cities', 
        'radar': '📡 Weather Radar',
        'voice_assistant': '🎤 Voice Assistant', 
        'login': '🔐 Login',
        'logout': '🚪 Logout', 
        'username': 'Username', 
        'password': 'Password',
        'login_btn': 'Login', 
        'register': 'Register', 
        'welcome': 'Welcome',
        'invalid_credentials': 'Invalid username or password!',
        'register_success': 'Registration successful! Please login.',
        'username_exists': 'Username already exists!',
        'password_mismatch': 'Passwords do not match!',
        'confirm_password': 'Confirm Password',
        'uv_index': '☀️ UV Index', 
        'world_clock': '🕐 World Clock',
        'forgot_password': '🔑 Forgot Password?', 
        'reset_password': 'Reset Password',
        'email': 'Email Address', 
        'phone': 'Phone Number',
        'contact_method': 'Contact Method', 
        'send_otp': 'Send OTP',
        'verify_otp': 'Verify OTP', 
        'enter_otp': 'Enter OTP',
        'new_password': 'New Password', 
        'confirm_new_password': 'Confirm New Password',
        'password_reset_success': 'Password reset successfully! Please login.',
        'invalid_otp': 'Invalid OTP! Please try again.', 
        'otp_sent': 'OTP sent successfully!',
        'user_not_found': 'User not found!', 
        'contact_us': '📞 Contact Us',
        'contact_message': 'We are here to help!', 
        'our_contacts': 'Our Contacts',
        'compare': '📊 Compare Cities', 
        'chatbot': '🤖 Weather Chatbot',
        'widget': '📱 Weather Widget', 
        'admin': '⚙️ Admin Dashboard',
        'export_pdf': '📄 Export PDF', 
        'alerts': '🔔 Weather Alerts',
        'set_alert': 'Set Alert', 
        'temp_threshold': 'Temperature Threshold',
        'city': 'City', 
        'alert_type': 'Alert Type',
        'sign_in': 'Sign In',
        'or_continue_with': 'Or continue with',
        'forgot_password_link': 'Forgot Password?',
        'contact_us_link': 'Contact Us',
        'no_account': "Don't have an account? Register here",
        'demo_credentials': 'Demo Credentials:',
        'username_label': 'Username:',
        'password_label': 'Password:',
        'welcome_back': 'Welcome back',
        'sign_in_to_access': 'Sign in to access your weather dashboard'
    },
    'hi': {
        'name': 'Hindi', 'flag': '🇮🇳',
        'title': '🌤️ मौसम ऐप',
        'subtitle': 'आपका व्यक्तिगत मौसम सहायक',
        'placeholder': 'शहर खोजें...',
        'search': 'खोजें',
        'recent': 'हाल की खोजें',
        'favorites': '⭐ पसंदीदा',
        'add_favorite': '⭐ पसंदीदा में जोड़ें',
        'feels_like': 'महसूस होता है',
        'humidity': 'नमी',
        'wind_speed': 'हवा की गति',
        'pressure': 'दबाव',
        'visibility': 'दृश्यता',
        'sunrise': 'सूर्योदय/सूर्यास्त',
        'forecast': '📊 5-दिन का पूर्वानुमान',
        'air_quality': 'वायु गुणवत्ता',
        'good': 'अच्छा',
        'fair': 'ठीक',
        'moderate': 'मध्यम',
        'poor': 'खराब',
        'very_poor': 'बहुत खराब',
        'share': '📤 साझा करें',
        'copy': '📋 कॉपी करें',
        'error': 'के लिए मौसम नहीं मिला',
        'updated': 'अपडेट किया गया',
        'location': '📍 स्थान',
        'hourly': '⏰ घंटेवार पूर्वानुमान',
        'stats': '📊 मौसम आँकड़े',
        'high': '🔥 उच्चतम',
        'low': '❄️ न्यूनतम',
        'average': '📊 औसत',
        'rainy_days': '🌧️ बरसात के दिन',
        'nearby': '📍 आसपास के शहर',
        'radar': '📡 मौसम रडार',
        'voice_assistant': '🎤 आवाज सहायक',
        'login': '🔐 लॉगिन',
        'logout': '🚪 लॉगआउट',
        'username': 'उपयोगकर्ता नाम',
        'password': 'पासवर्ड',
        'login_btn': 'लॉगिन',
        'register': 'पंजीकरण',
        'welcome': 'स्वागत है',
        'invalid_credentials': 'अमान्य उपयोगकर्ता नाम या पासवर्ड!',
        'register_success': 'पंजीकरण सफल! कृपया लॉगिन करें।',
        'username_exists': 'उपयोगकर्ता नाम पहले से मौजूद है!',
        'password_mismatch': 'पासवर्ड मेल नहीं खाते!',
        'confirm_password': 'पासवर्ड की पुष्टि करें',
        'uv_index': '☀️ यूवी सूचकांक',
        'world_clock': '🕐 विश्व घड़ी',
        'forgot_password': '🔑 पासवर्ड भूल गए?',
        'reset_password': 'पासवर्ड रीसेट करें',
        'email': 'ईमेल पता',
        'phone': 'फोन नंबर',
        'contact_method': 'संपर्क विधि',
        'send_otp': 'OTP भेजें',
        'verify_otp': 'OTP सत्यापित करें',
        'enter_otp': 'OTP दर्ज करें',
        'new_password': 'नया पासवर्ड',
        'confirm_new_password': 'नए पासवर्ड की पुष्टि करें',
        'password_reset_success': 'पासवर्ड सफलतापूर्वक रीसेट! कृपया लॉगिन करें।',
        'invalid_otp': 'अमान्य OTP! कृपया पुनः प्रयास करें।',
        'otp_sent': 'OTP सफलतापूर्वक भेजा गया!',
        'user_not_found': 'उपयोगकर्ता नहीं मिला!',
        'contact_us': '📞 संपर्क करें',
        'contact_message': 'हम आपकी मदद के लिए यहाँ हैं!',
        'our_contacts': 'हमारे संपर्क',
        'compare': '📊 शहरों की तुलना करें',
        'chatbot': '🤖 मौसम चैटबॉट',
        'widget': '📱 मौसम विजेट',
        'admin': '⚙️ एडमिन डैशबोर्ड',
        'export_pdf': '📄 पीडीएफ निर्यात करें',
        'alerts': '🔔 मौसम अलर्ट',
        'set_alert': 'अलर्ट सेट करें',
        'temp_threshold': 'तापमान सीमा',
        'city': 'शहर',
        'alert_type': 'अलर्ट प्रकार',
        'sign_in': 'साइन इन करें',
        'or_continue_with': 'या इसके साथ जारी रखें',
        'forgot_password_link': 'पासवर्ड भूल गए?',
        'contact_us_link': 'संपर्क करें',
        'no_account': "खाता नहीं है? यहाँ रजिस्टर करें",
        'demo_credentials': 'डेमो क्रेडेंशियल्स:',
        'username_label': 'उपयोगकर्ता नाम:',
        'password_label': 'पासवर्ड:',
        'welcome_back': 'वापसी पर स्वागत है',
        'sign_in_to_access': 'अपने मौसम डैशबोर्ड तक पहुँचने के लिए साइन इन करें'
    },
    'ta': {
        'name': 'Tamil', 'flag': '🇮🇳',
        'title': '🌤️ வானிலை பயன்பாடு',
        'subtitle': 'உங்கள் தனிப்பட்ட வானிலை உதவியாளர்',
        'placeholder': 'நகரத்தை தேடுங்கள்...',
        'search': 'தேடு',
        'recent': 'சமீபத்தியவை',
        'favorites': '⭐ பிடித்தவை',
        'add_favorite': '⭐ பிடித்தவைகளில் சேர்',
        'feels_like': 'உணர்வது',
        'humidity': 'ஈரப்பதம்',
        'wind_speed': 'காற்றின் வேகம்',
        'pressure': 'அழுத்தம்',
        'visibility': 'தெரிவு',
        'sunrise': 'சூரிய உதயம்/அஸ்தமனம்',
        'forecast': '📊 5-நாள் முன்னறிவிப்பு',
        'air_quality': 'காற்று தரம்',
        'good': 'நல்லது',
        'fair': 'சரி',
        'moderate': 'மிதமான',
        'poor': 'மோசமான',
        'very_poor': 'மிக மோசமான',
        'share': '📤 பகிர்',
        'copy': '📋 நகல்',
        'error': 'க்கான வானிலை கிடைக்கவில்லை',
        'updated': 'புதுப்பிக்கப்பட்டது',
        'location': '📍 இருப்பிடம்',
        'hourly': '⏰ மணிநேர முன்னறிவிப்பு',
        'stats': '📊 வானிலை புள்ளிவிவரங்கள்',
        'high': '🔥 அதிகபட்சம்',
        'low': '❄️ குறைந்தபட்சம்',
        'average': '📊 சராசரி',
        'rainy_days': '🌧️ மழை நாட்கள்',
        'nearby': '📍 அருகிலுள்ள நகரங்கள்',
        'radar': '📡 வானிலை ரேடார்',
        'voice_assistant': '🎤 குரல் உதவியாளர்',
        'login': '🔐 உள்நுழைவு',
        'logout': '🚪 வெளியேறு',
        'username': 'பயனர்பெயர்',
        'password': 'கடவுச்சொல்',
        'login_btn': 'உள்நுழைவு',
        'register': 'பதிவு',
        'welcome': 'வரவேற்கிறோம்',
        'invalid_credentials': 'தவறான பயனர்பெயர் அல்லது கடவுச்சொல்!',
        'register_success': 'பதிவு வெற்றிகரமானது! தயவுசெய்து உள்நுழையவும்.',
        'username_exists': 'பயனர்பெயர் ஏற்கனவே உள்ளது!',
        'password_mismatch': 'கடவுச்சொற்கள் பொருந்தவில்லை!',
        'confirm_password': 'கடவுச்சொல்லை உறுதிப்படுத்து',
        'uv_index': '☀️ புற ஊதா குறியீடு',
        'world_clock': '🕐 உலக கடிகாரம்',
        'forgot_password': '🔑 கடவுச்சொல் மறந்துவிட்டதா?',
        'reset_password': 'கடவுச்சொல்லை மீட்டமைக்க',
        'email': 'மின்னஞ்சல் முகவரி',
        'phone': 'தொலைபேசி எண்',
        'contact_method': 'தொடர்பு முறை',
        'send_otp': 'OTP அனுப்பு',
        'verify_otp': 'OTP ஐ சரிபார்க்கவும்',
        'enter_otp': 'OTP ஐ உள்ளிடவும்',
        'new_password': 'புதிய கடவுச்சொல்',
        'confirm_new_password': 'புதிய கடவுச்சொல்லை உறுதிப்படுத்தவும்',
        'password_reset_success': 'கடவுச்சொல் வெற்றிகரமாக மீட்டமைக்கப்பட்டது! தயவுசெய்து உள்நுழையவும்.',
        'invalid_otp': 'தவறான OTP! மீண்டும் முயற்சிக்கவும்.',
        'otp_sent': 'OTP வெற்றிகரமாக அனுப்பப்பட்டது!',
        'user_not_found': 'பயனர் கிடைக்கவில்லை!',
        'contact_us': '📞 எங்களை தொடர்பு கொள்ளவும்',
        'contact_message': 'நாங்கள் உதவ இங்கே இருக்கிறோம்!',
        'our_contacts': 'எங்கள் தொடர்புகள்',
        'compare': '📊 நகரங்களை ஒப்பிடுக',
        'chatbot': '🤖 வானிலை அரட்டை',
        'widget': '📱 வானிலை விட்ஜெட்',
        'admin': '⚙️ நிர்வாக டாஷ்போர்டு',
        'export_pdf': '📄 PDF ஏற்றுமதி',
        'alerts': '🔔 வானிலை எச்சரிக்கைகள்',
        'set_alert': 'எச்சரிக்கை அமைக்கவும்',
        'temp_threshold': 'வெப்பநிலை வரம்பு',
        'city': 'நகரம்',
        'alert_type': 'எச்சரிக்கை வகை',
        'sign_in': 'உள்நுழையவும்',
        'or_continue_with': 'அல்லது இதனுடன் தொடரவும்',
        'forgot_password_link': 'கடவுச்சொல் மறந்துவிட்டதா?',
        'contact_us_link': 'எங்களை தொடர்பு கொள்ளவும்',
        'no_account': 'கணக்கு இல்லையா? இங்கே பதிவு செய்யவும்',
        'demo_credentials': 'டெமோ கிரெடென்ஷியல்கள்:',
        'username_label': 'பயனர்பெயர்:',
        'password_label': 'கடவுச்சொல்:',
        'welcome_back': 'மீண்டும் வரவேற்கிறோம்',
        'sign_in_to_access': 'உங்கள் வானிலை டாஷ்போர்டை அணுக உள்நுழையவும்'
    },
    'ml': {
        'name': 'Malayalam', 'flag': '🇮🇳',
        'title': '🌤️ കാലാവസ്ഥാ ആപ്പ്',
        'subtitle': 'നിങ്ങളുടെ സ്വകാര്യ കാലാവസ്ഥാ സഹായി',
        'placeholder': 'നഗരം തിരയുക...',
        'search': 'തിരയുക',
        'recent': 'സമീപകാല തിരച്ചിലുകൾ',
        'favorites': '⭐ പ്രിയങ്കരങ്ങൾ',
        'add_favorite': '⭐ പ്രിയങ്കരങ്ങളിൽ ചേർക്കുക',
        'feels_like': 'അനുഭവപ്പെടുന്നത്',
        'humidity': 'ഈർപ്പം',
        'wind_speed': 'കാറ്റിന്റെ വേഗത',
        'pressure': 'മർദ്ദം',
        'visibility': 'ദൃശ്യത',
        'sunrise': 'സൂര്യോദയം/അസ്തമയം',
        'forecast': '📊 5-ദിവസ പ്രവചനം',
        'air_quality': 'വായുവിന്റെ ഗുണനിലവാരം',
        'good': 'നല്ലത്',
        'fair': 'ശരാശരി',
        'moderate': 'മിതമായ',
        'poor': 'മോശം',
        'very_poor': 'വളരെ മോശം',
        'share': '📤 പങ്കിടുക',
        'copy': '📋 പകർത്തുക',
        'error': 'ഇതിനുള്ള കാലാവസ്ഥ കണ്ടെത്താനായില്ല',
        'updated': 'അപ്ഡേറ്റ് ചെയ്തു',
        'location': '📍 സ്ഥാനം',
        'hourly': '⏰ മണിക്കൂർ പ്രവചനം',
        'stats': '📊 കാലാവസ്ഥാ സ്ഥിതിവിവരങ്ങൾ',
        'high': '🔥 ഉയർന്നത്',
        'low': '❄️ താഴ്ന്നത്',
        'average': '📊 ശരാശരി',
        'rainy_days': '🌧️ മഴ ദിവസങ്ങൾ',
        'nearby': '📍 സമീപ നഗരങ്ങൾ',
        'radar': '📡 കാലാവസ്ഥാ റഡാർ',
        'voice_assistant': '🎤 ശബ്ദ സഹായി',
        'login': '🔐 ലോഗിൻ',
        'logout': '🚪 ലോഗൗട്ട്',
        'username': 'ഉപയോക്തൃനാമം',
        'password': 'പാസ്വേഡ്',
        'login_btn': 'ലോഗിൻ',
        'register': 'രജിസ്റ്റർ',
        'welcome': 'സ്വാഗതം',
        'invalid_credentials': 'തെറ്റായ ഉപയോക്തൃനാമം അല്ലെങ്കിൽ പാസ്വേഡ്!',
        'register_success': 'രജിസ്ട്രേഷൻ വിജയകരം! ദയവായി ലോഗിൻ ചെയ്യുക.',
        'username_exists': 'ഉപയോക്തൃനാമം നിലവിലുണ്ട്!',
        'password_mismatch': 'പാസ്വേഡുകൾ പൊരുത്തപ്പെടുന്നില്ല!',
        'confirm_password': 'പാസ്വേഡ് സ്ഥിരീകരിക്കുക',
        'uv_index': '☀️ യുവി സൂചിക',
        'world_clock': '🕐 ലോക ക്ലോക്ക്',
        'forgot_password': '🔑 പാസ്വേഡ് മറന്നോ?',
        'reset_password': 'പാസ്വേഡ് പുനഃസജ്ജമാക്കുക',
        'email': 'ഇമെയിൽ വിലാസം',
        'phone': 'ഫോൺ നമ്പർ',
        'contact_method': 'ബന്ധപ്പെടാനുള്ള മാർഗ്ഗം',
        'send_otp': 'OTP അയയ്ക്കുക',
        'verify_otp': 'OTP പരിശോധിക്കുക',
        'enter_otp': 'OTP നൽകുക',
        'new_password': 'പുതിയ പാസ്വേഡ്',
        'confirm_new_password': 'പുതിയ പാസ്വേഡ് സ്ഥിരീകരിക്കുക',
        'password_reset_success': 'പാസ്വേഡ് വിജയകരമായി പുനഃസജ്ജമാക്കി! ദയവായി ലോഗിൻ ചെയ്യുക.',
        'invalid_otp': 'അസാധുവായ OTP! വീണ്ടും ശ്രമിക്കുക.',
        'otp_sent': 'OTP വിജയകരമായി അയച്ചു!',
        'user_not_found': 'ഉപയോക്താവിനെ കണ്ടെത്താനായില്ല!',
        'contact_us': '📞 ഞങ്ങളെ ബന്ധപ്പെടുക',
        'contact_message': 'സഹായിക്കാൻ ഞങ്ങൾ ഇവിടെയുണ്ട്!',
        'our_contacts': 'ഞങ്ങളുടെ ബന്ധങ്ങൾ',
        'compare': '📊 നഗരങ്ങൾ താരതമ്യം ചെയ്യുക',
        'chatbot': '🤖 കാലാവസ്ഥാ ചാറ്റ്ബോട്ട്',
        'widget': '📱 കാലാവസ്ഥാ വിഡ്ജെറ്റ്',
        'admin': '⚙️ അഡ്മിൻ ഡാഷ്ബോർഡ്',
        'export_pdf': '📄 PDF എക്സ്പോർട്ട്',
        'alerts': '🔔 കാലാവസ്ഥാ അലേർട്ടുകൾ',
        'set_alert': 'അലേർട്ട് സജ്ജമാക്കുക',
        'temp_threshold': 'താപനില പരിധി',
        'city': 'നഗരം',
        'alert_type': 'അലേർട്ട് തരം',
        'sign_in': 'സൈൻ ഇൻ',
        'or_continue_with': 'അല്ലെങ്കിൽ ഇതുമായി തുടരുക',
        'forgot_password_link': 'പാസ്വേഡ് മറന്നോ?',
        'contact_us_link': 'ഞങ്ങളെ ബന്ധപ്പെടുക',
        'no_account': 'അക്കൗണ്ട് ഇല്ലേ? ഇവിടെ രജിസ്റ്റർ ചെയ്യുക',
        'demo_credentials': 'ഡെമോ ക്രെഡൻഷ്യലുകൾ:',
        'username_label': 'ഉപയോക്തൃനാമം:',
        'password_label': 'പാസ്വേഡ്:',
        'welcome_back': 'തിരികെ സ്വാഗതം',
        'sign_in_to_access': 'നിങ്ങളുടെ കാലാവസ്ഥാ ഡാഷ്ബോർഡ് ആക്സസ് ചെയ്യാൻ സൈൻ ഇൻ ചെയ്യുക'
    },
    'te': {
        'name': 'Telugu', 'flag': '🇮🇳',
        'title': '🌤️ వాతావరణ యాప్',
        'subtitle': 'మీ వ్యక్తిగత వాతావరణ సహాయకుడు',
        'placeholder': 'నగరం శోధించండి...',
        'search': 'శోధించు',
        'recent': 'ఇటీవలి శోధనలు',
        'favorites': '⭐ ఇష్టమైనవి',
        'add_favorite': '⭐ ఇష్టమైనవాటికి జోడించు',
        'feels_like': 'అనిపిస్తుంది',
        'humidity': 'తేమ',
        'wind_speed': 'గాలి వేగం',
        'pressure': 'పీడనం',
        'visibility': 'దృశ్యత',
        'sunrise': 'సూర్యోదయం/సూర్యాస్తమయం',
        'forecast': '📊 5-రోజుల సూచన',
        'air_quality': 'గాలి నాణ్యత',
        'good': 'మంచిది',
        'fair': 'సరే',
        'moderate': 'మధ్యస్థం',
        'poor': 'పేలవం',
        'very_poor': 'చాలా పేలవం',
        'share': '📤 షేర్ చేయి',
        'copy': '📋 కాపీ చేయి',
        'error': 'కోసం వాతావరణం కనుగొనబడలేదు',
        'updated': 'నవీకరించబడింది',
        'location': '📍 స్థానం',
        'hourly': '⏰ గంటల సూచన',
        'stats': '📊 వాతావరణ గణాంకాలు',
        'high': '🔥 అధికం',
        'low': '❄️ తక్కువ',
        'average': '📊 సగటు',
        'rainy_days': '🌧️ వర్షపు రోజులు',
        'nearby': '📍 సమీప నగరాలు',
        'radar': '📡 వాతావరణ రాడార్',
        'voice_assistant': '🎤 వాయిస్ అసిస్టెంట్',
        'login': '🔐 లాగిన్',
        'logout': '🚪 లాగౌట్',
        'username': 'వినియోగదారు పేరు',
        'password': 'పాస్వర్డ్',
        'login_btn': 'లాగిన్',
        'register': 'నమోదు',
        'welcome': 'స్వాగతం',
        'invalid_credentials': 'తప్పు వినియోగదారు పేరు లేదా పాస్వర్డ్!',
        'register_success': 'నమోదు విజయవంతం! దయచేసి లాగిన్ చేయండి.',
        'username_exists': 'వినియోగదారు పేరు ఇప్పటికే ఉంది!',
        'password_mismatch': 'పాస్వర్డ్లు సరిపోలడం లేదు!',
        'confirm_password': 'పాస్వర్డ్ నిర్ధారించండి',
        'uv_index': '☀️ UV సూచిక',
        'world_clock': '🕐 ప్రపంచ గడియారం',
        'forgot_password': '🔑 పాస్వర్డ్ మర్చిపోయారా?',
        'reset_password': 'పాస్వర్డ్ రీసెట్ చేయి',
        'email': 'ఇమెయిల్ చిరునామా',
        'phone': 'ఫోన్ నంబర్',
        'contact_method': 'సంప్రదించే విధానం',
        'send_otp': 'OTP పంపు',
        'verify_otp': 'OTP ధృవీకరించు',
        'enter_otp': 'OTP నమోదు చేయండి',
        'new_password': 'కొత్త పాస్వర్డ్',
        'confirm_new_password': 'కొత్త పాస్వర్డ్ నిర్ధారించండి',
        'password_reset_success': 'పాస్వర్డ్ విజయవంతంగా రీసెట్ చేయబడింది! దయచేసి లాగిన్ చేయండి.',
        'invalid_otp': 'చెల్లని OTP! మళ్లీ ప్రయత్నించండి.',
        'otp_sent': 'OTP విజయవంతంగా పంపబడింది!',
        'user_not_found': 'వినియోగదారు కనుగొనబడలేదు!',
        'contact_us': '📞 మమ్మల్ని సంప్రదించండి',
        'contact_message': 'మేము సహాయం చేయడానికి ఇక్కడ ఉన్నాము!',
        'our_contacts': 'మా సంప్రదింపులు',
        'compare': '📊 నగరాలను సరిపోల్చండి',
        'chatbot': '🤖 వాతావరణ చాట్బాట్',
        'widget': '📱 వాతావరణ విడ్జెట్',
        'admin': '⚙️ అడ్మిన్ డాష్బోర్డ్',
        'export_pdf': '📄 PDF ఎగుమతి',
        'alerts': '🔔 వాతావరణ హెచ్చరికలు',
        'set_alert': 'హెచ్చరిక సెట్ చేయి',
        'temp_threshold': 'ఉష్ణోగ్రత పరిమితి',
        'city': 'నగరం',
        'alert_type': 'హెచ్చరిక రకం',
        'sign_in': 'సైన్ ఇన్',
        'or_continue_with': 'లేదా దీనితో కొనసాగండి',
        'forgot_password_link': 'పాస్వర్డ్ మర్చిపోయారా?',
        'contact_us_link': 'మమ్మల్ని సంప్రదించండి',
        'no_account': 'ఖాతా లేదా? ఇక్కడ నమోదు చేయండి',
        'demo_credentials': 'డెమో క్రెడెన్షియల్స్:',
        'username_label': 'వినియోగదారు పేరు:',
        'password_label': 'పాస్వర్డ్:',
        'welcome_back': 'తిరిగి స్వాగతం',
        'sign_in_to_access': 'మీ వాతావరణ డాష్బోర్డ్ను యాక్సెస్ చేయడానికి సైన్ ఇన్ చేయండి'
    },
    'kn': {
        'name': 'Kannada', 'flag': '🇮🇳',
        'title': '🌤️ ಹವಾಮಾನ ಅಪ್ಲಿಕೇಶನ್',
        'subtitle': 'ನಿಮ್ಮ ವೈಯಕ್ತಿಕ ಹವಾಮಾನ ಸಹಾಯಕ',
        'placeholder': 'ನಗರವನ್ನು ಹುಡುಕಿ...',
        'search': 'ಹುಡುಕು',
        'recent': 'ಇತ್ತೀಚಿನ ಹುಡುಕಾಟಗಳು',
        'favorites': '⭐ ಮೆಚ್ಚಿನವುಗಳು',
        'add_favorite': '⭐ ಮೆಚ್ಚಿನವುಗಳಿಗೆ ಸೇರಿಸಿ',
        'feels_like': 'ಅನಿಸುತ್ತದೆ',
        'humidity': 'ತೇವಾಂಶ',
        'wind_speed': 'ಗಾಳಿಯ ವೇಗ',
        'pressure': 'ಒತ್ತಡ',
        'visibility': 'ಗೋಚರತೆ',
        'sunrise': 'ಸೂರ್ಯೋದಯ/ಸೂರ್ಯಾಸ್ತ',
        'forecast': '📊 5-ದಿನದ ಮುನ್ಸೂಚನೆ',
        'air_quality': 'ಗಾಳಿಯ ಗುಣಮಟ್ಟ',
        'good': 'ಉತ್ತಮ',
        'fair': 'ಸರಿ',
        'moderate': 'ಮಧ್ಯಮ',
        'poor': 'ಕಳಪೆ',
        'very_poor': 'ಬಹಳ ಕಳಪೆ',
        'share': '📤 ಹಂಚಿಕೊಳ್ಳಿ',
        'copy': '📋 ನಕಲಿಸಿ',
        'error': 'ಗೆ ಹವಾಮಾನ ಕಂಡುಬಂದಿಲ್ಲ',
        'updated': 'ನವೀಕರಿಸಲಾಗಿದೆ',
        'location': '📍 ಸ್ಥಳ',
        'hourly': '⏰ ಗಂಟೆಯ ಮುನ್ಸೂಚನೆ',
        'stats': '📊 ಹವಾಮಾನ ಅಂಕಿಅಂಶಗಳು',
        'high': '🔥 ಹೆಚ್ಚಿನದು',
        'low': '❄️ ಕಡಿಮೆ',
        'average': '📊 ಸರಾಸರಿ',
        'rainy_days': '🌧️ ಮಳೆಯ ದಿನಗಳು',
        'nearby': '📍 ಸಮೀಪದ ನಗರಗಳು',
        'radar': '📡 ಹವಾಮಾನ ರೇಡಾರ್',
        'voice_assistant': '🎤 ಧ್ವನಿ ಸಹಾಯಕ',
        'login': '🔐 ಲಾಗಿನ್',
        'logout': '🚪 ಲಾಗೌಟ್',
        'username': 'ಬಳಕೆದಾರಹೆಸರು',
        'password': 'ಪಾಸ್ವರ್ಡ್',
        'login_btn': 'ಲಾಗಿನ್',
        'register': 'ನೋಂದಾಯಿಸಿ',
        'welcome': 'ಸ್ವಾಗತ',
        'invalid_credentials': 'ಅಮಾನ್ಯ ಬಳಕೆದಾರಹೆಸರು ಅಥವಾ ಪಾಸ್ವರ್ಡ್!',
        'register_success': 'ನೋಂದಣಿ ಯಶಸ್ವಿಯಾಗಿದೆ! ದಯವಿಟ್ಟು ಲಾಗಿನ್ ಮಾಡಿ.',
        'username_exists': 'ಬಳಕೆದಾರಹೆಸರು ಈಗಾಗಲೇ ಅಸ್ತಿತ್ವದಲ್ಲಿದೆ!',
        'password_mismatch': 'ಪಾಸ್ವರ್ಡ್ಗಳು ಹೊಂದಾಣಿಕೆಯಾಗುತ್ತಿಲ್ಲ!',
        'confirm_password': 'ಪಾಸ್ವರ್ಡ್ ಖಚಿತಪಡಿಸಿ',
        'uv_index': '☀️ UV ಸೂಚ್ಯಂಕ',
        'world_clock': '🕐 ವಿಶ್ವ ಗಡಿಯಾರ',
        'forgot_password': '🔑 ಪಾಸ್ವರ್ಡ್ ಮರೆತಿರಾ?',
        'reset_password': 'ಪಾಸ್ವರ್ಡ್ ಮರುಹೊಂದಿಸಿ',
        'email': 'ಇಮೇಲ್ ವಿಳಾಸ',
        'phone': 'ಫೋನ್ ಸಂಖ್ಯೆ',
        'contact_method': 'ಸಂಪರ್ಕ ವಿಧಾನ',
        'send_otp': 'OTP ಕಳುಹಿಸಿ',
        'verify_otp': 'OTP ಪರಿಶೀಲಿಸಿ',
        'enter_otp': 'OTP ನಮೂದಿಸಿ',
        'new_password': 'ಹೊಸ ಪಾಸ್ವರ್ಡ್',
        'confirm_new_password': 'ಹೊಸ ಪಾಸ್ವರ್ಡ್ ಖಚಿತಪಡಿಸಿ',
        'password_reset_success': 'ಪಾಸ್ವರ್ಡ್ ಯಶಸ್ವಿಯಾಗಿ ಮರುಹೊಂದಿಸಲಾಗಿದೆ! ದಯವಿಟ್ಟು ಲಾಗಿನ್ ಮಾಡಿ.',
        'invalid_otp': 'ಅಮಾನ್ಯ OTP! ದಯವಿಟ್ಟು ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಿ.',
        'otp_sent': 'OTP ಯಶಸ್ವಿಯಾಗಿ ಕಳುಹಿಸಲಾಗಿದೆ!',
        'user_not_found': 'ಬಳಕೆದಾರರು ಕಂಡುಬಂದಿಲ್ಲ!',
        'contact_us': '📞 ನಮ್ಮನ್ನು ಸಂಪರ್ಕಿಸಿ',
        'contact_message': 'ನಾವು ಸಹಾಯ ಮಾಡಲು ಇಲ್ಲಿದ್ದೇವೆ!',
        'our_contacts': 'ನಮ್ಮ ಸಂಪರ್ಕಗಳು',
        'compare': '📊 ನಗರಗಳನ್ನು ಹೋಲಿಕೆ ಮಾಡಿ',
        'chatbot': '🤖 ಹವಾಮಾನ ಚಾಟ್ಬಾಟ್',
        'widget': '📱 ಹವಾಮಾನ ವಿಡ್ಜೆಟ್',
        'admin': '⚙️ ಆಡ್ಮಿನ್ ಡ್ಯಾಶ್ಬೋರ್ಡ್',
        'export_pdf': '📄 PDF ರಫ್ತು',
        'alerts': '🔔 ಹವಾಮಾನ ಎಚ್ಚರಿಕೆಗಳು',
        'set_alert': 'ಎಚ್ಚರಿಕೆ ಹೊಂದಿಸಿ',
        'temp_threshold': 'ತಾಪಮಾನ ಮಿತಿ',
        'city': 'ನಗರ',
        'alert_type': 'ಎಚ್ಚರಿಕೆ ಪ್ರಕಾರ',
        'sign_in': 'ಸೈನ್ ಇನ್',
        'or_continue_with': 'ಅಥವಾ ಇದರೊಂದಿಗೆ ಮುಂದುವರಿಸಿ',
        'forgot_password_link': 'ಪಾಸ್ವರ್ಡ್ ಮರೆತಿರಾ?',
        'contact_us_link': 'ನಮ್ಮನ್ನು ಸಂಪರ್ಕಿಸಿ',
        'no_account': 'ಖಾತೆ ಇಲ್ಲವೇ? ಇಲ್ಲಿ ನೋಂದಾಯಿಸಿ',
        'demo_credentials': 'ಡೆಮೊ ರುಜುವಾತುಗಳು:',
        'username_label': 'ಬಳಕೆದಾರಹೆಸರು:',
        'password_label': 'ಪಾಸ್ವರ್ಡ್:',
        'welcome_back': 'ಮರಳಿ ಸ್ವಾಗತ',
        'sign_in_to_access': 'ನಿಮ್ಮ ಹವಾಮಾನ ಡ್ಯಾಶ್ಬೋರ್ಡ್ ಪ್ರವೇಶಿಸಲು ಸೈನ್ ಇನ್ ಮಾಡಿ'
    }
}

# ===== OTP FUNCTIONS =====
otp_storage = {}

def generate_otp():
    return str(random.randint(100000, 999999))

def send_otp_email(email, otp):
    print(f"📧 OTP for {email}: {otp}")
    return True

def send_otp_sms(phone, otp):
    print(f"📱 OTP for {phone}: {otp}")
    return True

# ===== ROUTES =====

# ===== GOOGLE OAUTH =====
@app.route('/social_login/google')
def google_login():
    params = {
        'client_id': GOOGLE_CLIENT_ID,
        'redirect_uri': GOOGLE_REDIRECT_URI,
        'response_type': 'code',
        'scope': 'email profile openid',
        'access_type': 'offline',
        'prompt': 'select_account'
    }
    auth_url = f'https://accounts.google.com/o/oauth2/auth?{urlencode(params)}'
    return redirect(auth_url)

@app.route('/google_callback')
def google_callback():
    code = request.args.get('code')
    if not code:
        return redirect(url_for('login'))
    
    token_data = {
        'code': code,
        'client_id': GOOGLE_CLIENT_ID,
        'client_secret': GOOGLE_CLIENT_SECRET,
        'redirect_uri': GOOGLE_REDIRECT_URI,
        'grant_type': 'authorization_code'
    }
    
    try:
        token_response = requests.post('https://oauth2.googleapis.com/token', data=token_data)
        token_json = token_response.json()
        
        if 'access_token' not in token_json:
            return redirect(url_for('login'))
        
        access_token = token_json['access_token']
        
        userinfo_response = requests.get(
            'https://www.googleapis.com/oauth2/v2/userinfo',
            headers={'Authorization': f'Bearer {access_token}'}
        )
        userinfo = userinfo_response.json()
        
        email = userinfo.get('email')
        name = userinfo.get('name', email.split('@')[0])
        social_id = userinfo.get('id')
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM users WHERE social_provider = ? AND social_id = ?', ('google', social_id))
        user = cursor.fetchone()
        
        if not user and email:
            cursor.execute('SELECT * FROM users WHERE email = ?', (email,))
            user = cursor.fetchone()
        
        if not user:
            cursor.execute('''
                INSERT INTO users (username, email, social_provider, social_id, verified)
                VALUES (?, ?, ?, ?, ?)
            ''', (name, email, 'google', social_id, 1))
            conn.commit()
            user_id = cursor.lastrowid
            cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
            user = cursor.fetchone()
        
        conn.close()
        
        if user:
            session['user'] = user['username']
            session['user_id'] = user['id']
            return redirect(url_for('home'))
        
        return redirect(url_for('login'))
        
    except Exception as e:
        print(f"Google OAuth error: {e}")
        return redirect(url_for('login'))

# ===== FACEBOOK OAUTH =====
@app.route('/social_login/facebook')
def facebook_login():
    params = {
        'client_id': FACEBOOK_APP_ID,
        'redirect_uri': FACEBOOK_REDIRECT_URI,
        'response_type': 'code',
        'scope': 'email,public_profile'
    }
    auth_url = f'https://www.facebook.com/v18.0/dialog/oauth?{urlencode(params)}'
    return redirect(auth_url)

@app.route('/facebook_callback')
def facebook_callback():
    code = request.args.get('code')
    if not code:
        return redirect(url_for('login'))
    
    token_url = f'https://graph.facebook.com/v18.0/oauth/access_token'
    token_data = {
        'client_id': FACEBOOK_APP_ID,
        'client_secret': FACEBOOK_APP_SECRET,
        'redirect_uri': FACEBOOK_REDIRECT_URI,
        'code': code
    }
    
    try:
        token_response = requests.get(token_url, params=token_data)
        token_json = token_response.json()
        
        if 'access_token' not in token_json:
            return redirect(url_for('login'))
        
        access_token = token_json['access_token']
        
        userinfo_response = requests.get(
            'https://graph.facebook.com/me',
            params={
                'access_token': access_token,
                'fields': 'id,name,email'
            }
        )
        userinfo = userinfo_response.json()
        
        email = userinfo.get('email')
        name = userinfo.get('name', 'Facebook User')
        social_id = userinfo.get('id')
        
        if not email:
            email = f'{social_id}@facebook.com'
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM users WHERE social_provider = ? AND social_id = ?', ('facebook', social_id))
        user = cursor.fetchone()
        
        if not user and email:
            cursor.execute('SELECT * FROM users WHERE email = ?', (email,))
            user = cursor.fetchone()
        
        if not user:
            cursor.execute('''
                INSERT INTO users (username, email, social_provider, social_id, verified)
                VALUES (?, ?, ?, ?, ?)
            ''', (name, email, 'facebook', social_id, 1))
            conn.commit()
            user_id = cursor.lastrowid
            cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
            user = cursor.fetchone()
        
        conn.close()
        
        if user:
            session['user'] = user['username']
            session['user_id'] = user['id']
            return redirect(url_for('home'))
        
        return redirect(url_for('login'))
        
    except Exception as e:
        print(f"Facebook OAuth error: {e}")
        return redirect(url_for('login'))

# ===== APPLE OAUTH (DEMO MODE) =====
@app.route('/social_login/apple')
def apple_login():
    import random
    import secrets
    
    email = f'apple_demo_{secrets.token_hex(4)}@icloud.com'
    name = f'AppleUser_{random.randint(1000, 9999)}'
    social_id = f'apple_{secrets.token_hex(8)}'
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM users WHERE social_provider = ? AND social_id = ?', ('apple', social_id))
    user = cursor.fetchone()
    
    if not user:
        cursor.execute('SELECT * FROM users WHERE email = ?', (email,))
        user = cursor.fetchone()
    
    if not user:
        cursor.execute('''
            INSERT INTO users (username, email, social_provider, social_id, verified)
            VALUES (?, ?, ?, ?, ?)
        ''', (name, email, 'apple', social_id, 1))
        conn.commit()
        user_id = cursor.lastrowid
        cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
        user = cursor.fetchone()
    
    conn.close()
    
    if user:
        session['user'] = user['username']
        session['user_id'] = user['id']
        return redirect(url_for('home'))
    
    return redirect(url_for('login'))

@app.route('/apple_callback', methods=['GET', 'POST'])
def apple_callback():
    if 'user' in session:
        return redirect(url_for('home'))
    return redirect(url_for('login'))

# ===== SOCIAL LOGIN =====
@app.route('/social_login/<provider>')
def social_login(provider):
    if provider == 'google':
        return redirect(url_for('google_login'))
    elif provider == 'facebook':
        return redirect(url_for('facebook_login'))
    elif provider == 'apple':
        return redirect(url_for('apple_login'))
    return redirect(url_for('login'))

# ===== LOGIN =====
@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    lang = session.get('lang', 'en')
    texts = LANGUAGES.get(lang, LANGUAGES['en'])
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = get_user_by_username(username)
        
        if user and user['password'] == password:
            session['user'] = username
            session['user_id'] = user['id']
            return redirect(url_for('home'))
        else:
            error = texts.get('invalid_credentials', 'Invalid username or password!')
    
    return render_template('login.html', error=error, texts=texts, lang=lang)

# ===== REGISTER =====
@app.route('/register', methods=['GET', 'POST'])
def register():
    error = None
    success = None
    step = 'form'
    lang = session.get('lang', 'en')
    texts = LANGUAGES.get(lang, LANGUAGES['en'])
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'send_otp':
            username = request.form.get('username')
            password = request.form.get('password')
            confirm_password = request.form.get('confirm_password')
            email = request.form.get('email')
            phone = request.form.get('phone')
            contact_method = request.form.get('contact_method')
            
            existing_user = get_user_by_username(username)
            
            if existing_user:
                error = texts.get('username_exists', 'Username already exists!')
            elif password != confirm_password:
                error = texts.get('password_mismatch', 'Passwords do not match!')
            elif len(username) < 3:
                error = 'Username must be at least 3 characters!'
            elif len(password) < 4:
                error = 'Password must be at least 4 characters!'
            elif contact_method == 'email' and not email:
                error = 'Email is required!'
            elif contact_method == 'phone' and not phone:
                error = 'Phone number is required!'
            elif contact_method == 'email' and '@' not in email:
                error = 'Please enter a valid email!'
            elif contact_method == 'phone' and (len(phone) < 10 or not phone.isdigit()):
                error = 'Please enter a valid phone number!'
            else:
                otp = generate_otp()
                contact_value = email if contact_method == 'email' else phone
                
                session['temp_username'] = username
                session['temp_password'] = password
                session['temp_email'] = email
                session['temp_phone'] = phone
                session['temp_contact'] = contact_value
                session['temp_contact_method'] = contact_method
                session['temp_otp'] = otp
                session['temp_otp_time'] = time.time()
                
                if contact_method == 'email':
                    send_otp_email(email, otp)
                else:
                    send_otp_sms(phone, otp)
                
                success = texts.get('otp_sent', 'OTP sent successfully!')
                step = 'verify'
        
        elif action == 'verify_otp':
            otp_input = request.form.get('otp')
            stored_otp = session.get('temp_otp', '')
            otp_time = session.get('temp_otp_time', 0)
            
            if time.time() - otp_time > 300:
                error = 'OTP expired! Please request a new one.'
                step = 'form'
            elif otp_input == stored_otp:
                username = session.get('temp_username')
                password = session.get('temp_password')
                email = session.get('temp_email')
                phone = session.get('temp_phone')
                
                create_user(username, password, email, phone)
                
                session.pop('temp_username', None)
                session.pop('temp_password', None)
                session.pop('temp_email', None)
                session.pop('temp_phone', None)
                session.pop('temp_contact', None)
                session.pop('temp_otp', None)
                session.pop('temp_otp_time', None)
                session.pop('temp_contact_method', None)
                
                success = texts.get('register_success', 'Account created successfully! Please login.')
                step = 'complete'
            else:
                error = texts.get('invalid_otp', 'Invalid OTP! Please try again.')
        
        elif action == 'resend_otp':
            contact_method = session.get('temp_contact_method', 'email')
            contact_value = session.get('temp_contact', '')
            
            if contact_value:
                otp = generate_otp()
                session['temp_otp'] = otp
                session['temp_otp_time'] = time.time()
                
                if contact_method == 'email':
                    send_otp_email(contact_value, otp)
                else:
                    send_otp_sms(contact_value, otp)
                
                success = texts.get('otp_sent', 'OTP resent successfully!')
                step = 'verify'
    
    return render_template('register.html', 
                         error=error, 
                         success=success, 
                         step=step,
                         temp_username=session.get('temp_username', ''),
                         temp_email=session.get('temp_email', ''),
                         temp_phone=session.get('temp_phone', ''),
                         temp_contact=session.get('temp_contact', ''),
                         texts=texts, 
                         lang=lang)

# ===== FORGOT PASSWORD =====
@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    error = None
    success = None
    lang = session.get('lang', 'en')
    texts = LANGUAGES.get(lang, LANGUAGES['en'])
    step = 'request'
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'send_otp':
            username = request.form.get('username')
            contact_method = request.form.get('contact_method')
            contact_value = request.form.get('contact_value')
            
            user = get_user_by_username(username)
            if user:
                otp = generate_otp()
                otp_storage[username] = {'otp': otp, 'contact': contact_value, 'method': contact_method, 'time': time.time()}
                
                if contact_method == 'email':
                    send_otp_email(contact_value, otp)
                else:
                    send_otp_sms(contact_value, otp)
                
                success = texts.get('otp_sent', 'OTP sent successfully!')
                step = 'verify'
            else:
                error = texts.get('user_not_found', 'User not found!')
        
        elif action == 'verify_otp':
            username = request.form.get('username')
            otp_input = request.form.get('otp')
            
            if username in otp_storage:
                stored_otp = otp_storage[username]['otp']
                otp_time = otp_storage[username].get('time', 0)
                
                if time.time() - otp_time > 300:
                    error = 'OTP expired! Please request a new one.'
                elif otp_input == stored_otp:
                    success = 'OTP verified! Please enter new password.'
                    step = 'reset'
                else:
                    error = texts.get('invalid_otp', 'Invalid OTP! Please try again.')
            else:
                error = 'Please request OTP first!'
        
        elif action == 'reset_password':
            username = request.form.get('username')
            new_password = request.form.get('new_password')
            confirm_password = request.form.get('confirm_password')
            
            if new_password == confirm_password and len(new_password) >= 4:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute('UPDATE users SET password = ? WHERE username = ?', (new_password, username))
                conn.commit()
                conn.close()
                
                success = texts.get('password_reset_success', 'Password reset successfully! Please login.')
                step = 'complete'
                if username in otp_storage:
                    del otp_storage[username]
            else:
                error = 'Passwords do not match or too short!'
    
    return render_template('forgot_password.html', error=error, success=success, step=step, texts=texts, lang=lang)

# ===== LOGOUT =====
@app.route('/logout')
def logout():
    session.pop('user', None)
    session.pop('user_id', None)
    return redirect(url_for('login'))

# ===== CONTACT =====
@app.route('/contact')
def contact():
    lang = session.get('lang', 'en')
    texts = LANGUAGES.get(lang, LANGUAGES['en'])
    return render_template('contact.html', texts=texts, lang=lang)

# ===== PROFILE =====
@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    user = get_user_profile(user_id)
    history = get_search_history(user_id)
    most_searched = get_most_searched_cities(user_id)
    alerts = get_user_alerts(user_id)
    
    lang = session.get('lang', 'en')
    texts = LANGUAGES.get(lang, LANGUAGES['en'])
    error = None
    success = None
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'update_profile':
            default_city = request.form.get('default_city')
            bio = request.form.get('bio')
            temp_unit = request.form.get('temp_unit', 'c')
            
            update_user_profile(user_id, default_city, bio, temp_unit)
            session['unit'] = temp_unit
            success = 'Profile updated successfully!'
        
        elif action == 'clear_history':
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('DELETE FROM search_history WHERE user_id = ?', (user_id,))
            conn.commit()
            conn.close()
            success = 'Search history cleared!'
            return redirect(url_for('profile'))
        
        elif action == 'add_alert':
            city = request.form.get('alert_city')
            temp_threshold = int(request.form.get('temp_threshold', 35))
            alert_type = request.form.get('alert_type', 'temperature')
            
            if city:
                save_user_alert(user_id, city, temp_threshold, alert_type)
                success = f'Alert set for {city} at {temp_threshold}°C!'
        
        elif action == 'delete_alert':
            alert_id = request.form.get('alert_id')
            delete_user_alert(alert_id)
            success = 'Alert deleted!'
    
    return render_template('profile.html', 
                         user=user, 
                         history=history, 
                         most_searched=most_searched,
                         alerts=alerts,
                         error=error, 
                         success=success,
                         texts=texts,
                         lang=lang)

# ===== WEATHER COMPARISON =====
@app.route('/compare', methods=['GET', 'POST'])
def compare():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    lang = session.get('lang', 'en')
    texts = LANGUAGES.get(lang, LANGUAGES['en'])
    theme = session.get('theme', 'default')
    unit = session.get('unit', 'c')
    
    comparison = None
    error = None
    city1 = ''
    city2 = ''
    
    if request.method == 'POST':
        city1 = request.form.get('city1', '').strip()
        city2 = request.form.get('city2', '').strip()
        
        if city1 and city2:
            result = compare_weather(city1, city2)
            if result:
                comparison = result
            else:
                error = 'Could not find weather for one or both cities.'
    
    return render_template('compare.html', 
                         comparison=comparison,
                         city1=city1,
                         city2=city2,
                         error=error,
                         unit=unit,
                         lang=lang,
                         texts=texts,
                         theme=theme,
                         themes=THEMES)

# ===== WEATHER CHATBOT =====
@app.route('/chatbot', methods=['GET', 'POST'])
def chatbot():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    lang = session.get('lang', 'en')
    texts = LANGUAGES.get(lang, LANGUAGES['en'])
    theme = session.get('theme', 'default')
    
    response = None
    user_query = ''
    city_name = ''
    weather_data = None
    
    if request.method == 'POST':
        user_query = request.form.get('query', '').strip()
        city = request.form.get('city', '').strip()
        city_name = city
        
        if user_query:
            if city:
                weather_data = get_weather(city)
                if not weather_data:
                    response = f"Sorry, I couldn't find weather data for '{city}'. Please check the city name and try again."
                else:
                    response = get_weather_chatbot_response(user_query, weather_data)
            else:
                import re
                city_match = re.search(r'(?:weather in|for|at)\s+([a-zA-Z\s]+)', user_query)
                if city_match:
                    detected_city = city_match.group(1).strip()
                    weather_data = get_weather(detected_city)
                    if weather_data:
                        city_name = detected_city
                        response = get_weather_chatbot_response(user_query, weather_data)
                    else:
                        response = get_weather_chatbot_response(user_query, None)
                else:
                    response = get_weather_chatbot_response(user_query, None)
    
    return render_template('chatbot.html',
                         response=response,
                         user_query=user_query,
                         city_name=city_name,
                         lang=lang,
                         texts=texts,
                         theme=theme,
                         themes=THEMES)

# ===== WEATHER WIDGET =====
@app.route('/widget')
def widget():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    lang = session.get('lang', 'en')
    texts = LANGUAGES.get(lang, LANGUAGES['en'])
    theme = session.get('theme', 'default')
    
    user_id = session['user_id']
    widget_token = None
    widget_url = None
    error = None
    
    city = request.args.get('city', '')
    if city:
        token = generate_widget_token(user_id, city)
        widget_token = token
        widget_url = f"{request.host_url}widget/embed/{token}"
    
    return render_template('widget.html',
                         widget_token=widget_token,
                         widget_url=widget_url,
                         error=error,
                         lang=lang,
                         texts=texts,
                         theme=theme,
                         themes=THEMES)

@app.route('/widget/embed/<token>')
def widget_embed(token):
    try:
        widget_data = get_widget_data(token)
        if not widget_data:
            return "Invalid widget token", 404
        
        city = widget_data['city']
        weather = get_weather(city)
        
        if not weather:
            return f"City '{city}' not found. Please try again.", 404
        
        return render_template('widget_embed.html', weather=weather)
    except Exception as e:
        return f"Error: {str(e)}", 500

# ===== ADMIN DASHBOARD =====
@app.route('/admin')
def admin_dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user = get_user_profile(session['user_id'])
    
    # Check if user is admin - allow username 'admin' OR email contains 'admin'
    is_admin = False
    if user['username'] == 'admin' or user['email'] == 'admin@example.com':
        is_admin = True
    
    # If no admin exists, allow any user (for testing)
    if not is_admin:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE username = "admin"')
        admin_exists = cursor.fetchone()
        conn.close()
        
        if not admin_exists:
            # No admin exists, allow any user temporarily
            is_admin = True
    
    if not is_admin:
        return f"Access Denied - Admin only. Your username: {user['username']}", 403
    
    lang = session.get('lang', 'en')
    texts = LANGUAGES.get(lang, LANGUAGES['en'])
    theme = session.get('theme', 'default')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get stats
    cursor.execute('SELECT COUNT(*) as count FROM users')
    total_users = cursor.fetchone()['count']
    
    cursor.execute('SELECT COUNT(*) as count FROM search_history')
    total_searches = cursor.fetchone()['count']
    
    cursor.execute('SELECT city, COUNT(*) as count FROM search_history GROUP BY city ORDER BY count DESC LIMIT 5')
    popular_cities = cursor.fetchall()
    
    cursor.execute('SELECT COUNT(*) as count FROM user_alerts WHERE is_active = 1')
    total_alerts = cursor.fetchone()['count']
    
    cursor.execute('''
        SELECT u.username, COUNT(s.id) as search_count 
        FROM users u 
        LEFT JOIN search_history s ON u.id = s.user_id 
        GROUP BY u.id 
        ORDER BY search_count DESC 
        LIMIT 10
    ''')
    user_activity = cursor.fetchall()
    
    conn.close()
    
    return render_template('admin.html',
                         total_users=total_users,
                         total_searches=total_searches,
                         popular_cities=popular_cities,
                         total_alerts=total_alerts,
                         user_activity=user_activity,
                         lang=lang,
                         texts=texts,
                         theme=theme,
                         themes=THEMES)

# ===== EXPORT PDF =====
@app.route('/export_pdf/<city>')
def export_pdf(city):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    weather = get_weather(city)
    if not weather:
        return "City not found", 404
    
    forecast = get_forecast(city)
    
    pdf_buffer = generate_weather_pdf(weather, forecast, city)
    
    return send_file(
        pdf_buffer,
        as_attachment=True,
        download_name=f'weather_report_{city}_{datetime.now().strftime("%Y%m%d")}.pdf',
        mimetype='application/pdf'
    )

# ===== HOME =====
@app.route('/', methods=['GET', 'POST'])
def home():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    weather = None
    forecast = None
    hourly_forecast = None
    alerts = []
    temp_alerts = []
    air_quality = None
    stats = None
    nearby_cities = None
    radar = None
    uv_index = None
    world_time = None
    recent_searches = session.get('recent_searches', [])
    favorites = session.get('favorites', [])
    error = None
    
    greeting, greeting_message = get_greeting()
    current_time = get_current_time()
    
    lang = session.get('lang', 'en')
    texts = LANGUAGES.get(lang, LANGUAGES['en'])
    unit = session.get('unit', 'c')
    theme = session.get('theme', 'default')
    
    if request.method == 'POST':
        city = request.form.get('city')
        action = request.form.get('action')
        
        if action == 'change_lang':
            lang = request.form.get('lang', 'en')
            session['lang'] = lang
            texts = LANGUAGES.get(lang, LANGUAGES['en'])
        elif action == 'toggle_unit':
            session['unit'] = 'f' if unit == 'c' else 'c'
            unit = session['unit']
        elif action == 'add_favorite':
            if city and city not in favorites:
                favorites.append(city)
                session['favorites'] = favorites
        elif action == 'remove_favorite':
            if city in favorites:
                favorites.remove(city)
                session['favorites'] = favorites
        elif city:
            weather = get_weather(city)
            if weather:
                if 'user_id' in session:
                    save_search_history(session['user_id'], city, weather)
                
                if city not in recent_searches:
                    recent_searches.insert(0, city)
                    if len(recent_searches) > 10:
                        recent_searches.pop()
                    session['recent_searches'] = recent_searches
                
                forecast = get_forecast(city)
                hourly_forecast = get_hourly_forecast(city)
                alerts = get_weather_alerts(weather)
                temp_alerts = check_temperature_alerts(weather)
                stats = get_weather_stats(forecast, unit)
                
                if 'lat' in weather and 'lon' in weather:
                    air_quality = get_air_quality(weather['lat'], weather['lon'])
                    nearby_cities = get_nearby_cities(weather['lat'], weather['lon'])
                    radar = get_weather_radar(weather['lat'], weather['lon'])
                    uv_index = get_uv_index(weather['lat'], weather['lon'])
                    
                    if 'timezone' in weather:
                        world_time = get_world_time(weather['timezone'])
            else:
                error = f"{texts['error']} '{city}'."
    
    if unit == 'f' and weather:
        weather['temperature'] = round((weather['temperature'] * 9/5) + 32)
        weather['feels_like'] = round((weather['feels_like'] * 9/5) + 32)
        if forecast:
            for day in forecast:
                day['temperature'] = round((day['temperature'] * 9/5) + 32)
        if hourly_forecast:
            for hour in hourly_forecast:
                hour['temp'] = round((hour['temp'] * 9/5) + 32)
        if nearby_cities:
            for city in nearby_cities:
                city['temperature'] = round((city['temperature'] * 9/5) + 32)
    
    trend_labels, trend_temps = get_temperature_trend(forecast, unit)
    username = session.get('user', 'User')
    
    return render_template('index.html', 
                         username=username,
                         weather=weather, forecast=forecast,
                         hourly_forecast=hourly_forecast, alerts=alerts,
                         temp_alerts=temp_alerts,
                         air_quality=air_quality, stats=stats,
                         nearby_cities=nearby_cities,
                         radar=radar, uv_index=uv_index, world_time=world_time,
                         favorites=favorites, recent_searches=recent_searches,
                         unit=unit, error=error, lang=lang, texts=texts,
                         languages=LANGUAGES, greeting=greeting,
                         greeting_message=greeting_message, current_time=current_time,
                         get_emoji=get_weather_emoji, trend_labels=trend_labels,
                         trend_temps=trend_temps, theme=theme, themes=THEMES)

# ===== LOCATION DETECTION =====
@app.route('/detect_location', methods=['POST'])
def detect_location():
    data = request.get_json()
    lat = data.get('lat')
    lon = data.get('lon')
    
    if lat and lon:
        weather = get_weather_by_coords(lat, lon)
        if weather:
            session['detected_city'] = weather['city']
            return jsonify({'success': True, 'city': weather['city']})
    
    return jsonify({'success': False, 'error': 'Could not detect location'})

# ===== THEME ROUTE =====
@app.route('/set_theme', methods=['POST'])
def set_theme():
    theme = request.form.get('theme', 'default')
    session['theme'] = theme
    return redirect('/')

# ===== NOTIFICATION ROUTE =====
@app.route('/send_notification', methods=['POST'])
def send_notification():
    data = request.get_json()
    title = data.get('title', 'Weather Update')
    message = data.get('message', 'Check the latest weather!')
    return jsonify({'success': True})

if __name__ == '__main__': 
    app.run(debug=True, host='0.0.0.0', port=5000)