export function Loader({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex-1 flex items-center justify-center min-h-[50vh]">
      <div className="flex flex-col items-center gap-3 text-muted text-sm">
        <div className="w-8 h-8 border-2 border-stone-300 border-t-accent rounded-full animate-spin" />
        <span>{label}</span>
      </div>
    </div>
  );
}
