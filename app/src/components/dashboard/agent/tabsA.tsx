'use client'

// A thin re-export rail: the tab implementations live in the split modules
// (the architecture boundary maxFileLines=400). panel.tsx and the tests keep
// importing from this file unchanged.
export { SubagentsTab } from './tabsSubagents'
export { MemoryTab } from './tabsMemory'
export { TabPill } from './tabsTabPill'
export { TrajectoryTab } from './tabsTrajectory'
export { SideConversationTab } from './tabsSideConversation'
