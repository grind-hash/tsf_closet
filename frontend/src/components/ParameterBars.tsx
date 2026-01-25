import type { SessionStats } from '../types';
import './ParameterBars.css';

interface ParameterBarsProps {
  stats: SessionStats;
}

export default function ParameterBars({ stats }: ParameterBarsProps) {
  return (
    <div className="parameter-bars">
      <h4>🌟 きょうのちょうし</h4>
      
      <div className="parameter-bar">
        <label>
          <span className="emoji">✨</span>
          ワクワクど
        </label>
        <div className="progress-container">
          <div
            className="progress-bar excitement"
            style={{ width: `${stats.excitement}%` }}
          />
        </div>
        <span className="value">{stats.excitement}</span>
      </div>

      <div className="parameter-bar">
        <label>
          <span className="emoji">🎭</span>
          なりきりど
        </label>
        <div className="progress-container">
          <div
            className="progress-bar immersion"
            style={{ width: `${stats.immersion}%` }}
          />
        </div>
        <span className="value">{stats.immersion}</span>
      </div>

      <div className="parameter-bar">
        <label>
          <span className="emoji">🚀</span>
          チャレンジど
        </label>
        <div className="progress-container challenge-container">
          <div
            className="progress-bar challenge"
            style={{ 
              width: `${Math.abs(stats.challenge)}%`,
              marginLeft: stats.challenge >= 0 ? '50%' : `${50 - Math.abs(stats.challenge)}%`,
            }}
          />
        </div>
        <span className="value">{stats.challenge}</span>
      </div>
    </div>
  );
}
