import React from 'react';
import { Badge, type BadgeVariant } from './Badge';
import './StatCard.css';

interface StatCardProps {
  title: string;
  value: string | number;
  subtext?: string;
  badgeText?: string;
  badgeVariant?: BadgeVariant;
  icon?: React.ReactNode;
  trend?: 'up' | 'down' | 'neutral';
  className?: string;
}

export const StatCard: React.FC<StatCardProps> = ({
  title,
  value,
  subtext,
  badgeText,
  badgeVariant = 'muted',
  icon,
  className = '',
}) => {
  return (
    <div className={`stat-card panel ${className}`}>
      <div className="stat-card__header">
        <span className="stat-card__title">{title}</span>
        {icon && <span className="stat-card__icon">{icon}</span>}
      </div>

      <div className="stat-card__body">
        <div className="stat-card__value mono">{value}</div>
        {badgeText && (
          <Badge variant={badgeVariant} dot>
            {badgeText}
          </Badge>
        )}
      </div>

      {subtext && <div className="stat-card__subtext">{subtext}</div>}
    </div>
  );
};

export default StatCard;
