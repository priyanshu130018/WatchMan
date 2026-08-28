export function RabbitLogo({ className = "h-8 w-8" }: { className?: string }) {
  return (
    <div
      className={`grid place-items-center rounded-xl gradient-rabbit text-white shadow-cinema ${className}`}
      aria-hidden
    >
      <svg viewBox="0 0 24 24" fill="none" className="h-4/5 w-4/5">
        <path
          d="M8 3c.3 2 .8 3.5 1.7 4.7M16 3c-.3 2-.8 3.5-1.7 4.7"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinecap="round"
        />
        <circle cx="12" cy="14" r="6" stroke="currentColor" strokeWidth="1.6" />
        <circle cx="10" cy="13" r="0.8" fill="currentColor" />
        <circle cx="14" cy="13" r="0.8" fill="currentColor" />
        <path
          d="M11 16c.4.5 1.6.5 2 0"
          stroke="currentColor"
          strokeWidth="1.4"
          strokeLinecap="round"
        />
      </svg>
    </div>
  );
}
