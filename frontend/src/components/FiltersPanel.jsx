import React from 'react';
import { Filter } from 'lucide-react';

function FiltersPanel({ filters, setFilters }) {
  const toggleClass = (classId) => {
    setFilters(prev => {
      if (prev.classes.includes(classId)) {
        return { ...prev, classes: prev.classes.filter(c => c !== classId) };
      } else {
        return { ...prev, classes: [...prev.classes, classId] };
      }
    });
  };

  const classes = [
    { id: 3, label: 'Abnormal Industrial', color: 'bg-red-500', border: 'border-red-500' },
    { id: 2, label: 'Persistent Industrial', color: 'bg-orange-500', border: 'border-orange-500' },
    { id: 1, label: 'Agricultural Burning', color: 'bg-yellow-500', border: 'border-yellow-500' },
    { id: 0, label: 'Natural / Forest Fire', color: 'bg-green-500', border: 'border-green-500' },
  ];

  return (
    <div className="glass-panel p-5">
      <div className="flex items-center gap-2 mb-4 border-b border-slate-700/50 pb-3">
        <Filter size={18} className="text-slate-400" />
        <h2 className="font-semibold text-slate-100 tracking-wide">Filters & Layers</h2>
      </div>

      <div className="space-y-4">
        <div>
          <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">Event Classification</h3>
          <div className="space-y-2">
            {classes.map(c => {
              const isActive = filters.classes.includes(c.id);
              return (
                <button 
                  key={c.id}
                  onClick={() => toggleClass(c.id)}
                  className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-sm transition-all duration-200 border ${
                    isActive 
                      ? `${c.border} bg-dark-700/50 text-slate-100` 
                      : 'border-transparent hover:bg-dark-700/30 text-slate-400'
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <div className={`w-3 h-3 rounded-full ${c.color} ${isActive ? 'shadow-lg shadow-' + c.color.replace('bg-', '') + '/50' : 'opacity-50'}`}></div>
                    <span>{c.label}</span>
                  </div>
                  <div className={`w-4 h-4 rounded border flex items-center justify-center transition-colors ${
                    isActive ? `${c.color} border-transparent` : 'border-slate-600'
                  }`}>
                    {isActive && <svg viewBox="0 0 14 14" fill="none" className="w-3 h-3 text-white"><path d="M3 7.5L5.5 10L11 4.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>}
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        <div className="pt-2">
          <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">Intelligence Layers</h3>
          <div className="space-y-2">
            <button 
              onClick={() => setFilters(prev => ({ ...prev, showFusion: !prev.showFusion }))}
              className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-sm transition-all duration-200 border ${
                filters.showFusion ? 'border-purple-500 bg-dark-700/50 text-slate-100' : 'border-transparent hover:bg-dark-700/30 text-slate-400'
              }`}
            >
              <div className="flex items-center gap-3">
                <div className={`w-3 h-3 rounded-full border-2 border-purple-500 ${filters.showFusion ? 'bg-transparent shadow-lg shadow-purple-500/50' : 'opacity-50'}`}></div>
                <span>4-Channel Fusion Scores</span>
              </div>
            </button>

            <button 
              onClick={() => setFilters(prev => ({ ...prev, showUnregistered: !prev.showUnregistered }))}
              className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-sm transition-all duration-200 border ${
                filters.showUnregistered ? 'border-pink-500 bg-dark-700/50 text-slate-100' : 'border-transparent hover:bg-dark-700/30 text-slate-400'
              }`}
            >
              <div className="flex items-center gap-3">
                <div className={`w-3 h-3 rounded-full bg-pink-500 ${filters.showUnregistered ? 'shadow-lg shadow-pink-500/50 animate-pulse' : 'opacity-50'}`}></div>
                <span>Unregistered Activity</span>
              </div>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default FiltersPanel;
