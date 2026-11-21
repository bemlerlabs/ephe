import { Skeleton } from '@/components/ui'

/** P1-10: boot placeholder for the message list while `initFromDb()` hydrates
 *  the persisted sessions. Prevents the welcome/empty flash and the
 *  "spinner or nothing" hole on a cold start. Three hinted turns
 *  (user right, assistant left) mirror the real bubble geometry. */
export default function ChatSkeleton() {
  return (
    <div
      data-testid="chat-skeleton"
      aria-hidden="true"
      className="flex-1 min-h-0 overflow-hidden px-4"
    >
      <div className="max-w-5xl mx-auto py-6 space-y-6">
        <div className="flex justify-end">
          <div className="w-2/3 sm:w-1/2 space-y-2 rounded-2xl glass-reading p-3">
            <Skeleton className="h-3 w-full" />
            <Skeleton className="h-3 w-4/5" />
          </div>
        </div>
        <div className="flex justify-start">
          <div className="w-3/4 sm:w-2/3 space-y-2 rounded-2xl glass-reading p-3">
            <Skeleton className="h-3 w-full" />
            <Skeleton className="h-3 w-full" />
            <Skeleton className="h-3 w-2/3" />
          </div>
        </div>
        <div className="flex justify-start">
          <div className="w-1/2 space-y-2 rounded-2xl glass-reading p-3">
            <Skeleton className="h-3 w-full" />
            <Skeleton className="h-3 w-3/4" />
          </div>
        </div>
      </div>
    </div>
  )
}
