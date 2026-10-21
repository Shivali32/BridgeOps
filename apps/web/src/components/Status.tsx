export default function Status({ value }: { value: string }) {
  return <span className={`status-badge status-${value}`}>{value.replaceAll('_', ' ')}</span>
}
