import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { X, Flame, ShieldAlert, Navigation, Search, CheckCircle2, Wind, Zap, BarChart3 } from 'lucide-react';

const API_BASE = 'http://127.0.0.1:8000/api';

const CLASS_NAMES = {
  0: 'Natural / Forest Fire',
  1: 'Agricultural Burning',
  2: 'Persistent Industrial Source',
  3: 'Abnormal Industrial Thermal Event',
};

function ShapBar({ feature, value }) {
  const absVal = Math.abs(value);
  const maxWidth = 80; // px
  const width = Math.min(absVal * 600, maxWidth);
  const isPositive = value >= 0;
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="text-slate-400 w-36 truncate flex-shrink-0">{feature}</span>
      <div className="flex-1 flex items-center gap-1">
        <div
          className={`h-2 rounded-full ${isPositive ? 'bg-red-400' : 'bg-blue-400'}`}
          style={{ width: `${width}px`, minWidth: '2px' }}
        />
        <span className={`font-mono ${isPositive ? 'text-red-400' : 'text-blue-400'}`}>
          {value > 0 ? '+' : ''}{value.toFixed(4)}
        </span>
      </div>
    </div>
  );
}

function FusedScoreBar({ score, agreement }) {
  const pct = Math.round((score ?? 0) * 100);
  const color =
    pct > 80 ? 'bg-red-500' :
    pct > 60 ? 'bg-orange-500' :
    pct > 40 ? 'bg-yellow-500' : 'bg-green-500';

  const agreeColor = {
    BOTH: 'text-red-400',
    THERMAL_ONLY: 'text-orange-400',
    ATMOSPHERIC_ONLY: 'text-purple-400',
    NEITHER: 'text-green-400',
  }[agreement] ?? 'text-slate-400';

  return (
    <div className="space-y-1">
      <div className="flex justify-between items-center">
        <span className="text-xs text-slate-400">Fused Confidence</span>
        <span className={`text-xs font-bold font-mono ${agreeColor}`}>{pct}%</span>
      </div>
      <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
        <div className={`h-full ${color} rounded-full transition-all duration-500`} style={{ width: `${pct}%` }} />
      </div>
      <p className={`text-xs ${agreeColor}`}>{agreement?.replace(/_/g, ' ')}</p>
    </div>
  );
}

