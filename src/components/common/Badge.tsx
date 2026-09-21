import React from 'react';
import './Badge.css';

export type BadgeVariant = 'green' | 'amber' | 'red' | 'blue' | 'copper' | 'muted';

interface BadgeProps {
  variant?: BadgeVariant;
  dot?: boolean;
  children: React.ReactNode;
  className?: string;
}

export const Badge: React.FC<BadgeProps> = ({
  variant = 'muted',
  dot = false,
  children,
  className = '',
}) => {
  return (
    <span className={`badge badge-${variant} ${className}`}>
      {dot && <span className={`dot dot-${variant}`} />}
      {children}
    </span>
  );
};

export default Badge;
