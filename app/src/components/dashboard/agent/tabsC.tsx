'use client'

// A thin re-export rail, as with tabsA: the tab implementations live in the
// split modules (the architecture boundary maxFileLines=400). panel.tsx and
// index.ts keep importing from this file unchanged.
export { ReviewTab } from './reviewTab'
export { TerminalTab } from './terminalTab'
