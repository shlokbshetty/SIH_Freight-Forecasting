import React from 'react';
import './Card.css';

interface CardProps {
  title?: React.ReactNode;
  subtitle?: string;
  action?: React.ReactNode;
  children: React.ReactNode;
  variant?: 'default' | 'raised' | 'interactive';
  className?: string;
  bodyClassName?: string;
}

export const Card: React.FC<CardProps> = ({
  title,
  subtitle,
  action,
  children,
  variant = 'default',
  className = '',
  bodyClassName = '',
}) => {
  return (
    <div className={`fi-card fi-card--${variant} ${className}`}>
      {(title || action) && (
        <div className="fi-card__header">
          <div>
            {typeof title === 'string' ? <h3 className="fi-card__title">{title}</h3> : title}
            {subtitle && <p className="fi-card__subtitle">{subtitle}</p>}
          </div>
          {action && <div className="fi-card__action">{action}</div>}
        </div>
      )}
      <div className={`fi-card__body ${bodyClassName}`}>{children}</div>
    </div>
  );
};

export default Card;
