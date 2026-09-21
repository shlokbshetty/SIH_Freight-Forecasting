import React, { useState } from 'react';
import { Anchor, Sparkles, X, ArrowRight, ShieldCheck, TrendingUp, Compass } from 'lucide-react';
import './OnboardingBanner.css';

interface OnboardingBannerProps {
  storageKey?: string;
}

export const OnboardingBanner: React.FC<OnboardingBannerProps> = ({
  storageKey = 'freightiq_onboarding_dismissed',
}) => {
  const [dismissed, setDismissed] = useState<boolean>(() => {
    return localStorage.getItem(storageKey) === 'true';
  });

  const handleDismiss = () => {
    localStorage.setItem(storageKey, 'true');
    setDismissed(true);
  };

  if (dismissed) return null;

  return (
    <div className="onboarding-banner panel" role="region" aria-label="Welcome & Onboarding">
      <div className="onboarding-banner__header">
        <div className="onboarding-banner__title-wrap">
          <div className="onboarding-banner__icon">
            <Anchor size={18} />
          </div>
          <div>
            <div className="onboarding-banner__tag">
              <Sparkles size={12} />
              <span>FREIGHTIQ VESSEL INTELLIGENCE</span>
            </div>
            <h2 className="onboarding-banner__heading">
              Welcome to FreightIQ Freight Forecasting & Charter Evaluation
            </h2>
          </div>
        </div>

        <button
          className="onboarding-banner__close"
          onClick={handleDismiss}
          title="Dismiss onboarding banner"
          aria-label="Dismiss banner"
        >
          <X size={16} />
        </button>
      </div>

      <div className="onboarding-banner__grid">
        <div className="onboarding-banner__card">
          <div className="onboarding-banner__card-icon green">
            <TrendingUp size={16} />
          </div>
          <div>
            <h4>Spot vs CVC Evaluation</h4>
            <p>Compare spot chartering against Contract of Affreightment (CVC) rates with quantile risk bands.</p>
          </div>
        </div>

        <div className="onboarding-banner__card">
          <div className="onboarding-banner__card-icon blue">
            <Compass size={16} />
          </div>
          <div>
            <h4>Interactive Route & Port GIS</h4>
            <p>Assess port feasibility, vessel draft limits, turnarounds, and bunker costs dynamically.</p>
          </div>
        </div>

        <div className="onboarding-banner__card">
          <div className="onboarding-banner__card-icon amber">
            <ShieldCheck size={16} />
          </div>
          <div>
            <h4>Real-time Market Timing</h4>
            <p>Identify optimal chartering windows and quantify waiting/demurrage exposure.</p>
          </div>
        </div>
      </div>

      <div className="onboarding-banner__footer">
        <span className="onboarding-banner__tip">
          💡 <strong>Pro Tip:</strong> Use the <strong>Evaluate (CVC)</strong> tab to model custom voyage legs and generate instant financial evaluation tables.
        </span>
        <button className="btn btn-primary btn-sm" onClick={handleDismiss}>
          <span>Explore Platform</span>
          <ArrowRight size={14} />
        </button>
      </div>
    </div>
  );
};

export default OnboardingBanner;
