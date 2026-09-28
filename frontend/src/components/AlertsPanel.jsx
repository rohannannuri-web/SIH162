import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { AlertTriangle, ChevronRight } from 'lucide-react';

const API_BASE = 'http://127.0.0.1:8000/api';

const AlertsPanel = ({ onEventClick }) => {
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchAlerts() {
      try {
        const response = await axios.get(`${API_BASE}/alerts/`);
        setAlerts(response.data);
      } catch (err) {
        console.error("Failed to fetch alerts:", err);
      } finally {
        setLoading(false);
      }
    }
    fetchAlerts();
    
    // Auto refresh every 30 seconds
    const interval = setInterval(fetchAlerts, 30000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="bg-dark-800 border border-slate-700/60 rounded-xl shadow-2xl backdrop-blur-md overflow-hidden flex flex-col">
      <div className="px-5 py-4 border-b border-slate-700/50 flex items-center justify-between bg-dark-800/80">
        <div className="flex items-center gap-2">
          <AlertTriangle size={18} className="text-red-500" />
          <h2 className="text-sm font-semibold text-slate-200 uppercase tracking-wider">Active Alerts</h2>
        </div>
        <span className="text-xs font-medium px-2 py-0.5 rounded-md bg-red-500/10 text-red-400 border border-red-500/20">
          {alerts.length} High Risk
        </span>
      </div>
      
      <div className="p-2 max-h-80 overflow-y-auto scrollbar-hide flex flex-col gap-2">
        {loading ? (
          <div className="p-4 text-center text-sm text-slate-400">Loading alerts...</div>
        ) : alerts.length === 0 ? (
          <div className="p-4 text-center text-sm text-slate-400">No active alerts.</div>
        ) : (
          alerts.map((alert) => (
            <div 
              key={alert.alert_id}
              onClick={() => onEventClick(alert.event_id)}
              className="p-3 rounded-lg bg-dark-700 hover:bg-slate-700/50 cursor-pointer transition-colors border border-slate-600/30 flex flex-col gap-2 group"
            >
              <div className="flex justify-between items-start">
                <span className="text-xs font-medium text-red-400">{alert.classification}</span>
                <ChevronRight size={14} className="text-slate-500 group-hover:text-white transition-colors" />
              </div>
              <p className="text-sm text-slate-200 font-medium leading-tight">
                {alert.facility}
              </p>
              <div className="flex items-center justify-between mt-1">
                 <span className="text-xs text-slate-400">FRP: {alert.frp} MW</span>
                 <span className="text-xs text-orange-400 font-semibold">{alert.frp_ratio.toFixed(1)}x Baseline</span>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

export default AlertsPanel;
