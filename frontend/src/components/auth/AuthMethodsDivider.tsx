interface Props {
  label?: string;
}

export function AuthMethodsDivider({ label = 'or' }: Props) {
  return (
    <div className="relative my-1">
      <div className="absolute inset-0 flex items-center" aria-hidden>
        <div className="w-full border-t border-border" />
      </div>
      <div className="relative flex justify-center">
        <span className="px-3 text-[11px] uppercase tracking-wider text-muted-foreground bg-card">
          {label}
        </span>
      </div>
    </div>
  );
}
