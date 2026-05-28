interface ReturnLabelProps {
  value: number | null | undefined;
}

export default function ReturnLabel({ value }: ReturnLabelProps) {
  if (value == null) return <span style={{ color: '#999' }}>—</span>;

  const color = value > 0 ? '#cf1322' : value < 0 ? '#389e0d' : '#666';
  const prefix = value > 0 ? '+' : '';
  const pct = (value * 100).toFixed(2);

  return <span style={{ color, fontWeight: 500 }}>{`${prefix}${pct}%`}</span>;
}
