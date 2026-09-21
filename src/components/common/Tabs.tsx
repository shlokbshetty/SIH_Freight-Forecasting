import React from 'react';
import './Tabs.css';

export interface TabItem {
  id: string;
  label: string;
  icon?: React.ReactNode;
  count?: number;
}

interface TabsProps {
  tabs: TabItem[];
  activeTab: string;
  onChange: (id: string) => void;
  className?: string;
}

export const Tabs: React.FC<TabsProps> = ({
  tabs,
  activeTab,
  onChange,
  className = '',
}) => {
  return (
    <div className={`fi-tabs ${className}`} role="tablist">
      {tabs.map((tab) => {
        const isActive = tab.id === activeTab;
        return (
          <button
            key={tab.id}
            role="tab"
            aria-selected={isActive}
            className={`fi-tabs__item ${isActive ? 'fi-tabs__item--active' : ''}`}
            onClick={() => onChange(tab.id)}
          >
            {tab.icon && <span className="fi-tabs__icon">{tab.icon}</span>}
            <span>{tab.label}</span>
            {tab.count !== undefined && (
              <span className={`fi-tabs__count ${isActive ? 'fi-tabs__count--active' : ''}`}>
                {tab.count}
              </span>
            )}
            {isActive && <span className="fi-tabs__pill" />}
          </button>
        );
      })}
    </div>
  );
};

export default Tabs;
