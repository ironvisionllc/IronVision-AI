import React from "react";

// Reusable skeleton components for loading states
export const Skeleton = ({ className = "" }) => (
  <div className={`iv-skeleton ${className}`} />
);

export const SkeletonText = ({ lines = 1, className = "" }) => (
  <div className={`space-y-2 ${className}`}>
    {Array.from({ length: lines }).map((_, i) => (
      <div 
        key={i} 
        className="iv-skeleton h-4 rounded"
        style={{ width: i === lines - 1 && lines > 1 ? '60%' : '100%' }}
      />
    ))}
  </div>
);

export const SkeletonCard = ({ className = "" }) => (
  <div className={`iv-card p-5 ${className}`}>
    <div className="flex items-start gap-4">
      <Skeleton className="w-12 h-12 rounded-xl flex-shrink-0" />
      <div className="flex-1 space-y-3">
        <Skeleton className="h-5 w-3/4 rounded" />
        <Skeleton className="h-4 w-1/2 rounded" />
        <div className="flex gap-2">
          <Skeleton className="h-6 w-16 rounded-full" />
          <Skeleton className="h-6 w-20 rounded-full" />
        </div>
      </div>
    </div>
  </div>
);

export const SkeletonStatCard = () => (
  <div className="iv-stat-card">
    <div className="flex items-start justify-between">
      <div className="space-y-2">
        <Skeleton className="h-3 w-16 rounded" />
        <Skeleton className="h-8 w-12 rounded" />
      </div>
      <Skeleton className="w-10 h-10 rounded-xl" />
    </div>
  </div>
);

export const SkeletonTable = ({ rows = 5, cols = 4 }) => (
  <div className="iv-card overflow-hidden">
    <div className="bg-gray-50 dark:bg-gray-800/50 px-4 py-3 border-b border-gray-200 dark:border-gray-700">
      <div className="flex gap-4">
        {Array.from({ length: cols }).map((_, i) => (
          <Skeleton key={i} className="h-4 flex-1 rounded" />
        ))}
      </div>
    </div>
    <div className="divide-y divide-gray-100 dark:divide-gray-800">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="px-4 py-4 flex gap-4">
          {Array.from({ length: cols }).map((_, j) => (
            <Skeleton key={j} className="h-5 flex-1 rounded" />
          ))}
        </div>
      ))}
    </div>
  </div>
);

export const SkeletonPage = () => (
  <div className="space-y-6 animate-pulse">
    <div className="flex justify-between items-center">
      <div className="space-y-2">
        <Skeleton className="h-8 w-48 rounded" />
        <Skeleton className="h-4 w-64 rounded" />
      </div>
      <Skeleton className="h-10 w-32 rounded-xl" />
    </div>
    <div className="grid grid-cols-4 gap-4">
      {[1,2,3,4].map(i => <SkeletonStatCard key={i} />)}
    </div>
    <div className="space-y-3">
      {[1,2,3].map(i => <SkeletonCard key={i} />)}
    </div>
  </div>
);

// Animated loading spinner
export const LoadingSpinner = ({ size = 24, className = "" }) => (
  <div 
    className={`iv-spinner ${className}`}
    style={{ width: size, height: size }}
  />
);

// Full page loader
export const PageLoader = ({ message = "Loading..." }) => (
  <div className="flex flex-col items-center justify-center h-[60vh] gap-4">
    <LoadingSpinner size={40} />
    <p className="text-sm text-gray-500 dark:text-gray-400 font-medium">{message}</p>
  </div>
);

// Empty state component
export const EmptyState = ({ 
  icon: Icon, 
  title, 
  description, 
  action,
  actionLabel,
  className = ""
}) => (
  <div className={`iv-empty-state py-12 ${className}`}>
    {Icon && (
      <div className="iv-empty-state-icon mb-4">
        <Icon size={32} weight="duotone" className="text-gray-400" />
      </div>
    )}
    <p className="iv-empty-state-title">{title}</p>
    {description && <p className="iv-empty-state-description mt-1">{description}</p>}
    {action && actionLabel && (
      <button 
        onClick={action}
        className="mt-4 iv-btn iv-btn-primary"
      >
        {actionLabel}
      </button>
    )}
  </div>
);

export default { 
  Skeleton, 
  SkeletonText, 
  SkeletonCard, 
  SkeletonStatCard, 
  SkeletonTable,
  SkeletonPage,
  LoadingSpinner, 
  PageLoader, 
  EmptyState 
};
