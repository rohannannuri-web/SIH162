import React, { useState, useEffect } from 'react';
import axios from 'axios';
import MapView from './components/MapView';
import EventPanel from './components/EventPanel';
import SitePanel from './components/SitePanel';
import FiltersPanel from './components/FiltersPanel';
import AlertsPanel from './components/AlertsPanel';
import { Layers, Activity, AlertTriangle } from 'lucide-react';

const API_BASE = 'http://127.0.0.1:8000/api';

function App() {
  const [eventsGeoJSON, setEventsGeoJSON] = useState(null);
  const [sitesGeoJSON, setSitesGeoJSON] = useState(null);
  const [selectedEventId, setSelectedEventId] = useState(null);
  const [selectedSiteId, setSelectedSiteId] = useState(null);
  
  // App state
  const [loading, setLoading] = useState(true);

  // Filters state
  const [filters, setFilters] = useState({
    timeRange: 7, // days
    classes: [0, 1, 2, 3]
  });

  useEffect(() => {
    async function fetchData() {
      try {
        const [eventsRes, sitesRes, classRes] = await Promise.all([
          axios.get(`${API_BASE}/events/geojson`),
          axios.get(`${API_BASE}/sites/geojson`),
          axios.get(`${API_BASE}/classifications`)
        ]);
        
        // Enrich events with class_id
        const classifications = classRes.data;
        const classMap = {};
        classifications.forEach(c => {
            classMap[c.event_id] = c.ml_class;
        });

        const enrichedEvents = eventsRes.data;
        enrichedEvents.features.forEach(f => {
            f.properties.class_id = classMap[f.properties.event_id] ?? -1;
        });

        setEventsGeoJSON(enrichedEvents);
        setSitesGeoJSON(sitesRes.data);
      } catch (err) {
        console.error("Failed to load initial data:", err);
      } finally {
        setLoading(false);
      }
    }
    fetchData();
  }, []);

  return (
    <div className="h-screen w-screen flex flex-col overflow-hidden bg-dark-900">
      {/* Top Header Navigation */}
      <header className="h-16 flex items-center justify-between px-6 bg-dark-800/90 border-b border-slate-700/50 backdrop-blur-md z-10">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-gradient-to-tr from-orange-500 to-red-500 flex items-center justify-center shadow-lg shadow-red-500/20">
            <Activity size={24} className="text-white" />
          </div>
          <div>
            <h1 className="text-lg font-semibold tracking-tight text-white">SIH 26162</h1>
            <p className="text-xs text-slate-400 font-medium tracking-wider uppercase">Thermal Intelligence</p>
          </div>
        </div>
        
        <div className="flex items-center gap-4">
          <div className="px-4 py-2 rounded-full bg-red-500/10 border border-red-500/20 flex items-center gap-2">
            <span className="relative flex h-3 w-3">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-3 w-3 bg-red-500"></span>
            </span>
            <span className="text-sm font-medium text-red-400">Live Engine Active</span>
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <div className="flex-1 relative flex">
        {loading ? (
          <div className="absolute inset-0 flex items-center justify-center bg-dark-900 z-50">
            <div className="flex flex-col items-center gap-4">
              <div className="w-8 h-8 border-4 border-slate-600 border-t-orange-500 rounded-full animate-spin"></div>
              <p className="text-slate-400 animate-pulse">Loading intelligence layers...</p>
            </div>
          </div>
        ) : (
          <>
            {/* Map Underlay */}
            <MapView 
              eventsGeoJSON={eventsGeoJSON} 
              sitesGeoJSON={sitesGeoJSON}
              filters={filters}
              onEventClick={setSelectedEventId}
              onSiteClick={setSelectedSiteId}
            />

            {/* Left Panel: Filters and Alerts */}
            <div className="absolute top-6 left-6 z-10 w-80 flex flex-col gap-4 pointer-events-none">
              <div className="pointer-events-auto shrink-0">
                <FiltersPanel filters={filters} setFilters={setFilters} />
              </div>
              <div className="pointer-events-auto shrink-0">
                <AlertsPanel onEventClick={setSelectedEventId} />
              </div>
            </div>

            {/* Right Panel: Details Overlay */}
            <div className="absolute top-6 right-6 bottom-6 z-10 w-[400px] flex flex-col gap-4 pointer-events-none overflow-y-auto scrollbar-hide">
              {selectedEventId && (
                <div className="pointer-events-auto shrink-0">
                  <EventPanel eventId={selectedEventId} onClose={() => setSelectedEventId(null)} />
                </div>
              )}
              
              {selectedSiteId && (
                <div className="pointer-events-auto shrink-0">
                  <SitePanel siteId={selectedSiteId} onClose={() => setSelectedSiteId(null)} />
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

export default App;
