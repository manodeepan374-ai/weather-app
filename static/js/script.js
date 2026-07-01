// =====================================================
// WEATHER APP - Complete JavaScript
// =====================================================

// =====================================================
// 1. DARK MODE TOGGLE
// =====================================================
const darkModeToggle = document.getElementById('darkModeToggle');
let isDarkMode = localStorage.getItem('darkMode') === 'true';

function toggleDarkMode() {
    isDarkMode = !isDarkMode;
    document.body.classList.toggle('dark-mode', isDarkMode);
    localStorage.setItem('darkMode', isDarkMode);
    darkModeToggle.innerHTML = isDarkMode ? '<i class="fas fa-sun"></i>' : '<i class="fas fa-moon"></i>';
}

// Load dark mode preference on page load
if (isDarkMode) {
    document.body.classList.add('dark-mode');
    darkModeToggle.innerHTML = '<i class="fas fa-sun"></i>';
}

darkModeToggle.addEventListener('click', toggleDarkMode);

// =====================================================
// 2. TIME-BASED BACKGROUND
// =====================================================
function setTimeBackground() {
    const hour = new Date().getHours();
    const body = document.body;
    
    // Remove existing time classes
    body.classList.remove('morning', 'afternoon', 'evening', 'night');
    
    // Add appropriate class based on time
    if (hour >= 5 && hour < 12) {
        body.classList.add('morning');
    } else if (hour >= 12 && hour < 17) {
        body.classList.add('afternoon');
    } else if (hour >= 17 && hour < 21) {
        body.classList.add('evening');
    } else {
        body.classList.add('night');
    }
}

// Set time background on page load
setTimeBackground();

// =====================================================
// 3. SATELLITE MAP (Leaflet + Mapbox)
// =====================================================
function initSatelliteMap(lat, lon, city, country, description, temperature, unit) {
    // Create the map
    var map = L.map('satelliteMap', {
        zoomControl: true,
        attributionControl: true
    }).setView([lat, lon], 15);
    
    // Add satellite tiles from Mapbox (free)
 L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    maxZoom: 19
}).addTo(map);
    
    // Custom marker icon
    var customIcon = L.divIcon({
        className: 'custom-marker',
        html: '<div style="background: #667eea; border-radius: 50%; width: 34px; height: 34px; display: flex; align-items: center; justify-content: center; border: 3px solid white; box-shadow: 0 4px 15px rgba(0,0,0,0.4);"><span style="color: white; font-size: 16px;">📍</span></div>',
        iconSize: [34, 34],
        iconAnchor: [17, 34]
    });
    
    // Add marker with popup
    L.marker([lat, lon], { icon: customIcon })
        .addTo(map)
        .bindPopup('<b>' + city + ', ' + country + '</b><br>' + description + '<br>' + temperature + '°' + (unit == 'f' ? 'F' : 'C'));
    
    // Fix map rendering after load
    setTimeout(function() {
        map.invalidateSize();
    }, 500);
}

// =====================================================
// 4. SHARE WEATHER FUNCTION
// =====================================================
function shareWeatherFn(city, temp, condition, unit) {
    if (city) {
        const text = '🌤️ Weather in ' + city + ': ' + temp + '°' + (unit == 'f' ? 'F' : 'C') + ', ' + condition;
        
        // Use Web Share API if available (mobile)
        if (navigator.share) {
            navigator.share({
                title: 'Weather Update',
                text: text
            });
        } else {
            // Fallback: copy to clipboard
            navigator.clipboard.writeText(text)
                .then(function() {
                    alert('📋 Weather copied to clipboard!');
                })
                .catch(function() {
                    alert('❌ Could not copy. Please try again.');
                });
        }
    }
}

// =====================================================
// 5. COPY WEATHER FUNCTION
// =====================================================
function copyWeatherFn(city, temp, condition, unit) {
    if (city) {
        const text = '🌤️ Weather in ' + city + ': ' + temp + '°' + (unit == 'f' ? 'F' : 'C') + ', ' + condition;
        
        // Copy to clipboard
        navigator.clipboard.writeText(text)
            .then(function() {
                alert('📋 Weather copied to clipboard!');
            })
            .catch(function() {
                alert('❌ Could not copy. Please try again.');
            });
    }
}

// =====================================================
// 6. AUTO SUBMIT ON ENTER KEY
// =====================================================
function setupAutoSubmit() {
    const cityInput = document.getElementById('cityInput');
    const searchForm = document.getElementById('searchForm');
    
    if (cityInput && searchForm) {
        cityInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                searchForm.submit();
            }
        });
    }
}

// =====================================================
// 7. RECENT SEARCH CLICK HANDLER
// =====================================================
function searchCity(city) {
    document.getElementById('cityInput').value = city;
    document.getElementById('searchForm').submit();
}

// =====================================================
// 8. VOICE SEARCH (Using Web Speech API)
// =====================================================
function setupVoiceSearch() {
    const voiceBtn = document.querySelector('.voice-btn');
    
    if (voiceBtn) {
        // Check if browser supports speech recognition
        if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
            const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
            const recognition = new SpeechRecognition();
            recognition.lang = 'en-US';
            recognition.continuous = false;
            recognition.interimResults = false;
            
            voiceBtn.addEventListener('click', function() {
                this.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
                recognition.start();
            });
            
            recognition.onresult = function(event) {
                const transcript = event.results[0][0].transcript;
                document.getElementById('cityInput').value = transcript;
                document.getElementById('searchForm').submit();
            };
            
            recognition.onerror = function() {
                voiceBtn.innerHTML = '<i class="fas fa-microphone"></i>';
                alert('🎤 Could not hear you. Please try again!');
            };
            
            recognition.onend = function() {
                voiceBtn.innerHTML = '<i class="fas fa-microphone"></i>';
            };
        } else {
            voiceBtn.style.display = 'none';
        }
    }
}

// =====================================================
// 9. RESPONSIVE MAP FIX
// =====================================================
function fixMapOnResize() {
    const mapContainer = document.getElementById('satelliteMap');
    if (mapContainer && window.map) {
        window.map.invalidateSize();
    }
}

// =====================================================
// 10. CONSOLE LOG (For debugging)
// =====================================================
console.log('🌤️ Weather App Loaded Successfully!');
console.log('📍 Dark Mode:', isDarkMode ? 'ON' : 'OFF');
console.log('🕐 Time:', new Date().toLocaleTimeString());

// =====================================================
// 11. INITIALIZE ALL FUNCTIONS ON PAGE LOAD
// =====================================================
document.addEventListener('DOMContentLoaded', function() {
    // Setup auto submit
    setupAutoSubmit();
    
    // Setup voice search
    setupVoiceSearch();
    
    // Initialize map if satelliteMap exists
    if (document.getElementById('satelliteMap')) {
        // Map data is passed from Flask via inline script
        // The map initialization happens inline in index.html
    }
});

// =====================================================
// 12. WINDOW RESIZE HANDLER
// =====================================================
window.addEventListener('resize', function() {
    fixMapOnResize();
});