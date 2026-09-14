function fulfillmentColor(confirmed: number, headcount: number): string {
  if (confirmed >= headcount) return "var(--color-approved)";
  if (confirmed > 0) return "var(--color-pending)";
  return "var(--color-border)";
}

export function FulfillmentBar({
  confirmed,
  headcount,
  width = 90,
}: {
  confirmed: number;
  headcount: number;
  width?: number;
}) {
  const pct = headcount > 0 ? Math.min(100, Math.round((confirmed / headcount) * 100)) : 0;
  return (
    <div className="flex items-center gap-2.5">
      <div className="h-1.5 overflow-hidden rounded-full bg-border" style={{ width }}>
        <div
          className="h-full rounded-full"
          style={{ width: `${pct}%`, backgroundColor: fulfillmentColor(confirmed, headcount) }}
        />
      </div>
      <div className="font-mono text-xs text-text-2">
        {confirmed}/{headcount}
      </div>
    </div>
  );
}
