import React, { useMemo } from 'react';
import { MapContainer, TileLayer, GeoJSON } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import L from 'leaflet';

function MapView({ eventsGeoJSON, sitesGeoJSON, filters, onEventClick, onSiteClick }) {
  const position = [17.4, 78.4]; // Center near Hyderabad

  const getColor = (class_id) => {
    switch (class_id) {
      case 0: return '#22c55e'; // Green
      case 1: return '#eab308'; // Yellow
      case 2: return '#f97316'; // Orange
      case 3: return '#ef4444'; // Red
      default: return '#3b82f6'; // Blue
    }
  };

  // Filter events before passing to GeoJSON
  const filteredEvents = useMemo(() => {
    if (!eventsGeoJSON) return null;
    return {
      type: 'FeatureCollection',
      features: eventsGeoJSON.features.filter(f => 
        filters.classes.includes(f.properties.class_id)
      )
    };
  }, [eventsGeoJSON, filters]);

  const onEachEvent = (feature, layer) => {
    layer.on({
      click: () => {
        onEventClick(feature.properties.event_id);
      }
    });
  };

  const onEachSite = (feature, layer) => {
    layer.on({
      click: () => {
        onSiteClick(feature.properties.site_id);
      }
    });
  };

  const eventPointToLayer = (feature, latlng) => {
    const classId = feature.properties.class_id;
    const isAbnormal = classId === 3;
    
    return L.circleMarker(latlng, {
      radius: isAbnormal ? 10 : 6,
      fillColor: getColor(classId),
      color: isAbnormal ? '#fca5a5' : '#111827',
      weight: isAbnormal ? 2 : 1,
      opacity: 1,
      fillOpacity: isAbnormal ? 0.9 : 0.8
    });
  };

  const sitePointToLayer = (feature, latlng) => {
    // GeoJSON for industrial sites could be polygons or points.
    // If it's a point, we draw a small marker.
    // If it's a polygon, leaflet GeoJSON component handles it automatically, but we can set style.
    return L.circleMarker(latlng, {
      radius: 4,
      fillColor: '#94a3b8',
      color: '#cbd5e1',
      weight: 1,
      opacity: 1,
      fillOpacity: 0.5
    });
  };

  const siteStyle = {
    fillColor: '#94a3b8',
    color: '#cbd5e1',
    weight: 1,
    opacity: 0.8,
    fillOpacity: 0.3
  };

  return (
    <div className="absolute inset-0" style={{ zIndex: 0 }}>
      {/* react-leaflet MapContainer must be given a height */}
      <MapContainer 
        center={position} 
        zoom={6} 
        style={{ height: '100%', width: '100%', backgroundColor: '#0f172a' }}
        zoomControl={false}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />

        {sitesGeoJSON && (
          <GeoJSON 
            data={sitesGeoJSON} 
            pointToLayer={sitePointToLayer}
            style={siteStyle}
            onEachFeature={onEachSite}
          />
        )}

        {filteredEvents && (
          <GeoJSON 
            key={JSON.stringify(filters.classes) + (filteredEvents?.features?.length || 0)} 
            data={filteredEvents} 
            pointToLayer={eventPointToLayer}
            onEachFeature={onEachEvent}
          />
        )}
      </MapContainer>
    </div>
  );
}

export default MapView;
