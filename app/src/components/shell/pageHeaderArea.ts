import { createContext } from 'react'

/**
 * The area title a surface already announces. A section header whose title repeats
 * it keeps its text and loses the heading role, so the outline carries the name
 * once. Null means the surface offers no area title and every header is a heading.
 */
export const PageHeaderAreaTitle = createContext<string | null>(null)
