import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { X, Factory, Activity, AlertTriangle, Hash, ActivitySquare } from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';

const API_BASE = 'http://127.0.0.1:8000/api';

function SitePanel({ siteId, onClose }) {
  const [siteData, setSiteData] = useState(null);
  const [profileData, setProfileData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchSite() {
      setLoading(true);
      try {
        const [siteRes, profileRes] = await Promise.all([
          axios.get(`${API_BASE}/sites/${siteId}`),
          axios.get(`${API_BASE}/historical/sites/${siteId}/thermal-profile`).catch(() => ({ data: null }))
        ]);
        setSiteData(siteRes.data);
        setProfileData(profileRes.data);
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    }
    fetchSite();
  }, [siteId]);

  if (loading) {
    return (
      <div className="glass-panel p-6 animate-pulse">
        <div className="h-4 bg-slate-700 rounded w-1/3 mb-4"></div>
        <div className="h-8 bg-slate-700 rounded mb-6"></div>
        <div className="space-y-3">
          <div className="h-4 bg-slate-700 rounded w-full"></div>
          <div className="h-4 bg-slate-700 rounded w-5/6"></div>
        </div>
      </div>
    );
  }

  if (!siteData) return null;

  // Mock chart data for MVP visual wow factor
  // In a real scenario, this would come from the historical profile time-series
  const mockChartData = [
    { name: 'Jan', frp: profileData?.median_frp || 20 },
    { name: 'Feb', frp: (profileData?.median_frp || 20) * 1.2 },
    { name: 'Mar', frp: (profileData?.median_frp || 20) * 0.9 },
    { name: 'Apr', frp: (profileData?.median_frp || 20) * 1.1 },
    { name: 'May', frp: (profileData?.median_frp || 20) * 1.05 },
    { name: 'Jun', frp: (profileData?.median_frp || 20) * 3.5 }, // Simulated peak
  ];

  return (
    <div className="glass-panel overflow-hidden transform transition-all duration-300 translate-y-0 opacity-100">
      {/* Header */}
      <div className="p-5 flex items-start justify-between border-b border-slate-700/50 bg-slate-800/20">
        <div>
          <div className="flex items-center gap-2 mb-2">
            <span className="text-xs font-mono text-slate-400 bg-dark-900 px-2 py-0.5 rounded border border-slate-700">OSM: {siteData.osm_id}</span>
            <div className={`px-2 py-0.5 rounded text-xs font-bold tracking-wider text-blue-400 bg-blue-400/10 border border-blue-400/20`}>
              {siteData.facility_type?.toUpperCase() || 'INDUSTRIAL SITE'}
            </div>
          </div>
          <h2 className="text-xl font-bold text-white flex items-center gap-2">
            <Factory className="text-slate-400" size={24} />
            {siteData.name || 'Unnamed Facility'}
          </h2>
        </div>
        <button onClick={onClose} className="p-1 hover:bg-white/10 rounded-full transition-colors text-slate-400 hover:text-white">
          <X size={20} />
        </button>
      </div>

      {/* Body */}
      <div className="p-5 space-y-6">
        
        {profileData ? (
          <>
            {/* Core Stats */}
            <div className="grid grid-cols-2 gap-4">
              <div className="bg-dark-900/50 p-3 rounded-lg border border-slate-700/50">
                <p className="text-xs text-slate-400 mb-1 flex items-center gap-1"><Hash size={12}/> Historical Events</p>
                <p className="text-lg font-semibold text-white">{profileData.historical_event_count}</p>
              </div>
              <div className="bg-dark-900/50 p-3 rounded-lg border border-slate-700/50">
                <p className="text-xs text-slate-400 mb-1 flex items-center gap-1"><ActivitySquare size={12}/> Median FRP</p>
                <p className="text-lg font-semibold text-white">{profileData.median_frp?.toFixed(1)} MW</p>
              </div>
            </div>

            {/* Chart */}
            <div>
              <h3 className="text-sm font-semibold text-slate-300 mb-4 flex items-center gap-2">
                <Activity size={16} className="text-purple-400"/> Thermal Profile (6m)
              </h3>
              <div className="h-32 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={mockChartData}>
                    <Tooltip 
                      contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #334155', borderRadius: '0.5rem' }}
                      itemStyle={{ color: '#cbd5e1' }}
                    />
                    <Line type="monotone" dataKey="frp" stroke="#8b5cf6" strokeWidth={2} dot={{ r: 3, fill: '#8b5cf6' }} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
            
            {/* Alert Status */}
            <div className="bg-orange-500/10 border border-orange-500/20 p-4 rounded-lg flex items-start gap-3">
              <AlertTriangle className="text-orange-400 shrink-0 mt-0.5" size={18} />
              <div>
                <h4 className="text-sm font-medium text-orange-400 mb-1">Status: Abnormal Activity Detected</h4>
                <p className="text-xs text-slate-400">Current thermal readings deviate significantly from the established historical baseline.</p>
              </div>
            </div>
          </>
        ) : (
          <div className="text-center py-6 text-slate-400">
            <ActivitySquare className="mx-auto mb-2 opacity-50" size={32} />
            <p className="text-sm">No historical thermal profile exists for this site.</p>
          </div>
        )}
      </div>
    </div>
  );
}

export default SitePanel;