function EventPanel({ eventId, onClose }) {
  const [eventData, setEventData] = useState(null);
  const [explainData, setExplainData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [satData, setSatData] = useState(null);
  const [satLoading, setSatLoading] = useState(false);
  const [fusedData, setFusedData] = useState(null);

  useEffect(() => {
    async function fetchEvent() {
      setLoading(true);
      setSatData(null);
      setSatLoading(false);
      setFusedData(null);
      try {
        const [eventRes, explainRes, fusedRes] = await Promise.all([
          axios.get(`${API_BASE}/events/${eventId}`),
          axios.get(`${API_BASE}/classifications/${eventId}/explain`),
          axios.get(`${API_BASE}/atmospheric/fused/${eventId}`).catch(() => ({ data: null })),
        ]);
        setEventData(eventRes.data);
        setExplainData(explainRes.data);
        setFusedData(fusedRes.data);
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    }
    fetchEvent();
  }, [eventId]);

  const fetchSatellite = async () => {
    setSatLoading(true);
    try {
      const res = await axios.get(`${API_BASE}/satellite/${eventId}`);
      setSatData(res.data);
    } catch (err) {
      setSatData({ status: 'error', message: 'Failed to communicate with satellite API.' });
    } finally {
      setSatLoading(false);
    }
  };

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

  if (!eventData || !explainData) return null;

  const isHighRisk = explainData.risk === 'HIGH';
  const isAtmosAlert = fusedData?.signal_agreement === 'ATMOSPHERIC_ONLY';
  const riskColor = isHighRisk
    ? 'text-red-400 bg-red-400/10 border-red-400/20'
    : explainData.risk === 'MEDIUM'
    ? 'text-orange-400 bg-orange-400/10 border-orange-400/20'
    : 'text-green-400 bg-green-400/10 border-green-400/20';

  // Parse SHAP values
  let shapEntries = [];
  if (explainData.shap_values) {
    try {
      const shapObj = typeof explainData.shap_values === 'string'
        ? JSON.parse(explainData.shap_values)
        : explainData.shap_values;
      shapEntries = Object.entries(shapObj)
        .map(([k, v]) => ({ feature: k, value: v }))
        .sort((a, b) => Math.abs(b.value) - Math.abs(a.value));
    } catch (_) {}
  }

  return (
    <div className="glass-panel overflow-hidden transform transition-all duration-300 translate-y-0 opacity-100">
      {/* Header */}
      <div className={`p-5 flex items-start justify-between border-b ${isHighRisk ? 'border-red-500/30 bg-red-500/5' : isAtmosAlert ? 'border-purple-500/30 bg-purple-500/5' : 'border-slate-700/50'}`}>
        <div>
          <div className="flex items-center gap-2 mb-2">
            <span className="text-xs font-mono text-slate-400 bg-dark-900 px-2 py-0.5 rounded border border-slate-700">ID: {eventId}</span>
            <div className={`px-2 py-0.5 rounded text-xs font-bold tracking-wider ${riskColor} border`}>
              {explainData.risk} RISK
            </div>
            {isAtmosAlert && (
              <div className="px-2 py-0.5 rounded text-xs font-bold tracking-wider text-purple-400 bg-purple-400/10 border border-purple-400/20">
                ATMOS
              </div>
            )}
          </div>
          <h2 className="text-xl font-bold text-white flex items-center gap-2">
            {isHighRisk && <ShieldAlert className="text-red-500" size={24} />}
            {isAtmosAlert && <Wind className="text-purple-500" size={24} />}
            {explainData.classification}
          </h2>
        </div>
        <button onClick={onClose} className="p-1 hover:bg-white/10 rounded-full transition-colors text-slate-400 hover:text-white">
          <X size={20} />
        </button>
      </div>

      {/* Body */}
      <div className="p-5 space-y-5 max-h-[80vh] overflow-y-auto scrollbar-hide">

        {/* Core Stats */}
        <div className="grid grid-cols-2 gap-3">
          <div className="bg-dark-900/50 p-3 rounded-lg border border-slate-700/50">
            <p className="text-xs text-slate-400 mb-1 flex items-center gap-1"><Flame size={12} /> FRP (MW)</p>
            <p className="text-lg font-semibold text-white">{eventData.frp?.toFixed(1)}</p>
          </div>
          <div className="bg-dark-900/50 p-3 rounded-lg border border-slate-700/50">
            <p className="text-xs text-slate-400 mb-1 flex items-center gap-1"><Navigation size={12} /> Coordinates</p>
            <p className="text-sm font-mono text-white">{eventData.latitude?.toFixed(4)}, {eventData.longitude?.toFixed(4)}</p>
          </div>
        </div>

        {/* Fused Confidence Score (Phase 5b) */}
        {fusedData && fusedData.fused_score != null && (
          <div className="bg-dark-900/50 p-4 rounded-lg border border-slate-700/50">
            <p className="text-xs font-semibold text-slate-300 mb-3 flex items-center gap-2">
              <Zap size={14} className="text-yellow-400" /> Fused Confidence Score
            </p>
            <FusedScoreBar score={fusedData.fused_score} agreement={fusedData.signal_agreement} />
            {fusedData.alert_category && (
              <p className="mt-2 text-xs text-purple-400 bg-purple-500/10 border border-purple-500/20 rounded p-2">
                {fusedData.alert_category}
              </p>
            )}
            {fusedData.explanation && (
              <p className="mt-2 text-xs text-slate-400 leading-relaxed">{fusedData.explanation}</p>
            )}
          </div>
        )}

        {/* SHAP Explanation (Phase 6) */}
        {shapEntries.length > 0 && (
          <div>
            <h3 className="text-sm font-semibold text-slate-300 mb-3 flex items-center gap-2">
              <BarChart3 size={16} className="text-blue-400" /> SHAP Feature Attribution
            </h3>
            <div className="bg-dark-900/50 p-3 rounded-lg border border-slate-700/50 space-y-2">
              <p className="text-xs text-slate-500 mb-2">
                <span className="text-red-400">■</span> pushes toward this class &nbsp;
                <span className="text-blue-400">■</span> pushes away
              </p>
              {shapEntries.map(({ feature, value }) => (
                <ShapBar key={feature} feature={feature} value={value} />
              ))}
            </div>
          </div>
        )}

        {/* Classification Evidence */}
        <div>
          <h3 className="text-sm font-semibold text-slate-300 mb-3 flex items-center gap-2">
            <Search size={16} className="text-blue-400" /> Classification Evidence
          </h3>
          <div className="space-y-2">
            {explainData.evidence.map((ev, i) => (
              <div key={i} className="flex items-start gap-2 bg-blue-500/5 border border-blue-500/10 p-2.5 rounded-lg">
                <CheckCircle2 size={16} className="text-blue-400 shrink-0 mt-0.5" />
                <p className="text-sm text-slate-300 leading-snug">{ev}</p>
              </div>
            ))}
            {explainData.evidence.length === 0 && (
              <p className="text-sm text-slate-500 italic">No strong feature evidence identified.</p>
            )}
          </div>
        </div>

        {/* Satellite Evidence */}
        <div className="pt-4 border-t border-slate-700/50">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm font-semibold text-slate-300">Satellite Analysis</h3>
            {!satData && !satLoading && (
              <button
                onClick={fetchSatellite}
                className="text-xs bg-blue-600 hover:bg-blue-500 text-white px-2 py-1 rounded transition-colors"
              >
                Analyze Sentinel-2
              </button>
            )}
          </div>

          {satLoading && (
            <div className="animate-pulse h-32 bg-slate-700 rounded-lg flex items-center justify-center text-sm text-slate-400">
              Querying Sentinel-2 STAC...
            </div>
          )}
          {satData && satData.status === 'skipped' && (
            <div className="text-sm text-slate-400 bg-slate-800/50 p-3 rounded-lg border border-slate-700">{satData.evidence}</div>
          )}
          {satData && satData.status === 'success' && satData.image_url && (
            <div className="space-y-2">
              <div className="relative rounded-lg overflow-hidden border border-slate-700">
                <img src={satData.image_url} alt="Sentinel-2 True Color" className="w-full h-48 object-cover" />
                <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/80 to-transparent p-2">
                  <p className="text-xs text-white">Acquired: {new Date(satData.acquisition_date).toLocaleDateString()}</p>
                  <p className="text-xs text-white opacity-80">Cloud Cover: {satData.cloud_cover?.toFixed(1)}%</p>
                </div>
              </div>
              <p className="text-xs text-blue-400 flex items-center gap-1"><CheckCircle2 size={12} /> {satData.evidence}</p>
            </div>
          )}
          {satData && satData.status === 'success' && !satData.image_url && (
            <div className="text-sm text-slate-400 bg-slate-800/50 p-3 rounded-lg border border-slate-700">{satData.evidence}</div>
          )}
          {satData && satData.status === 'error' && (
            <div className="text-sm text-red-400 bg-red-900/20 p-3 rounded-lg border border-red-900">{satData.message || 'Failed to load.'}</div>
          )}
        </div>

        {/* Action Buttons */}
        <div className="pt-4 border-t border-slate-700/50 flex gap-3">
          <button className="flex-1 bg-slate-700 hover:bg-slate-600 text-white py-2 rounded-lg text-sm font-medium transition-colors">
            View History
          </button>
          {isHighRisk && (
            <button className="flex-1 bg-red-500 hover:bg-red-600 text-white py-2 rounded-lg text-sm font-medium shadow-lg shadow-red-500/20 transition-colors">
              Dispatch Alert
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

export default EventPanel;
