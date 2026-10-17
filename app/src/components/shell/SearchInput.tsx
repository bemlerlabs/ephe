/**
 * Ephe — S wave: SearchInput for content pages (the app-shell pattern).
 * A controlled component; icon + rounded field in the marketplace look.
 */
import { Search } from 'lucide-react'

export default function SearchInput({
  value,
  onChange,
  placeholder,
  label,
  testid = 'page-search',
}: {
  value: string
  onChange: (v: string) => void
  placeholder: string
  label: string
  /** Two search fields in one view need their own anchors. */
  testid?: string
}) {
  return (
    <div className="relative">
      <Search
        className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-faint"
        aria-hidden="true"
      />
      <input
        type="search"
        data-testid={testid}
        aria-label={label}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full rounded-xl border border-hairline bg-background/60 py-2.5 pl-9 pr-3 text-ui-sm text-foreground/90 placeholder:text-ink-faint focus-ring focus:border-brand/50 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/40"
      />
    </div>
  )
}
